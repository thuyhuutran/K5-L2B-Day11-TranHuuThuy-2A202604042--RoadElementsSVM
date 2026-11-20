"""select_bdd_road: shortlist BDD100K val images for the 16 Set A slots (A01-A12 core, A13-A16 extra).

    python -m road_lab.select_bdd_road --labels LABEL.json [LABEL.json ...] \
        --out manifests/manifest_front.csv --candidates out/candidates_front.csv [--top 8] [--seed 11]

Reads BDD100K label JSON only (no images needed). Each slot has a focus rule computed from the
labels (lane count, dashed/double/occluded lanes, drivable type, curb, crosswalk, lights, signs,
time of day, weather). The script writes the top candidates per slot and fills a manifest with the
first unused candidate. It cannot judge blur, faded paint or a supplementary sign from labels:
those columns say "coach kiểm tay" and the coach must open every picked image before the class.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

from . import geometry as geo
from .bdd import Frame, box, classify, load_frames, polys

MIN_BOX_PX = 8.0


def features(fr: Frame) -> dict:
    f = {
        "lanes": 0, "dashed": 0, "long_dashed": 0, "occluded_lane": 0, "double_yellow": 0, "vertical": 0,
        "curb": 0, "crosswalk": 0, "direct": 0, "alternative": 0, "lights": 0, "lights_front_small": 0,
        "signs": 0, "small_signs": 0,
    }
    for lb in fr.labels:
        kind, sub = classify(lb)
        attrs = lb.get("attributes") or {}
        if kind == "lane":
            if str(attrs.get("laneDirection", "parallel")) == "vertical":
                f["vertical"] += 1
                continue
            f["lanes"] += 1
            if str(attrs.get("laneStyle", "solid")) == "dashed":
                f["dashed"] += 1
                length = max((geo.polyline_length(geo.sample_bezier(v, t)) for v, t, _ in polys(lb)), default=0.0)
                if length >= 300:
                    f["long_dashed"] += 1
            if attrs.get("occluded"):
                f["occluded_lane"] += 1
            if sub == "double yellow":
                f["double_yellow"] += 1
        elif kind == "road_curb":
            f["curb"] += 1
        elif kind == "crosswalk":
            f["crosswalk"] += 1
        elif kind == "drivable":
            f[sub] += 1
        elif kind in {"traffic_light", "traffic_sign"}:
            b = box(lb)
            if b is None or (b[3] - b[1]) < MIN_BOX_PX:
                continue
            if kind == "traffic_light":
                f["lights"] += 1
            else:
                f["signs"] += 1
                if (b[3] - b[1]) < 20:
                    f["small_signs"] += 1
    return f


def _day(fr: Frame) -> bool:
    return fr.timeofday == "daytime"


def _clear(fr: Frame) -> bool:
    return fr.weather in {"clear", "partly cloudy", "overcast"}


# slot -> (tier, focus text, rule(frame, feats) -> score or None)
SLOTS: dict[str, tuple[str, str, object]] = {
    "A01": ("core", "3+ vạch làn", lambda fr, f: f["lanes"] if f["lanes"] >= 3 and _day(fr) and _clear(fr) else None),
    "A02": ("core", "vạch đứt dài", lambda fr, f: f["long_dashed"] * 2 + f["lanes"] if f["long_dashed"] and _day(fr) else None),
    "A03": ("core", "làn bị che", lambda fr, f: f["occluded_lane"] * 2 + f["lanes"] if f["occluded_lane"] and _day(fr) else None),
    "A04": ("core", "vàng đôi + direct/alternative", lambda fr, f: 3 + f["lanes"] if f["double_yellow"] and f["direct"] and f["alternative"] and _day(fr) else None),
    "A05": ("core", "vùng lái + mép lề", lambda fr, f: f["curb"] + f["direct"] if f["curb"] and f["direct"] and _day(fr) else None),
    "A06": ("core", "vạch qua đường", lambda fr, f: f["crosswalk"] + f["lanes"] if f["crosswalk"] and _day(fr) else None),
    "A07": ("core", "đèn giao thông", lambda fr, f: 5 - min(4, abs(f["lights"] - 2)) if 1 <= f["lights"] <= 3 and _day(fr) else None),
    "A08": ("core", "nhiều cụm đèn", lambda fr, f: f["lights"] if f["lights"] >= 4 and _day(fr) else None),
    "A09": ("core", "biển báo", lambda fr, f: f["signs"] if 2 <= f["signs"] <= 6 and _day(fr) else None),
    "A10": ("core", "biển phụ (coach kiểm tay)", lambda fr, f: f["small_signs"] * 2 + f["signs"] if f["signs"] >= 2 and f["small_signs"] and _day(fr) else None),
    "A11": ("core", "hoàng hôn, đủ loại nhãn", lambda fr, f: f["lanes"] + f["lights"] + f["signs"] if fr.timeofday == "dawn/dusk" and f["lanes"] >= 2 and f["lights"] and f["signs"] else None),
    "A12": ("core", "phố đông, đủ loại nhãn", lambda fr, f: f["lanes"] + f["lights"] + f["signs"] + f["crosswalk"] if fr.scene == "city street" and _day(fr) and f["lanes"] >= 2 and f["direct"] and f["lights"] and f["signs"] and f["crosswalk"] else None),
    "A13": ("extra", "mưa", lambda fr, f: f["lanes"] + f["direct"] if fr.weather == "rainy" and f["lanes"] >= 2 else None),
    "A14": ("extra", "đêm", lambda fr, f: f["lanes"] + f["lights"] if fr.timeofday == "night" and f["lanes"] >= 2 else None),
    "A15": ("extra", "vạch mờ (coach kiểm tay)", lambda fr, f: f["lanes"] if fr.weather in {"overcast", "foggy"} and f["lanes"] >= 2 else None),
    "A16": ("extra", "giao lộ phức tạp", lambda fr, f: f["crosswalk"] + f["vertical"] + f["lights"] if f["crosswalk"] and f["vertical"] and f["lights"] >= 2 else None),
}

MANIFEST_COLUMNS = ["slot", "file", "split", "weather", "scene", "timeofday", "tier", "focus", "reason", "blur_note"]


def shortlist(frames: dict[str, Frame], top: int, seed: int) -> dict[str, list[tuple[float, Frame, dict]]]:
    rng = random.Random(seed)
    names = sorted(frames)
    rng.shuffle(names)  # tie-break among equal scores is deterministic but not alphabetical
    feats = {n: features(frames[n]) for n in names}
    out: dict[str, list[tuple[float, Frame, dict]]] = {}
    for slot, (_, _, rule) in SLOTS.items():
        scored = []
        for order, n in enumerate(names):
            s = rule(frames[n], feats[n])
            if s is not None:
                scored.append((float(s), -order, frames[n], feats[n]))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out[slot] = [(s, fr, f) for s, _, fr, f in scored[:top]]
    return out


def _reason(f: dict) -> str:
    keys = [k for k in ("lanes", "dashed", "occluded_lane", "double_yellow", "curb", "crosswalk", "direct", "alternative", "lights", "signs") if f[k]]
    return "; ".join(f"{k}={f[k]}" for k in keys)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="select_bdd_road", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", nargs="+", required=True, help="BDD100K val label JSON (lane, drivable, det)")
    ap.add_argument("--out", required=True, help="manifest_front.csv")
    ap.add_argument("--candidates", required=True, help="candidates CSV (top-N per slot)")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--split", default="val")
    a = ap.parse_args(argv)

    frames = load_frames(a.labels)
    if not frames:
        print("Không đọc được frame nào từ file nhãn.", file=sys.stderr)
        return 2
    sl = shortlist(frames, a.top, a.seed)

    Path(a.candidates).parent.mkdir(parents=True, exist_ok=True)
    with open(a.candidates, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["slot", "rank", "file", "score", "timeofday", "weather", "scene", "reason"])
        for slot, rows in sl.items():
            for r, (s, fr, f) in enumerate(rows, 1):
                w.writerow([slot, r, fr.name, s, fr.timeofday, fr.weather, fr.scene, _reason(f)])

    used: set[str] = set()
    manifest, empty = [], []
    for slot, (tier, focus, _) in SLOTS.items():
        pick = next(((s, fr, f) for s, fr, f in sl[slot] if fr.name not in used), None)
        if pick is None:
            empty.append(slot)
            manifest.append({"slot": slot, "file": "", "split": a.split, "weather": "", "scene": "", "timeofday": "",
                             "tier": tier, "focus": focus, "reason": "KHÔNG có ứng viên: coach chọn tay", "blur_note": ""})
            continue
        _, fr, f = pick
        used.add(fr.name)
        manifest.append({"slot": slot, "file": fr.name, "split": a.split, "weather": fr.weather, "scene": fr.scene,
                         "timeofday": fr.timeofday, "tier": tier, "focus": focus, "reason": _reason(f),
                         "blur_note": "coach kiểm tay"})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(manifest)
    print(f"{len(frames)} frame; manifest {a.out} ({16 - len(empty)}/16 slot có ảnh); ứng viên {a.candidates}")
    if empty:
        print("Slot chưa có ứng viên: " + ", ".join(empty))
    print("Bước tiếp: mở từng ảnh đã chọn, kiểm trọng tâm, độ mờ, biển phụ; sửa cột file nếu cần.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
