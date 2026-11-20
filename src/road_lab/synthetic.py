"""Deterministic synthetic ground truth (A01-A12 front, B01-B08 fisheye) for the checker self-test.

This is NOT a substitute for the coach's real GT: it only exercises the checker code paths
(every label, attribute, camera and QC1 code) so `road_check selftest` runs without any dataset.
"""
from __future__ import annotations

import math

from .cvat_xml import Image, Shape, Tag
from .taxonomy import CORE_FISHEYE, CORE_FRONT, TAG_ATTRIBUTE

FISHEYE_FILES = {
    "B01": "02688_FV", "B02": "03177_FV", "B03": "04267_RV", "B04": "05535_RV",
    "B05": "05780_MVL", "B06": "04068_MVL", "B07": "01216_MVR", "B08": "05783_MVR",
}
FISHEYE_CAM = {"FV": "fisheye_front", "RV": "fisheye_rear", "MVL": "fisheye_left", "MVR": "fisheye_right"}


def _tags(camera: str, timeofday: str = "day", weather: str = "clear") -> list[Tag]:
    return [
        Tag("camera", {TAG_ATTRIBUTE: camera}),
        Tag("timeofday", {TAG_ATTRIBUTE: timeofday}),
        Tag("weather", {TAG_ATTRIBUTE: weather}),
        Tag("source", {TAG_ATTRIBUTE: "real"}),
    ]


def _line(x_near: float, x_far: float, y_near: float = 715.0, y_far: float = 430.0, n: int = 5, bend: float = 0.0) -> list[tuple[float, float]]:
    pts = []
    for k in range(n):
        t = k / (n - 1)
        x = x_near + (x_far - x_near) * t + bend * math.sin(math.pi * t)
        pts.append((round(x, 2), round(y_near + (y_far - y_near) * t, 2)))
    return pts


def _lane(pts, position, style="dashed", color="white", kind="single", occluded=False) -> Shape:
    return Shape("lane", "polyline", pts, {"position": position, "style": style, "color": color, "kind": kind}, occluded)


def _light(x, y, w, h, color="red", typ="vehicle", facing="front", edge=False) -> Shape:
    return Shape(
        "traffic_light", "rectangle", [(x, y), (x + w, y + h)],
        {"color": color, "type": typ, "facing": facing, "edge_zone": "true" if edge else "false"},
    )


def _sign(x, y, w, h, group="prohibitory", facing="front", edge=False) -> Shape:
    return Shape(
        "traffic_sign", "rectangle", [(x, y), (x + w, y + h)],
        {"group": group, "facing": facing, "edge_zone": "true" if edge else "false"},
    )


def _front(i: int) -> Image:
    slot = CORE_FRONT[i]
    tod = {10: "dusk"}.get(i, "day")
    img = Image(f"{slot}_synthetic.jpg", 1280, 720, tags=_tags("front", tod))
    s = img.shapes
    bend = (i % 3 - 1) * 18.0
    s.append(_lane(_line(450, 615, bend=bend), "L1", "dashed"))
    s.append(_lane(_line(830, 665, bend=bend), "R1", "solid"))
    if i in (0, 3, 11):
        s.append(_lane(_line(120, 590, bend=bend), "L2", "solid", "yellow" if i == 3 else "white", "double" if i == 3 else "single"))
    if i in (0, 4):
        s.append(_lane(_line(1160, 690, bend=bend), "R2", "dashed"))
    if i == 2:
        s[0].occluded = True
    s.append(Shape("drivable", "polygon", [(470, 715), (810, 715), (662, 440), (618, 440)], {"area_type": "direct"}))
    if i in (3, 5, 11):
        s.append(Shape("drivable", "polygon", [(130, 715), (440, 715), (612, 440), (595, 440)], {"area_type": "alternative"}))
    if i in (4, 11):
        s.append(Shape("road_curb", "polyline", [(20.0, 700.0), (300.0, 560.0), (560.0, 445.0)]))
    if i in (5, 11):
        s.append(Shape("crosswalk", "polygon", [(380, 600), (900, 600), (870, 560), (410, 560)]))
    if i in (6, 7, 10, 11):
        s.append(_light(700, 200, 14, 36, "red"))
    if i == 7:
        s.append(_light(820, 210, 12, 30, "green", facing="front"))
        s.append(_light(300, 230, 10, 24, "unknown", facing="side"))
        s.append(_light(950, 260, 3, 6, "red"))  # below 8 px: optional
    if i in (8, 9, 10, 11):
        s.append(_sign(1000, 300, 40, 40, "prohibitory"))
    if i == 8:
        s.append(_sign(1060, 300, 36, 36, "warning"))
    if i == 9:
        s.append(_sign(1000, 342, 40, 14, "supplementary"))
    for k, sh in enumerate(s):
        sh.index = k
    return img


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 9) -> list[tuple[float, float]]:
    return [
        (round(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / (n - 1))), 2),
         round(cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / (n - 1))), 2))
        for k in range(n)
    ]


def _fisheye(i: int) -> Image:
    slot = CORE_FISHEYE[i]
    stem = FISHEYE_FILES[slot]
    cam = FISHEYE_CAM[stem.split("_")[1]]
    img = Image(f"{slot}_{stem}.png", 1280, 966, tags=_tags(cam))
    s = img.shapes
    side = cam in {"fisheye_left", "fisheye_right"}
    if side:
        s.append(_lane(_arc(640, 1500, 900, 235, 305), "other", "solid"))
    else:
        s.append(_lane(_arc(1500, 1000, 1000, 190, 205), "L1", "dashed"))
        s.append(_lane(_arc(-220, 1000, 1000, 350, 335), "R1", "solid"))
    s.append(Shape("drivable", "polygon", [(200, 860), (1080, 860), (900, 600), (380, 600)], {"area_type": "direct"}))
    if i in (0, 3, 4, 6):
        s.append(Shape("crosswalk", "polygon", [(300, 760), (980, 760), (930, 690), (350, 690)]))
    if i in (4, 6):
        s.append(Shape("road_curb", "polyline", _arc(640, 1700, 1250, 240, 300, 7)))
    if i == 1:
        s.append(_light(60, 120, 16, 34, "green", edge=True))
        s.append(_sign(1180, 150, 30, 30, "information", edge=True))
    for k, sh in enumerate(s):
        sh.index = k
    return img


def synthetic_gt() -> list[Image]:
    return [_front(i) for i in range(len(CORE_FRONT))] + [_fisheye(i) for i in range(len(CORE_FISHEYE))]
