"""bdd_to_cvat_road: convert BDD100K labels of the picked Set A images into a CVAT for images 1.1 draft GT.

    python -m road_lab.bdd_to_cvat_road --labels LABEL.json [...] --manifest manifests/manifest_front.csv \
        --out coach_gt/road_gt_front_draft.xml [--core-only]

What is converted (taxonomy Road v1.0):
  * lane (parallel only; vertical stop lines are skipped) -> polyline ``lane``; Bezier curves are
    sampled into points; style from laneStyle; color/kind from the lane class
    (single/double white/yellow/other). ``position`` is NOT in BDD100K: left empty for the coach.
  * road curb -> polyline ``road_curb``; crosswalk -> polygon ``crosswalk`` (convex hull of all
    crosswalk strokes in the image, guide: one polygon around the stripes).
  * drivable direct/alternative -> polygon ``drivable`` with area_type.
  * traffic light / sign boxes from 8 px tall -> ``traffic_light`` / ``traffic_sign``; light color
    from trafficLightColor (none -> off is NOT assumed: left empty); type, facing, group left empty.
  * tags: camera=front, timeofday (daytime->day, dawn/dusk->dusk, night->night), weather
    (clear/partly cloudy->clear, overcast->overcast, rainy->rain, foggy->fog, else other), source=real.

Image names become ``{slot}_{bdd name}`` to match the class image pack. Every empty attribute is
listed in ``<out>_todo.csv``; the draft is not GT until the coach has filled and reviewed it.
BDD100K lane polylines follow the paint edge/centre as their annotators drew them, and their
direction is not guaranteed near-to-far: the converter orients each lane bottom-to-top, but the
coach still checks every line against guideline Road v1.0.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import geometry as geo
from .bdd import Frame, box, classify, load_frames, polys
from .cvat_xml import Image, Shape, Tag, write
from .taxonomy import CORE_FRONT, TAG_ATTRIBUTE

TIMEOFDAY = {"daytime": "day", "dawn/dusk": "dusk", "night": "night"}
WEATHER = {"clear": "clear", "partly cloudy": "clear", "overcast": "overcast", "rainy": "rain", "foggy": "fog"}
LIGHT_COLOR = {"red": "red", "yellow": "yellow", "green": "green"}
MIN_BOX_PX = 8.0
BDD_W, BDD_H = 1280, 720


def _lane_attrs(sub: str, style: str) -> dict[str, str]:
    kind, _, colour = sub.partition(" ")
    return {
        "position": "",
        "style": style if style in {"solid", "dashed"} else "",
        "color": colour if colour in {"white", "yellow"} else "other",
        "kind": kind if kind in {"single", "double"} else "",
    }


def _near_to_far(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return pts if pts[0][1] >= pts[-1][1] else list(reversed(pts))


def convert_frame(fr: Frame, slot: str) -> tuple[Image, list[dict]]:
    img = Image(f"{slot}_{fr.name}", BDD_W, BDD_H)
    img.tags = [
        Tag("camera", {TAG_ATTRIBUTE: "front"}),
        Tag("timeofday", {TAG_ATTRIBUTE: TIMEOFDAY.get(fr.timeofday, "")}),
        Tag("weather", {TAG_ATTRIBUTE: WEATHER.get(fr.weather, "other")}),
        Tag("source", {TAG_ATTRIBUTE: "real"}),
    ]
    crosswalk_pts: list[tuple[float, float]] = []
    for lb in fr.labels:
        kind, sub = classify(lb)
        attrs = lb.get("attributes") or {}
        occl = bool(attrs.get("occluded", False))
        if kind == "lane":
            if str(attrs.get("laneDirection", "parallel")) == "vertical":
                continue
            for v, t, _ in polys(lb):
                pts = _near_to_far(geo.sample_bezier(v, t))
                if len(pts) >= 2:
                    img.shapes.append(Shape("lane", "polyline", pts, _lane_attrs(sub, str(attrs.get("laneStyle", ""))), occl))
        elif kind == "road_curb":
            for v, t, _ in polys(lb):
                pts = _near_to_far(geo.sample_bezier(v, t))
                if len(pts) >= 2:
                    img.shapes.append(Shape("road_curb", "polyline", pts, {}, occl))
        elif kind == "crosswalk":
            for v, t, _ in polys(lb):
                crosswalk_pts.extend(geo.sample_bezier(v, t))
        elif kind == "drivable":
            for v, t, _ in polys(lb):
                pts = geo.sample_bezier(v, t)
                if len(pts) >= 3:
                    img.shapes.append(Shape("drivable", "polygon", pts, {"area_type": sub}))
        elif kind in {"traffic_light", "traffic_sign"}:
            b = box(lb)
            if b is None or (b[3] - b[1]) < MIN_BOX_PX:
                continue
            pts = [(b[0], b[1]), (b[2], b[3])]
            if kind == "traffic_light":
                a = {"color": LIGHT_COLOR.get(sub, ""), "type": "", "facing": "", "edge_zone": "false"}
            else:
                a = {"group": "", "facing": "", "edge_zone": "false"}
            img.shapes.append(Shape(kind, "rectangle", pts, a, occl))
    if len(crosswalk_pts) >= 3:
        img.shapes.append(Shape("crosswalk", "polygon", geo.convex_hull(crosswalk_pts), {}))
    todo = []
    for k, s in enumerate(img.shapes):
        s.index = k
        for attr, val in s.attributes.items():
            if val == "":
                todo.append({"image": img.name, "ref": s.ref, "attribute": attr, "note": "BDD100K không có; coach điền theo Road v1.0"})
    for t in img.tags:
        if t.attributes.get(TAG_ATTRIBUTE, "") == "":
            todo.append({"image": img.name, "ref": f"tag:{t.label}", "attribute": TAG_ATTRIBUTE, "note": "giá trị BDD100K không ánh xạ được"})
    return img, todo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdd_to_cvat_road", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True, help=".xml or .zip (CVAT for images 1.1)")
    ap.add_argument("--core-only", action="store_true", help="chỉ A01-A12 (GT đầy đủ chỉ cần ảnh bắt buộc)")
    a = ap.parse_args(argv)

    frames = load_frames(a.labels)
    with open(a.manifest, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("file")]
    if a.core_only:
        rows = [r for r in rows if r["slot"] in CORE_FRONT]
    images, todo, missing = [], [], []
    for r in rows:
        fr = frames.get(r["file"])
        if fr is None:
            missing.append(r["file"])
            continue
        img, t = convert_frame(fr, r["slot"])
        images.append(img)
        todo.extend(t)
    if not images:
        print("Không có ảnh nào trong manifest khớp file nhãn.", file=sys.stderr)
        return 2
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    write(images, a.out, comment="DRAFT from BDD100K (c) 2018 The Regents of the University of California, BDD100K License. Not GT until reviewed by the coach under Road v1.0.")
    todo_path = Path(a.out).with_suffix("").as_posix() + "_todo.csv"
    with open(todo_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["image", "ref", "attribute", "note"])
        w.writeheader()
        w.writerows(todo)
    print(f"{len(images)} ảnh → {a.out}; {len(todo)} thuộc tính cần coach điền → {todo_path}")
    if missing:
        print("Không thấy nhãn cho: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
