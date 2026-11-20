import json
from pathlib import Path

import pytest

from road_lab import geometry as geo
from road_lab.cvat_xml import CvatFormatError, load, parse_bytes, to_xml, write
from road_lab.synthetic import synthetic_gt
from road_lab.taxonomy import expected_camera, image_slot, raw_labels_json

ROOT = Path(__file__).resolve().parents[1]


def test_labels_config_matches_taxonomy():
    assert json.loads((ROOT / "configs" / "road_v1_labels.json").read_text(encoding="utf-8")) == json.loads(raw_labels_json())


def test_labels_config_shape():
    labels = json.loads(raw_labels_json())
    types = {l["name"]: l["type"] for l in labels}
    assert types == {"lane": "polyline", "road_curb": "polyline", "crosswalk": "polygon", "drivable": "polygon",
                     "traffic_light": "rectangle", "traffic_sign": "rectangle",
                     "camera": "tag", "timeofday": "tag", "weather": "tag", "source": "tag"}
    lane = next(l for l in labels if l["name"] == "lane")
    pos = next(a for a in lane["attributes"] if a["name"] == "position")
    assert pos["values"] == ["L1", "R1", "L2", "R2", "other"]


def test_xml_roundtrip(tmp_path):
    gt = synthetic_gt()
    p = tmp_path / "a.xml"
    write(gt, p)
    back = load(p)
    assert [im.name for im in back] == [im.name for im in gt]
    for a, b in zip(gt, back):
        assert len(a.shapes) == len(b.shapes)
        assert {t.label: t.attributes for t in a.tags} == {t.label: t.attributes for t in b.tags}
        for s, t in zip(a.shapes, b.shapes):
            assert s.label == t.label and s.kind == t.kind and s.attributes == t.attributes and s.occluded == t.occluded
            assert all(abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01 for (x1, y1), (x2, y2) in zip(s.points, t.points))


def test_zip_roundtrip(tmp_path):
    gt = synthetic_gt()[:3]
    p = tmp_path / "a.zip"
    write(gt, p)
    assert [im.name for im in load(p)] == [im.name for im in gt]


def test_bad_xml_raises():
    with pytest.raises(CvatFormatError):
        parse_bytes(b"<annotations><image name='x'", "bad")


def test_to_xml_has_polyline():
    assert '<polyline label="lane"' in to_xml(synthetic_gt()[:1])


def test_slot_and_camera():
    assert image_slot("A03_b1c66a42-6f7d68ca.jpg") == "A03"
    assert image_slot("B07_01216_MVR.png") == "B07"
    assert image_slot("nothing.png") is None
    assert expected_camera("B07_01216_MVR.png") == "fisheye_right"
    assert expected_camera("A01_x.jpg") == "front"


def test_geometry_basics():
    line = [(0.0, 0.0), (0.0, 100.0)]
    assert geo.polyline_length(line) == pytest.approx(100.0)
    assert geo.max_deviation([(3.0, 0.0), (3.0, 100.0)], line) == pytest.approx(3.0, abs=0.01)
    assert geo.x_at_y([(100.0, 720.0), (300.0, 520.0)], 620.0) == pytest.approx(200.0)
    assert geo.x_at_y([(100.0, 720.0), (300.0, 520.0)], 500.0) is None
    sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    iou, spill = geo.polygon_iou_spill([sq], [sq])
    assert iou == pytest.approx(1.0, abs=0.02) and spill == pytest.approx(0.0, abs=0.02)
    assert len(geo.convex_hull(sq + [(5.0, 5.0)])) == 4
    assert geo.box_iou([(0, 0), (10, 10)], [(5, 0), (15, 10)]) == pytest.approx(1 / 3, abs=0.01)


def test_bezier_passes_through_ends():
    pts = geo.sample_bezier([(0.0, 0.0), (10.0, 20.0), (30.0, 20.0), (40.0, 0.0)], "LCCL")
    assert pts[0] == (0.0, 0.0) and pts[-1] == (40.0, 0.0)
    assert len(pts) > 4


def test_shape_ref_carries_first_point_so_reordered_shapes_stay_findable():
    img = synthetic_gt()[0]
    lane = next(s for s in img.shapes if s.label == "lane")
    x, y = lane.points[0]
    assert lane.ref == f"lane#{lane.index}@({x:.0f},{y:.0f})"
    moved = lane.copy()
    moved.index = 7  # CVAT re-import can list the same shape at another position
    assert moved.ref.endswith(f"@({x:.0f},{y:.0f})")
