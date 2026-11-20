"""Read BDD100K scalabel-style label JSON (lane, drivable, detection) into one frame index.

Handles both layouts seen in the BDD100K releases:
  * the combined 2018 file (``bdd100k_labels_images_val.json``): categories ``lane``,
    ``drivable area``, ``traffic light``, ``traffic sign``; lane class in ``attributes.laneType``,
    drivable class in ``attributes.areaType``;
  * the per-task files (``lane/polygons``, ``drivable/polygons``, ``det_20``): lane classes as the
    category (``single white``, ``road curb``, ``crosswalk``...), drivable as ``direct``/``alternative``.

Format reference: https://doc.bdd100k.com/format.html (attributes laneDirection, laneStyle,
areaType, trafficLightColor; poly2d = vertices + types, 'C' = cubic Bezier control point).
Files are read as data only; nothing in them is executed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LANE_CLASSES = {
    "crosswalk", "double other", "double white", "double yellow", "road curb",
    "single other", "single white", "single yellow",
}
DRIVABLE_CLASSES = {"direct", "alternative"}


@dataclass
class Frame:
    name: str
    attributes: dict = field(default_factory=dict)
    labels: list[dict] = field(default_factory=list)

    @property
    def timeofday(self) -> str:
        return str(self.attributes.get("timeofday", "undefined"))

    @property
    def weather(self) -> str:
        return str(self.attributes.get("weather", "undefined"))

    @property
    def scene(self) -> str:
        return str(self.attributes.get("scene", "undefined"))


def _frames_from_json(data) -> list[dict]:
    if isinstance(data, dict):
        return data.get("frames") or data.get("images") or []
    return data if isinstance(data, list) else []


def load_frames(paths: list[str | Path]) -> dict[str, Frame]:
    """Merge every label file into {image name: Frame}; later files add labels, never replace."""
    out: dict[str, Frame] = {}
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for fr in _frames_from_json(data):
            name = fr.get("name") or fr.get("videoName")
            if not name:
                continue
            f = out.setdefault(name, Frame(name))
            for k, v in (fr.get("attributes") or {}).items():
                f.attributes.setdefault(k, v)
            f.labels.extend(fr.get("labels") or [])
    return out


def classify(label: dict) -> tuple[str, str]:
    """(kind, sub-class) with kind in lane | road_curb | crosswalk | drivable | traffic_light | traffic_sign | other."""
    cat = str(label.get("category", "")).strip().lower()
    attrs = label.get("attributes") or {}
    if cat.startswith("lane/"):
        cat = cat[5:]
    if cat.startswith("area/"):
        cat = {"drivable": "direct"}.get(cat[5:], cat[5:])
    if cat == "lane":
        cat = str(attrs.get("laneType", "single other")).lower()
    if cat == "drivable area":
        cat = str(attrs.get("areaType", "direct")).lower()
    if cat in LANE_CLASSES:
        if cat == "road curb":
            return "road_curb", cat
        if cat == "crosswalk":
            return "crosswalk", cat
        return "lane", cat
    if cat in DRIVABLE_CLASSES:
        return "drivable", cat
    if cat in {"traffic light", "traffic_light"}:
        return "traffic_light", str(attrs.get("trafficLightColor", "none")).lower()
    if cat in {"traffic sign", "traffic_sign"}:
        return "traffic_sign", ""
    return "other", cat


def polys(label: dict) -> list[tuple[list[tuple[float, float]], str, bool]]:
    """[(vertices, types, closed)] of a label's poly2d entries."""
    out = []
    for p in label.get("poly2d") or []:
        verts = [(float(x), float(y)) for x, y in p.get("vertices", [])]
        if verts:
            out.append((verts, str(p.get("types", "L" * len(verts))), bool(p.get("closed", False))))
    return out


def box(label: dict) -> tuple[float, float, float, float] | None:
    b = label.get("box2d")
    if not b:
        return None
    return float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])
