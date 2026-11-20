"""rowanchor: the optional buffer activity "Từ polyline của tôi đến đích row-anchor".

    python -m road_lab.rowanchor FILE.zip --image A01 [--position R1] [--rows 720,680,640,600,560]

For each lane polyline with the given position on one front image, print x at each anchor row by
linear interpolation between the two points that bracket the row, or "không có làn" when the row
lies outside the polyline. Use it to check the numbers you computed by hand; it is not graded.
"""
from __future__ import annotations

import argparse
import sys

from .cvat_xml import CvatFormatError, load
from .geometry import x_at_y
from .taxonomy import image_slot

DEFAULT_ROWS = (720, 680, 640, 600, 560)


def anchors(points, rows=DEFAULT_ROWS) -> list[float | None]:
    return [x_at_y(points, float(y)) for y in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rowanchor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--image", required=True, help="slot (A01) hoặc tên ảnh")
    ap.add_argument("--position", default="R1")
    ap.add_argument("--rows", default=",".join(map(str, DEFAULT_ROWS)))
    a = ap.parse_args(argv)
    rows = tuple(int(r) for r in a.rows.split(","))
    try:
        images = load(a.file)
    except (CvatFormatError, OSError) as exc:
        print(f"Không mở được file: {exc}", file=sys.stderr)
        return 2
    img = next((im for im in images if im.name == a.image or image_slot(im.name) == a.image), None)
    if img is None:
        print(f"Không thấy ảnh {a.image}", file=sys.stderr)
        return 2
    lanes = [s for s in img.shapes if s.label == "lane" and s.attributes.get("position") == a.position]
    if not lanes:
        print(f"{img.name}: không có polyline lane position = {a.position}")
        return 1
    print("| polyline | " + " | ".join(f"y={y}" for y in rows) + " |")
    print("| --- |" + " ---: |" * len(rows))
    for s in lanes:
        xs = anchors(s.points, rows)
        print(f"| {s.ref} | " + " | ".join("không có làn" if x is None else f"{x:.1f}" for x in xs) + " |")
    first, last = lanes[0].points[0], lanes[0].points[-1]
    if first[1] < last[1]:
        print("\nChú ý: polyline đầu tiên vẽ từ xa về gần (điểm đầu cao hơn điểm cuối).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
