"""Guideline Road v1.0 taxonomy: the single source of truth for labels, attributes and tags.

`configs/road_v1_labels.json` (CVAT "Raw" labels) is generated from this module:

    python -m road_lab.taxonomy > configs/road_v1_labels.json

A test checks that the committed JSON still matches this module.
"""
from __future__ import annotations

import json
import re
import sys

GUIDELINE_VERSION = "Road v1.0"

# label -> (CVAT shape type, {attribute: [values]}, checkbox attributes)
SHAPE_LABELS: dict[str, dict] = {
    "lane": {
        "type": "polyline",
        "color": "#ffd400",
        "select": {
            "position": ["L1", "R1", "L2", "R2", "other"],
            "style": ["solid", "dashed"],
            "color": ["white", "yellow", "other"],
            "kind": ["single", "double"],
        },
        "checkbox": [],
    },
    "road_curb": {"type": "polyline", "color": "#ff7f0e", "select": {}, "checkbox": []},
    "crosswalk": {"type": "polygon", "color": "#e377c2", "select": {}, "checkbox": []},
    "drivable": {
        "type": "polygon",
        "color": "#2ca02c",
        "select": {"area_type": ["direct", "alternative"]},
        "checkbox": [],
    },
    "traffic_light": {
        "type": "rectangle",
        "color": "#d62728",
        "select": {
            "color": ["red", "yellow", "green", "off", "unknown"],
            "type": ["vehicle", "pedestrian", "beacon"],
            "facing": ["front", "side", "back"],
        },
        "checkbox": ["edge_zone"],
    },
    "traffic_sign": {
        "type": "rectangle",
        "color": "#1f77b4",
        "select": {
            "group": ["prohibitory", "mandatory", "warning", "information", "supplementary", "other"],
            "facing": ["front", "side", "back"],
        },
        "checkbox": ["edge_zone"],
    },
}

# Image tags are modelled as four Tag labels, each with ONE select attribute named "value".
# (Lab Coach design decision recorded in lab/AGENTS.md.)
TAG_ATTRIBUTE = "value"
TAG_LABELS: dict[str, list[str]] = {
    "camera": ["front", "fisheye_front", "fisheye_rear", "fisheye_left", "fisheye_right"],
    "timeofday": ["day", "dusk", "night"],
    "weather": ["clear", "overcast", "rain", "fog", "other"],
    "source": ["real", "simulated"],
}
TAG_COLORS = {"camera": "#7f7f7f", "timeofday": "#bcbd22", "weather": "#17becf", "source": "#8c564b"}

FISHEYE_CAMERAS = {"fisheye_front", "fisheye_rear", "fisheye_left", "fisheye_right"}
SIDE_CAMERAS = {"fisheye_left", "fisheye_right"}

# File-name convention of the class image pack: A01..A16 front, B01..B12 fisheye.
CORE_FRONT = [f"A{i:02d}" for i in range(1, 13)]
EXTRA_FRONT = [f"A{i:02d}" for i in range(13, 17)]
CORE_FISHEYE = [f"B{i:02d}" for i in range(1, 9)]
EXTRA_FISHEYE = [f"B{i:02d}" for i in range(9, 13)]
CORE_IMAGES = set(CORE_FRONT + CORE_FISHEYE)
EXTRA_IMAGES = set(EXTRA_FRONT + EXTRA_FISHEYE)

# WoodScape file suffix -> camera tag value
WOODSCAPE_SUFFIX_TO_CAMERA = {
    "FV": "fisheye_front",
    "RV": "fisheye_rear",
    "MVL": "fisheye_left",
    "MVR": "fisheye_right",
}

_SLOT_RE = re.compile(r"(?<![A-Za-z0-9])([AB])(\d{2})(?!\d)")


def image_slot(name: str) -> str | None:
    """Return the A01..B12 slot of an image name, e.g. 'A03_b1c66a42-6f7d68ca.jpg' -> 'A03'."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    m = _SLOT_RE.search(base)
    return f"{m.group(1)}{m.group(2)}" if m else None


def expected_camera(name: str) -> str | None:
    """Camera implied by the file name: A-slots are front; B-slots use the WoodScape suffix."""
    slot = image_slot(name)
    if slot is None:
        return None
    if slot.startswith("A"):
        return "front"
    base = name.rsplit("/", 1)[-1]
    for suffix, cam in WOODSCAPE_SUFFIX_TO_CAMERA.items():
        if re.search(rf"_{suffix}(?:\.|_|$)", base):
            return cam
    return None


def raw_labels() -> list[dict]:
    """CVAT 'Raw' labels JSON (Project -> Labels -> Raw)."""
    out: list[dict] = []
    for name, spec in SHAPE_LABELS.items():
        attrs = [
            {
                "name": a,
                "mutable": False,
                "input_type": "select",
                "default_value": vals[0],
                "values": list(vals),
            }
            for a, vals in spec["select"].items()
        ]
        attrs += [
            {
                "name": a,
                "mutable": False,
                "input_type": "checkbox",
                "default_value": "false",
                "values": ["false"],
            }
            for a in spec["checkbox"]
        ]
        out.append({"name": name, "color": spec["color"], "type": spec["type"], "attributes": attrs})
    for name, vals in TAG_LABELS.items():
        out.append(
            {
                "name": name,
                "color": TAG_COLORS[name],
                "type": "tag",
                "attributes": [
                    {
                        "name": TAG_ATTRIBUTE,
                        "mutable": False,
                        "input_type": "select",
                        "default_value": vals[0],
                        "values": list(vals),
                    }
                ],
            }
        )
    return out


def raw_labels_json() -> str:
    return json.dumps(raw_labels(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    sys.stdout.write(raw_labels_json())
