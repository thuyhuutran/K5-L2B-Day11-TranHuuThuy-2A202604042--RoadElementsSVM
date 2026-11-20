"""road_check: compare a learner's CVAT for images 1.1 export with GT under guideline Road v1.0.

Subcommands
    lint      FILE...                         learner self-check, no GT needed
    check     --gt GT... --sub SUB...         one learner vs GT: QC1 findings + automatic rubric part
    selftest  [--gt GT...]                    mandatory checker self-test (synthetic GT by default)
    batch     --gt GT... --submissions DIR    every <name>-front.zip / <name>-fisheye.zip in DIR

Thresholds below are the values the checker uses; their status (guide value vs Lab Coach
choice) is listed in lab/AGENTS.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from . import geometry as geo
from .cvat_xml import CvatFormatError, Image, Shape, Tag, load
from .taxonomy import (
    CORE_IMAGES,
    EXTRA_IMAGES,
    FISHEYE_CAMERAS,
    GUIDELINE_VERSION,
    SHAPE_LABELS,
    SIDE_CAMERAS,
    TAG_ATTRIBUTE,
    TAG_LABELS,
    expected_camera,
    image_slot,
)

THRESHOLDS = {
    "lane_match_px": 25.0,  # mean distance for a submitted polyline to be paired with a GT polyline
    "lane_dev_px": 5.0,  # guide: max deviation from the line centre (QC1-04 / QC1-11)
    "lane_stop_px": 15.0,  # first / last point must be this close to the GT ends
    "drivable_iou": 0.85,
    "drivable_spill": 0.05,
    "crosswalk_iou": 0.75,
    "curb_dev_px": 5.0,
    "box_match_iou": 0.5,
    "box_tight_iou": 0.75,
    "min_box_px": 8.0,  # guide: lights / signs from 8 px tall are mandatory
    "major_rate": 0.05,  # guide: major-error rate above 5 % of checked labels -> Rework
    "edge_zone_radius": 0.8,  # guide: outside 80 % of the image radius (lint hint only)
}

CODE_TITLES = {
    "QC1-01": "tag camera",
    "QC1-02": "đủ L1, R1",
    "QC1-03": "position",
    "QC1-04": "tâm vạch, chiều, điểm dừng",
    "QC1-05": "vạch đứt, che",
    "QC1-06": "style, color, kind",
    "QC1-07": "vùng lái",
    "QC1-08": "đèn, màu",
    "QC1-09": "facing, type, group, biển phụ",
    "QC1-10": "hình in, đủ biển",
    "QC1-11": "fisheye",
    "QC1-12": "file",
}
CODE_LEVEL = {
    "QC1-01": "nặng", "QC1-02": "nặng", "QC1-03": "nặng", "QC1-04": "chính", "QC1-05": "chính",
    "QC1-06": "chính", "QC1-07": "chính", "QC1-08": "nặng / chính", "QC1-09": "chính",
    "QC1-10": "chính", "QC1-11": "chính", "QC1-12": "nhẹ / nặng",
}
# Error type per code. Missed / extra / extent follow the three annotation error kinds named in
# ISO/IEC 5259-4 8.4.2 (under-detection, over-detection, range); "attribute" and "file" are course additions.
CODE_KIND = {
    "QC1-01": "sai thuộc tính / bỏ sót", "QC1-02": "bỏ sót", "QC1-03": "sai thuộc tính / thừa",
    "QC1-04": "sai phạm vi / bỏ sót", "QC1-05": "sai phạm vi / sai thuộc tính", "QC1-06": "sai thuộc tính",
    "QC1-07": "sai phạm vi / bỏ sót / thừa", "QC1-08": "bỏ sót / sai phạm vi / sai thuộc tính",
    "QC1-09": "sai thuộc tính", "QC1-10": "bỏ sót / sai phạm vi", "QC1-11": "sai phạm vi / sai thuộc tính",
    "QC1-12": "lỗi file",
}
SEV_VI = {"critical": "nặng", "major": "chính", "minor": "nhẹ"}

# Rubric rows: (id, title, points, automatic?)
RUBRIC = [
    ("tags", "Mọi ảnh đủ bốn tag, camera đúng", 4, True),
    ("file", "Export CVAT 1.1 mở lại được, đúng tên label và thuộc tính", 4, True),
    ("screens", "Ảnh chụp và bảng kiểm file (báo cáo mục 5–6)", 2, False),
    ("l1r1", "Set A: đủ L1/R1 trên mọi ảnh thấy được", 8, True),
    ("dev", "Set A: khoảng cách lớn nhất tới GT ≤ 5 px", 9, True),
    ("dir", "Set A: gần ra xa, vạch đứt một polyline, occluded, dừng đúng chỗ", 8, True),
    ("pos", "Thuộc tính làn: position khớp GT", 5, True),
    ("sck", "Thuộc tính làn: style / color / kind khớp GT", 5, True),
    ("spill", "Vùng lái: không tràn lề, vỉa hè, thân xe, phần sau cọc", 6, True),
    ("atype", "Vùng lái: direct / alternative đúng", 4, True),
    ("presence", "Đèn, biển: đủ từ 8 px, không gán hình in", 5, True),
    ("tight", "Đèn, biển: box sát vỏ, mép biển", 4, True),
    ("battr", "Đèn, biển: color, facing, type, group, biển phụ riêng", 6, True),
    ("arc", "Fisheye: polyline theo cung, lệch ≤ 5 px", 5, True),
    ("ferule", "Fisheye: thân xe không gán, position = other ở camera hai bên, edge_zone", 5, True),
    ("qc1", "Phiếu QC 1 cho bạn khác", 15, False),
    ("report", "Báo cáo cá nhân", 5, False),
]
AUTO_MAX = sum(p for _, _, p, auto in RUBRIC if auto)


@dataclass
class Finding:
    image: str
    code: str
    severity: str  # critical | major | minor
    ref: str
    message: str


@dataclass
class Result:
    name: str
    findings: list[Finding] = field(default_factory=list)
    checked: Counter = field(default_factory=Counter)
    total_checked: int = 0
    attempted: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra_shapes: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
    rubric: list[dict] = field(default_factory=list)

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def major_rate(self) -> float:
        return self.count("major") / self.total_checked if self.total_checked else 0.0

    @property
    def decision(self) -> str:
        if self.count("critical"):
            return "Rework"
        if self.major_rate > THRESHOLDS["major_rate"]:
            return "Rework"
        return "Release"

    @property
    def auto_score(self) -> float:
        return round(sum(r["score"] for r in self.rubric if r["auto"]), 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "guideline": GUIDELINE_VERSION,
            "attempted_core": self.attempted,
            "missing_core": self.missing,
            "extra_images_shapes": self.extra_shapes,
            "checked_labels": self.total_checked,
            "checked_by_code": dict(sorted(self.checked.items())),
            "critical": self.count("critical"),
            "major": self.count("major"),
            "minor": self.count("minor"),
            "major_rate": round(self.major_rate, 4),
            "decision_auto": self.decision,
            "auto_score": self.auto_score,
            "auto_max": AUTO_MAX,
            "rubric": self.rubric,
            "findings": [asdict(f) for f in self.findings],
        }


# --------------------------------------------------------------------------- validation
def _shape_problems(s: Shape) -> tuple[bool, list[str]]:
    """(usable for matching, problems). Unknown label / wrong shape type / bad geometry -> unusable."""
    spec = SHAPE_LABELS.get(s.label)
    if spec is None:
        return False, [f"label lạ '{s.label}'"]
    if s.kind != spec["type"]:
        return False, [f"{s.label} phải là {spec['type']}, file có {s.kind}"]
    need = {"polyline": 2, "polygon": 3, "rectangle": 2}[spec["type"]]
    if len(s.points) < need:
        return False, [f"{s.label} chỉ có {len(s.points)} điểm"]
    probs = []
    for attr, values in spec["select"].items():
        v = s.attributes.get(attr)
        if v is None or v == "":
            probs.append(f"thiếu thuộc tính {attr}")
        elif v not in values:
            probs.append(f"{attr}='{v}' không thuộc {values}")
    for attr in spec["checkbox"]:
        v = s.attributes.get(attr, "false").lower()
        if v not in {"true", "false"}:
            probs.append(f"{attr}='{v}' phải là true/false")
    extra = set(s.attributes) - set(spec["select"]) - set(spec["checkbox"])
    if extra:
        probs.append(f"thuộc tính lạ {sorted(extra)}")
    return True, probs


def _tag_problems(t: Tag) -> list[str]:
    vals = TAG_LABELS.get(t.label)
    if vals is None:
        return [f"tag lạ '{t.label}'"]
    v = t.attributes.get(TAG_ATTRIBUTE)
    if v not in vals:
        return [f"tag {t.label}: giá trị '{v}' không thuộc {vals}"]
    return []


def _checkbox(s: Shape, attr: str) -> bool:
    return s.attributes.get(attr, "false").lower() == "true"


# --------------------------------------------------------------------------- per-image check
class _ImageChecker:
    def __init__(self, gt: Image, sub: Image, res: Result):
        self.gt, self.sub, self.res = gt, sub, res
        self.slot = image_slot(gt.name) or gt.name
        gt_cam = gt.tag_value("camera") or expected_camera(gt.name) or "front"
        self.camera = gt_cam
        self.fisheye = gt_cam in FISHEYE_CAMERAS
        self._pending: dict[tuple[str, str], Finding] = {}

    # one finding per (object ref, code); later messages are appended, severity is the max
    def add(self, code: str, severity: str, ref: str, msg: str) -> None:
        key = (ref, code)
        order = {"minor": 0, "major": 1, "critical": 2}
        if key in self._pending:
            f = self._pending[key]
            f.message += "; " + msg
            if order[severity] > order[f.severity]:
                f.severity = severity
        else:
            self._pending[key] = Finding(self.slot, code, severity, ref, msg)

    def metric(self, name: str, ok: bool) -> None:
        m = self.res.metrics[name]
        m[0] += int(ok)
        m[1] += 1

    def run(self) -> None:
        gt, sub = self.gt, self.sub
        valid: list[Shape] = []
        file_ok = True
        for s in sub.shapes:
            usable, probs = _shape_problems(s)
            if probs:
                file_ok = False
                self.add("QC1-12", "minor", s.ref, ", ".join(probs))
            if usable:
                valid.append(s)
        for t in sub.tags:
            probs = _tag_problems(t)
            if probs and t.label != "camera":
                file_ok = False
                self.add("QC1-12", "minor", f"tag:{t.label}", ", ".join(probs))
        self.metric("file", file_ok)

        self._tags()
        by = defaultdict(list)
        for s in valid:
            by[s.label].append(s)
        gby = defaultdict(list)
        for s in gt.shapes:
            gby[s.label].append(s)

        self._lanes(gby["lane"], by["lane"])
        self._curbs(gby["road_curb"], by["road_curb"])
        self._drivable(gby["drivable"], by["drivable"])
        self._crosswalk(gby["crosswalk"], by["crosswalk"])
        self._boxes("traffic_light", gby["traffic_light"], by["traffic_light"])
        self._boxes("traffic_sign", gby["traffic_sign"], by["traffic_sign"])

        # checked units (GT side) per code
        c = self.res.checked
        lanes = gby["lane"]
        c["QC1-01"] += len(TAG_LABELS)
        c["QC1-02"] += sum(1 for g in lanes if g.attributes.get("position") in {"L1", "R1"})
        for code in ("QC1-03", "QC1-04", "QC1-05", "QC1-06"):
            c[code] += len(lanes)
        c["QC1-07"] += len(gby["drivable"]) + len(gby["crosswalk"]) + len(gby["road_curb"])
        c["QC1-08"] += len(gby["traffic_light"])
        c["QC1-09"] += len(gby["traffic_light"]) + len(gby["traffic_sign"])
        c["QC1-10"] += len(gby["traffic_sign"])
        if self.fisheye:
            c["QC1-11"] += len(gt.shapes)
        c["QC1-12"] += len(gt.shapes) + len(TAG_LABELS)
        self.res.total_checked += len(gt.shapes) + len(TAG_LABELS)
        self.res.findings.extend(self._pending.values())

    # ---------------------------------------------------------------- tags (QC1-01)
    def _tags(self) -> None:
        ok = True
        cam = self.sub.tag_value("camera")
        if cam is None:
            self.add("QC1-01", "critical", "tag:camera", f"thiếu tag camera (đúng là {self.camera})")
            ok = False
        elif cam != self.camera:
            self.add("QC1-01", "critical", "tag:camera", f"camera = {cam}, đúng là {self.camera}")
            ok = False
        for label in TAG_LABELS:
            if label != "camera" and self.sub.tag_value(label) is None:
                self.add("QC1-01", "minor", f"tag:{label}", f"thiếu tag {label}")
                ok = False
        self.metric("tags", ok)

    # ---------------------------------------------------------------- polylines
    def _pair(self, gts: list[Shape], subs: list[Shape]) -> tuple[dict[int, list[Shape]], list[Shape]]:
        groups: dict[int, list[Shape]] = defaultdict(list)
        unmatched: list[Shape] = []
        for s in subs:
            best = min(((geo.mean_distance(s.points, g.points), gi) for gi, g in enumerate(gts)), default=None)
            if best is not None and best[0] <= THRESHOLDS["lane_match_px"]:
                groups[best[1]].append(s)
            else:
                unmatched.append(s)
        return groups, unmatched

    @staticmethod
    def _merge(g: Shape, pieces: list[Shape]) -> list[tuple[float, float]]:
        pieces = sorted(pieces, key=lambda p: geo.closest_on_polyline(p.points[0], g.points)[1])
        pts: list[tuple[float, float]] = []
        for p in pieces:
            for q in p.points:
                if not pts or math.dist(pts[-1], q) > 1e-6:
                    pts.append(q)
        return pts

    def _lanes(self, gts: list[Shape], subs: list[Shape]) -> None:
        groups, unmatched = self._pair(gts, subs)
        side = self.camera in SIDE_CAMERAS
        for gi, g in enumerate(gts):
            gpos = g.attributes.get("position", "")
            pieces = groups.get(gi, [])
            setA = not self.fisheye
            if not pieces:
                if gpos in {"L1", "R1"}:
                    self.add("QC1-02", "critical", f"GT {g.ref}", f"thiếu vạch {gpos}")
                else:
                    self.add("QC1-04", "major", f"GT {g.ref}", f"thiếu vạch position={gpos}")
                if setA and gpos in {"L1", "R1"}:
                    self.metric("l1r1", False)
                if self.fisheye:
                    self.metric("arc", False)
                continue
            if setA and gpos in {"L1", "R1"}:
                self.metric("l1r1", True)
            ref = pieces[0].ref if len(pieces) == 1 else "+".join(p.ref for p in pieces)
            dir_ok = True
            if len(pieces) > 1:
                self.add("QC1-05", "major", ref, f"một vạch bị tách thành {len(pieces)} polyline (GT {g.ref})")
                dir_ok = False
            pts = self._merge(g, pieces)
            first = pieces[0]

            dev = geo.max_deviation(pts, g.points)
            dev_ok = dev <= THRESHOLDS["lane_dev_px"]
            if not dev_ok:
                code = "QC1-11" if self.fisheye else "QC1-04"
                self.add(code, "major", ref, f"lệch tối đa {dev:.1f} px so với tâm vạch (≤ {THRESHOLDS['lane_dev_px']:.0f})")
            if setA:
                self.metric("dev", dev_ok)
            else:
                self.metric("arc", dev_ok)

            s0 = geo.closest_on_polyline(pts[0], g.points)[1]
            s1 = geo.closest_on_polyline(pts[-1], g.points)[1]
            if s1 < s0:
                self.add("QC1-04", "major", ref, "vẽ ngược chiều (phải từ gần xe ra xa)")
                dir_ok = False
            else:
                d_near = math.dist(pts[0], g.points[0])
                d_far = math.dist(pts[-1], g.points[-1])
                if d_near > THRESHOLDS["lane_stop_px"]:
                    self.add("QC1-04", "major", ref, f"điểm đầu cách điểm GT gần xe {d_near:.0f} px")
                    dir_ok = False
                if d_far > THRESHOLDS["lane_stop_px"]:
                    self.add("QC1-04", "major", ref, f"điểm cuối cách điểm dừng GT {d_far:.0f} px")
                    dir_ok = False
            if any(p.occluded for p in pieces) != g.occluded:
                self.add("QC1-05", "major", ref, f"occluded phải là {'bật' if g.occluded else 'tắt'}")
                dir_ok = False
            if setA:
                self.metric("dir", dir_ok)

            spos = first.attributes.get("position", "")
            pos_ok = spos == gpos
            if not pos_ok:
                self.add("QC1-03", "critical", ref, f"position = {spos}, đúng là {gpos}")
            self.metric("pos", pos_ok)
            if side:
                self.metric("ferule", pos_ok)
            bad = [
                f"{a}={first.attributes.get(a, '')}→{g.attributes.get(a, '')}"
                for a in ("style", "color", "kind")
                if first.attributes.get(a, "") != g.attributes.get(a, "")
            ]
            if bad:
                self.add("QC1-06", "major", ref, "sai " + ", ".join(bad))
            self.metric("sck", not bad)
        for s in unmatched:
            self.add("QC1-03", "critical", s.ref, "lane không có trong GT (vạch thừa, vạch ô đỗ hoặc vạch ngựa vạn gán thành lane?)")

    def _curbs(self, gts: list[Shape], subs: list[Shape]) -> None:
        groups, unmatched = self._pair(gts, subs)
        for gi, g in enumerate(gts):
            pieces = groups.get(gi, [])
            if not pieces:
                self.add("QC1-07", "major", f"GT {g.ref}", "thiếu road_curb")
                if self.fisheye:
                    self.metric("arc", False)
                continue
            pts = self._merge(g, pieces)
            dev = geo.max_deviation(pts, g.points)
            ok = dev <= THRESHOLDS["curb_dev_px"]
            ref = "+".join(p.ref for p in pieces)
            if not ok:
                self.add("QC1-11" if self.fisheye else "QC1-07", "major", ref, f"road_curb lệch tối đa {dev:.1f} px")
            if self.fisheye:
                self.metric("arc", ok)
        for s in unmatched:
            self.add("QC1-07", "major", s.ref, "road_curb không có trong GT")

    # ---------------------------------------------------------------- polygons
    def _drivable(self, gts: list[Shape], subs: list[Shape]) -> None:
        for at in ("direct", "alternative"):
            g = [s.points for s in gts if s.attributes.get("area_type") == at]
            s = [x.points for x in subs if x.attributes.get("area_type") == at]
            if not g and not s:
                continue
            iou, spill = geo.polygon_iou_spill(g, s)
            ok = iou >= THRESHOLDS["drivable_iou"] and spill <= THRESHOLDS["drivable_spill"]
            if not ok:
                self.add("QC1-07", "major", f"drivable[{at}]", f"IoU {iou:.2f}, tràn {spill:.0%} ra ngoài GT")
            self.metric("spill", ok)
            if self.fisheye:
                self.metric("ferule", ok)
        for gshape in gts:
            best, best_area = None, 0.0
            for x in subs:
                _, _, inter = geo.union_overlap([gshape.points], [x.points], dy=2.0)
                if inter > best_area:
                    best, best_area = x, inter
            self.metric("atype", best is not None and best.attributes.get("area_type") == gshape.attributes.get("area_type"))

    def _crosswalk(self, gts: list[Shape], subs: list[Shape]) -> None:
        if not gts and not subs:
            return
        iou, _ = geo.polygon_iou_spill([s.points for s in gts], [s.points for s in subs])
        if iou < THRESHOLDS["crosswalk_iou"]:
            self.add("QC1-07", "major", "crosswalk", f"IoU vùng vạch ngựa vạn {iou:.2f} (< {THRESHOLDS['crosswalk_iou']})")

    # ---------------------------------------------------------------- boxes
    def _boxes(self, label: str, gts: list[Shape], subs: list[Shape]) -> None:
        pairs = sorted(
            ((geo.box_iou(g.points, s.points), gi, si) for gi, g in enumerate(gts) for si, s in enumerate(subs)),
            reverse=True,
        )
        gm: dict[int, tuple[int, float]] = {}
        used: set[int] = set()
        for iou, gi, si in pairs:
            if iou < THRESHOLDS["box_match_iou"]:
                break
            if gi in gm or si in used:
                continue
            gm[gi] = (si, iou)
            used.add(si)
        presence_code = "QC1-08" if label == "traffic_light" else "QC1-10"
        noun = "đèn" if label == "traffic_light" else "biển"
        attrs = ("color", "type", "facing") if label == "traffic_light" else ("group", "facing")
        for gi, g in enumerate(gts):
            required = geo.box_height(g.points) >= THRESHOLDS["min_box_px"]
            if gi not in gm:
                if required:
                    self.add(presence_code, "major", f"GT {g.ref}", f"thiếu {noun} (cao {geo.box_height(g.points):.0f} px)")
                    self.metric("presence", False)
                continue
            si, iou = gm[gi]
            s = subs[si]
            self.metric("presence", True)
            tight = iou >= THRESHOLDS["box_tight_iou"]
            self.metric("tight", tight)
            if not tight:
                self.add(presence_code, "major", s.ref, f"box chưa sát (IoU {iou:.2f} < {THRESHOLDS['box_tight_iou']})")
            attr_ok = True
            if label == "traffic_light" and s.attributes.get("color") != g.attributes.get("color"):
                sev = "critical" if g.attributes.get("facing") == "front" else "major"
                self.add("QC1-08", sev, s.ref, f"color = {s.attributes.get('color')}, đúng là {g.attributes.get('color')}")
                attr_ok = False
            other = [a for a in attrs if a != "color" and s.attributes.get(a) != g.attributes.get(a)]
            if other:
                self.add("QC1-09", "major", s.ref, ", ".join(f"{a} = {s.attributes.get(a)}→{g.attributes.get(a)}" for a in other))
                attr_ok = False
            self.metric("battr", attr_ok)
            ez_ok = _checkbox(s, "edge_zone") == _checkbox(g, "edge_zone")
            if not ez_ok:
                self.add("QC1-11", "major", s.ref, f"edge_zone phải là {'bật' if _checkbox(g, 'edge_zone') else 'tắt'}")
            if self.fisheye:
                self.metric("ferule", ez_ok)
        for si, s in enumerate(subs):
            if si not in used:
                self.add(presence_code, "major", s.ref, f"{noun} không có trong GT (hình in, phản chiếu, hoặc box lệch hẳn)")
                self.metric("presence", False)


# --------------------------------------------------------------------------- whole submission
def _label_count(im: Image) -> int:
    return len(im.shapes) + len(im.tags)


def _index(images: list[Image]) -> dict[str, Image]:
    """One image per slot. When a slot appears more than once (an image uploaded twice, or a
    project-level export that repeats images across subsets), keep the copy with the most labels;
    on a tie keep the first. ``duplicate_slots`` reports the repeats."""
    out: dict[str, Image] = {}
    for im in images:
        slot = image_slot(im.name)
        if slot and (slot not in out or _label_count(im) > _label_count(out[slot])):
            out[slot] = im
    return out


def duplicate_slots(images: list[Image]) -> dict[str, int]:
    n = Counter(image_slot(im.name) for im in images)
    return {slot: k for slot, k in sorted(n.items(), key=lambda t: str(t[0])) if slot and k > 1}


def _duplicate_message(k: int) -> str:
    return (f"ảnh xuất hiện {k} lần trong export (upload trùng, hoặc export cấp project?): "
            "chấm bản có nhiều nhãn nhất; xoá bản thừa rồi export lại từ task")


def check(gt_images: list[Image], sub_images: list[Image], name: str = "learner", file_errors: list[Finding] | None = None) -> Result:
    res = Result(name)
    gt = {k: v for k, v in _index(gt_images).items() if k in CORE_IMAGES}
    sub = _index(sub_images)
    for im in sub_images:
        slot = image_slot(im.name)
        if slot in EXTRA_IMAGES:
            res.extra_shapes[slot] = res.extra_shapes.get(slot, 0) + len(im.shapes)
        elif slot is None or slot not in gt:
            res.findings.append(Finding(im.name, "QC1-12", "minor", "file", "ảnh không thuộc lô 20 ảnh bắt buộc (tên file bị đổi?)"))
    for slot, k in duplicate_slots(sub_images).items():
        res.findings.append(Finding(slot, "QC1-12", "minor", "file", _duplicate_message(k)))
    for slot in sorted(gt):
        s = sub.get(slot)
        if s is None or (not s.shapes and not s.tags):
            res.missing.append(slot)
            continue
        res.attempted.append(slot)
        _ImageChecker(gt[slot], s, res).run()
    if file_errors:
        res.findings[:0] = file_errors
    _score(res, parse_failed=bool(file_errors))
    return res


def _score(res: Result, parse_failed: bool = False) -> None:
    res.rubric = []
    for rid, title, pts, auto in RUBRIC:
        if not auto:
            res.rubric.append({"id": rid, "title": title, "max": pts, "score": 0.0, "auto": False, "detail": "chấm tay"})
            continue
        ok, tot = res.metrics.get(rid, [0, 0]) if rid in res.metrics else (0, 0)
        if not res.attempted:
            score, detail = 0.0, "chưa làm ảnh bắt buộc nào"
        elif tot == 0:
            score, detail = float(pts), "không có mục để kiểm trên ảnh đã làm"
        else:
            score, detail = pts * ok / tot, f"{ok}/{tot}"
        if rid == "file" and parse_failed:
            score, detail = 0.0, "có file không mở được"
        res.rubric.append({"id": rid, "title": title, "max": pts, "score": round(score, 2), "auto": True, "detail": detail})


def load_many(paths: list[str]) -> tuple[list[Image], list[Finding]]:
    images: list[Image] = []
    errors: list[Finding] = []
    for p in paths:
        try:
            images.extend(load(p))
        except (CvatFormatError, OSError, ValueError) as exc:
            errors.append(Finding(Path(p).name, "QC1-12", "critical", "file", f"không mở được: {exc}"))
    return images, errors


# --------------------------------------------------------------------------- QC1 markdown
def qc1_markdown(res: Result, checker: str = "road_check (tự động)") -> str:
    by_code = Counter(f.code for f in res.findings)
    lines = [
        f"# Phiếu QC 1 — {GUIDELINE_VERSION} (phần tự động, road_check)",
        "",
        f"Lô được kiểm (học viên): {res.name}    Người kiểm: {checker}",
        f"Ngày: {date.today().isoformat()}    Phiên bản guideline: {GUIDELINE_VERSION}",
        f"Số ảnh kiểm: {len(res.attempted)} / {len(res.attempted) + len(res.missing)} ảnh bắt buộc"
        f" (+ {len(res.extra_shapes)} ảnh thêm, chỉ đếm số nhãn)    Số nhãn đã kiểm (shape + tag, theo GT): {res.total_checked}",
        "",
    ]
    if res.missing:
        lines += [f"Ảnh bắt buộc chưa làm (không tính vào tỉ lệ): {', '.join(res.missing)}", ""]
    lines += ["## Tổng hợp theo mã", "", "| Mã | Loại lỗi | Số mục kiểm | Số lỗi | Mức |", "| --- | --- | ---: | ---: | --- |"]
    for code, title in CODE_TITLES.items():
        lines.append(f"| {code} {title} | {CODE_KIND[code]} | {res.checked.get(code, 0)} | {by_code.get(code, 0)} | {CODE_LEVEL[code]} |")
    lines += ["", "## Danh sách lỗi (mỗi lỗi một dòng)", "", "| # | Mã | Ảnh | Nhãn (label, id) | Mức | Mô tả ngắn |", "| --- | --- | --- | --- | --- | --- |"]
    for i, f in enumerate(sorted(res.findings, key=lambda f: (f.image, f.code, f.ref)), 1):
        lines.append(f"| {i} | {f.code} | {f.image} | {f.ref} | {SEV_VI[f.severity]} | {f.message.replace('|', '/')} |")
    if not res.findings:
        lines.append("| | | | | | (không có lỗi) |")
    lines += [
        "",
        "## Ca mơ hồ",
        "",
        "| Ảnh | Câu hỏi cho lead | Lời đáp (nếu có) |",
        "| --- | --- | --- |",
        "| | (script không quyết định được Hold — coach điền nếu có) | |",
        "",
        "## Quyết định",
        "",
        f"Lỗi nặng: {res.count('critical')}    Lỗi chính: {res.count('major')} / {res.total_checked} nhãn = "
        f"{res.major_rate:.1%}    Lỗi nhẹ: {res.count('minor')}    Ca chờ lead: (coach điền)",
        "",
        f"Quyết định đề xuất của script (Release / Rework; Hold do người kiểm quyết): **{res.decision}**",
        "",
        "Lý do (theo luật của phiếu): "
        + (
            "có lỗi nặng → Rework."
            if res.count("critical")
            else f"tỉ lệ lỗi chính {res.major_rate:.1%} {'>' if res.major_rate > THRESHOLDS['major_rate'] else '≤'} 5 % → {res.decision}."
        ),
        "",
        "## Điểm phần tự động (rubric, chưa gồm phần chấm tay)",
        "",
        "| Tiêu chí | Điểm | Tối đa | Chi tiết |",
        "| --- | ---: | ---: | --- |",
    ]
    for r in res.rubric:
        score = f"{r['score']:.2f}" if r["auto"] else "—"
        lines.append(f"| {r['title']} | {score} | {r['max']} | {r['detail']} |")
    lines += [
        "",
        f"Tổng phần tự động: **{res.auto_score:.2f} / {AUTO_MAX}**. Còn chấm tay: ảnh chụp (2), Phiếu QC 1 cho bạn (15), "
        "báo cáo (5), điểm thưởng ảnh thêm (tối đa +4, tổng ≤ 100).",
        "",
    ]
    return "\n".join(lines)


def print_summary(res: Result, out=sys.stdout) -> None:
    print(f"== {res.name}: {len(res.attempted)} ảnh bắt buộc đã làm, thiếu {len(res.missing)} {res.missing or ''}", file=out)
    print(
        f"   lỗi nặng {res.count('critical')}, chính {res.count('major')} / {res.total_checked} nhãn "
        f"({res.major_rate:.1%}), nhẹ {res.count('minor')} → đề xuất {res.decision}",
        file=out,
    )
    print(f"   điểm tự động {res.auto_score:.2f} / {AUTO_MAX}", file=out)
    for f in sorted(res.findings, key=lambda f: (f.image, f.code, f.ref)):
        print(f"   [{f.code} {SEV_VI[f.severity]}] {f.image} {f.ref}: {f.message}", file=out)


# --------------------------------------------------------------------------- lint (no GT)
def lint(images: list[Image]) -> list[Finding]:
    out: list[Finding] = []

    def warn(img: Image, code: str, sev: str, ref: str, msg: str) -> None:
        out.append(Finding(image_slot(img.name) or img.name, code, sev, ref, msg))

    for slot, k in duplicate_slots(images).items():
        out.append(Finding(slot, "QC1-12", "minor", "file", _duplicate_message(k)))
    for img in images:
        for s in img.shapes:
            _, probs = _shape_problems(s)
            if probs:
                warn(img, "QC1-12", "minor", s.ref, ", ".join(probs))
            if s.kind in {"polyline", "polygon"}:
                dup = sum(1 for a, b in zip(s.points, s.points[1:]) if a == b)
                if dup:
                    warn(img, "QC1-12", "minor", s.ref, f"{dup} điểm lặp liền nhau (click hai lần?): xoá điểm thừa")
        for t in img.tags:
            for p in _tag_problems(t):
                warn(img, "QC1-12", "minor", f"tag:{t.label}", p)
        if not img.shapes and not img.tags:
            warn(img, "QC1-12", "minor", "image", "ảnh chưa có nhãn nào")
            continue
        exp = expected_camera(img.name)
        cam = img.tag_value("camera")
        if cam is None:
            warn(img, "QC1-01", "critical", "tag:camera", "thiếu tag camera")
        elif exp and cam != exp:
            warn(img, "QC1-01", "critical", "tag:camera", f"camera = {cam}, tên file gợi ý {exp}")
        for label in TAG_LABELS:
            if label != "camera" and img.tag_value(label) is None:
                warn(img, "QC1-01", "minor", f"tag:{label}", f"thiếu tag {label}")
        cam = cam or exp or "front"
        lanes = [s for s in img.shapes if s.label == "lane" and len(s.points) >= 2]
        pos = Counter(s.attributes.get("position") for s in lanes)
        if cam == "front":
            for p in ("L1", "R1"):
                if pos[p] == 0:
                    warn(img, "QC1-02", "critical", "lane", f"chưa có {p} (bỏ qua nếu thật sự không thấy vạch)")
            for s in lanes:
                if s.points[0][1] < s.points[-1][1]:
                    warn(img, "QC1-04", "major", s.ref, "điểm đầu cao hơn điểm cuối: có vẽ từ xa về gần không?")
        if cam in SIDE_CAMERAS:
            for s in lanes:
                if s.attributes.get("position") != "other":
                    warn(img, "QC1-03", "critical", s.ref, "camera hai bên: lane phải có position = other")
        for p, n in pos.items():
            if p in {"L1", "R1", "L2", "R2"} and n > 1:
                warn(img, "QC1-05", "major", "lane", f"{n} polyline cùng position {p}: vạch đứt có bị tách không?")
        if cam in FISHEYE_CAMERAS:
            for s in lanes + [x for x in img.shapes if x.label == "road_curb"]:
                if len(s.points) < 4:
                    warn(img, "QC1-11", "major", s.ref, f"chỉ {len(s.points)} điểm: trên fisheye hãy đặt điểm theo cung")
            r = THRESHOLDS["edge_zone_radius"] * img.width / 2
            cx, cy = img.width / 2, img.height / 2
            for s in img.shapes:
                if s.kind == "rectangle" and len(s.points) == 2:
                    x1, y1, x2, y2 = geo.box_norm(s.points)
                    far = math.hypot((x1 + x2) / 2 - cx, (y1 + y2) / 2 - cy) > r
                    if far != _checkbox(s, "edge_zone"):
                        warn(img, "QC1-11", "major", s.ref, f"gợi ý edge_zone = {'bật' if far else 'tắt'} (tâm box {'ngoài' if far else 'trong'} 80 % bán kính; tự kiểm lại)")
        for s in img.shapes:
            if s.kind == "rectangle" and len(s.points) == 2 and geo.box_height(s.points) < THRESHOLDS["min_box_px"]:
                warn(img, "QC1-08" if s.label == "traffic_light" else "QC1-10", "minor", s.ref, "box thấp hơn 8 px: không bắt buộc")
    return out


def label_counts(images: list[Image]) -> dict[str, Counter]:
    out: dict[str, Counter] = {}
    seen: Counter = Counter()
    for img in images:
        seen[img.name] += 1
        key = img.name if seen[img.name] == 1 else f"{img.name} (bản {seen[img.name]})"
        out[key] = Counter(s.label for s in img.shapes)
    return out


# --------------------------------------------------------------------------- self-test
def perturb(gt_images: list[Image]) -> tuple[list[Image], list[tuple[str, str]]]:
    """Apply the five mandatory perturbations. Returns (submission, [(slot, code)] expected once each)."""
    sub = [im.copy() for im in gt_images]
    front = [im for im in sub if (image_slot(im.name) or "").startswith("A") and image_slot(im.name) in CORE_IMAGES]
    if not front:
        raise ValueError("GT has no core front image (A01–A12)")
    expected: list[tuple[str, str]] = []
    used_lanes: set[tuple[str, int]] = set()

    def lanes(im: Image) -> list[Shape]:
        return [s for s in im.shapes if s.label == "lane"]

    def pick(pred, avoid_images=()):
        for im in front:
            if image_slot(im.name) in avoid_images:
                continue
            for s in lanes(im):
                if (im.name, s.index) not in used_lanes and pred(s):
                    used_lanes.add((im.name, s.index))
                    return im, s
        raise ValueError("GT has no lane suitable for this perturbation")

    # 1. camera tag on one image
    im = front[0]
    for t in im.tags:
        if t.label == "camera":
            t.attributes[TAG_ATTRIBUTE] = "fisheye_front"
    expected.append((image_slot(im.name), "QC1-01"))
    # 2. split a dashed lane (>= 3 points) into two at its middle vertex
    im2, s2 = pick(lambda s: s.attributes.get("style") == "dashed" and len(s.points) >= 3)
    m = len(s2.points) // 2
    second = s2.copy()
    second.points = s2.points[m:]
    second.index = max(x.index for x in im2.shapes) + 1
    s2.points = s2.points[: m + 1]
    im2.shapes.append(second)
    expected.append((image_slot(im2.name), "QC1-05"))
    # 3. reverse one polyline
    im3, s3 = pick(lambda s: len(s.points) >= 2)
    s3.points = list(reversed(s3.points))
    expected.append((image_slot(im3.name), "QC1-04"))
    # 4. shift another polyline by 12 px along its normal
    im4, s4 = pick(lambda s: geo.polyline_length(s.points) > 60)
    s4.points = geo.offset_along_normal(s4.points, 12.0)
    expected.append((image_slot(im4.name), "QC1-04"))
    # 5. change the colour of one facing=front light
    for im in front:
        lights = [s for s in im.shapes if s.label == "traffic_light" and s.attributes.get("facing") == "front"
                  and s.attributes.get("color") in {"red", "yellow", "green"}]
        if lights:
            l = lights[0]
            l.attributes["color"] = {"red": "green", "green": "red", "yellow": "red"}[l.attributes["color"]]
            expected.append((image_slot(im.name), "QC1-08"))
            break
    else:
        raise ValueError("GT has no facing=front light with color red/yellow/green on a core front image")
    return sub, expected


def selftest(gt_images: list[Image], out=sys.stdout) -> bool:
    ok = True
    res = check(gt_images, gt_images, "GT-vs-GT")
    clean = not res.findings and res.auto_score == AUTO_MAX and len(res.attempted) == len(_index(gt_images).keys() & CORE_IMAGES)
    print(f"[{'PASS' if clean else 'FAIL'}] GT làm bài nộp: {len(res.findings)} lỗi, điểm tự động {res.auto_score}/{AUTO_MAX}", file=out)
    if not clean:
        print_summary(res, out)
        ok = False
    sub, expected = perturb(gt_images)
    res2 = check(gt_images, sub, "perturbed")
    got = Counter((f.image, f.code) for f in res2.findings)
    want = Counter(expected)
    exact = got == want
    for key in sorted(want):
        print(f"[{'PASS' if got.get(key, 0) == want[key] else 'FAIL'}] {key[1]} ở {key[0]}: mong {want[key]}, thấy {got.get(key, 0)}", file=out)
    for key in sorted(set(got) - set(want)):
        print(f"[FAIL] lỗi ngoài dự kiến {key[1]} ở {key[0]} ×{got[key]}", file=out)
    crit = [f for f in res2.findings if f.code == "QC1-08"]
    if not crit or crit[0].severity != "critical":
        print("[FAIL] sai màu đèn facing=front phải là lỗi nặng", file=out)
        exact = False
    if not exact:
        print_summary(res2, out)
    print(f"[{'PASS' if exact else 'FAIL'}] bản làm nhiễu: {len(res2.findings)} lỗi, mong đúng {len(expected)}", file=out)
    return ok and exact


# --------------------------------------------------------------------------- delivery manifest
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def _file_entry(path: Path) -> dict:
    data = path.read_bytes()
    entry: dict = {"file": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            entry["contains_images"] = any(n.lower().endswith(IMAGE_SUFFIXES) for n in zf.namelist())
    else:
        entry["contains_images"] = False
    try:
        images = load(path)
    except (CvatFormatError, OSError, ValueError) as exc:
        entry["error"] = str(exc)
        return entry
    shapes = Counter(s.label for im in images for s in im.shapes)
    entry |= {
        "images": len(images),
        "images_unlabelled": sum(1 for im in images if not im.shapes and not im.tags),
        "images_all_tags": sum(1 for im in images if all(im.tag_value(t) is not None for t in TAG_LABELS)),
        "shapes_by_label": dict(sorted(shapes.items())),
    }
    return entry


def delivery_manifest(paths: list[str], findings: list[Finding], name: str, revision: int) -> dict:
    """Describe one delivery: what was sent, its checksums, and the lint result at send time."""
    sev = Counter(f.severity for f in findings)
    return {
        "manifest": "road-delivery/1",
        "format": "CVAT for images 1.1",
        "guideline": GUIDELINE_VERSION,
        "name": name,
        "revision": revision,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [_file_entry(Path(p)) for p in paths],
        "lint": {SEV_VI[k]: sev.get(k, 0) for k in ("critical", "major", "minor")},
        "note": "Tạo bởi road_check lint. Mô tả file đã gửi, không phải kết luận chất lượng.",
    }


# --------------------------------------------------------------------------- CLI
def _write_outputs(res: Result, json_path: str | None, md_path: str | None) -> None:
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if md_path:
        Path(md_path).parent.mkdir(parents=True, exist_ok=True)
        Path(md_path).write_text(qc1_markdown(res), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="road_check", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("lint", help="tự kiểm file export (không cần GT)")
    p.add_argument("files", nargs="+")
    p.add_argument("--manifest", help="ghi manifest bàn giao (JSON) vào đường dẫn này")
    p.add_argument("--name", default="learner", help="tên người nộp ghi trong manifest")
    p.add_argument("--revision", type=int, default=1, help="lần nộp: 1 là lần đầu, 2 là sau Rework")
    p = sp.add_parser("check", help="so một học viên với GT")
    p.add_argument("--gt", nargs="+", required=True)
    p.add_argument("--sub", nargs="+", required=True)
    p.add_argument("--name", default="learner")
    p.add_argument("--json")
    p.add_argument("--qc1-md")
    p = sp.add_parser("selftest", help="self-test bắt buộc của checker")
    p.add_argument("--gt", nargs="*")
    p = sp.add_parser("batch", help="chấm mọi <tên>-front.zip / <tên>-fisheye.zip trong một thư mục")
    p.add_argument("--gt", nargs="+", required=True)
    p.add_argument("--submissions", required=True)
    p.add_argument("--out", default="out")
    a = ap.parse_args(argv)

    if a.cmd == "lint":
        images, errors = load_many(a.files)
        findings = errors + lint(images)
        for name, cnt in label_counts(images).items():
            print(f"{name}: " + (", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) or "chưa có shape"))
        print()
        for f in findings:
            print(f"[{f.code} {SEV_VI[f.severity]}] {f.image} {f.ref}: {f.message}")
        print(f"\n{len(images)} ảnh, {len(findings)} cảnh báo. Lint chỉ là gợi ý; GT và người kiểm mới quyết định lỗi.")
        if a.manifest:
            if a.revision < 1:
                print("--revision phải từ 1 trở lên", file=sys.stderr)
                return 2
            if errors:
                print("Không tạo manifest: còn file không mở được. Sửa file rồi chạy lại.", file=sys.stderr)
                return 1
            dest = Path(a.manifest)
            if dest.exists() and any(dest.samefile(f) for f in a.files):
                print("--manifest trùng với một file nhãn; chọn tên khác (ví dụ <tên>-manifest.json)", file=sys.stderr)
                return 2
            m = delivery_manifest(a.files, findings, a.name, a.revision)
            Path(a.manifest).parent.mkdir(parents=True, exist_ok=True)
            Path(a.manifest).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Manifest bàn giao → {a.manifest}")
            if any(f.get("contains_images") for f in m["files"]):
                print("Cảnh báo: zip có kèm ảnh. Export lại, bỏ chọn Save images.")
        return 1 if errors else 0

    if a.cmd == "check":
        gt, gt_err = load_many(a.gt)
        if gt_err:
            print(f"GT không mở được: {gt_err[0].message}", file=sys.stderr)
            return 2
        sub, sub_err = load_many(a.sub)
        res = check(gt, sub, a.name, sub_err)
        print_summary(res)
        _write_outputs(res, a.json, a.qc1_md)
        return 0

    if a.cmd == "selftest":
        if a.gt:
            gt, gt_err = load_many(a.gt)
            if gt_err:
                print(f"GT không mở được: {gt_err[0].message}", file=sys.stderr)
                return 2
            print(f"Self-test trên GT của coach ({len(gt)} ảnh)")
        else:
            from .synthetic import synthetic_gt

            gt = synthetic_gt()
            print("Self-test trên GT tổng hợp (không cần dữ liệu)")
        try:
            passed = selftest(gt)
        except ValueError as exc:
            print(f"[FAIL] không dựng được bản làm nhiễu: {exc}")
            return 1
        print("SELFTEST PASS" if passed else "SELFTEST FAIL")
        return 0 if passed else 1

    if a.cmd == "batch":
        gt, gt_err = load_many(a.gt)
        if gt_err:
            print(f"GT không mở được: {gt_err[0].message}", file=sys.stderr)
            return 2
        root = Path(a.submissions)
        names = sorted({p.name.rsplit("-", 1)[0] for p in root.glob("*-front.zip")} | {p.name.rsplit("-", 1)[0] for p in root.glob("*-fisheye.zip")})
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for n in names:
            files = [str(p) for p in (root / f"{n}-front.zip", root / f"{n}-fisheye.zip") if p.exists()]
            sub, sub_err = load_many(files)
            if len(files) < 2:
                sub_err.append(Finding(n, "QC1-12", "critical", "file", "thiếu một trong hai file zip"))
            res = check(gt, sub, n, sub_err)
            _write_outputs(res, str(out / f"{n}.json"), str(out / f"{n}-auto-qc1.md"))
            d = res.to_dict()
            rows.append({k: d[k] for k in ("name", "checked_labels", "critical", "major", "minor", "major_rate", "decision_auto", "auto_score", "auto_max")}
                        | {"attempted_core": len(res.attempted), "extra_images": len(res.extra_shapes)})
            print_summary(res)
        if rows:
            with open(out / "scores.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        print(f"\n{len(rows)} học viên → {out}/scores.csv")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
