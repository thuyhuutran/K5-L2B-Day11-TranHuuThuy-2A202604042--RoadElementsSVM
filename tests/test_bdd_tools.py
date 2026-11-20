"""select / convert / rowanchor on a tiny hand-made BDD100K-format fixture (no real dataset needed)."""
import csv
import json

import pytest

from road_lab import bdd_to_cvat_road as conv
from road_lab import rowanchor
from road_lab import select_bdd_road as sel
from road_lab.bdd import classify, load_frames
from road_lab.cvat_xml import Image, Shape, load, write


def lane(cat, verts, style="solid", direction="parallel", occluded=False, types=None):
    return {"category": cat, "attributes": {"laneDirection": direction, "laneStyle": style, "occluded": occluded},
            "poly2d": [{"vertices": verts, "types": types or "L" * len(verts), "closed": False}]}


def frame(name, labels, tod="daytime", weather="clear", scene="highway"):
    return {"name": name, "attributes": {"timeofday": tod, "weather": weather, "scene": scene}, "labels": labels}


@pytest.fixture()
def labels_file(tmp_path):
    frames = [
        frame("hwy.jpg", [
            lane("single white", [[600, 400], [200, 720]], style="dashed"),
            lane("single white", [[700, 720], [660, 400]]),
            lane("double yellow", [[550, 400], [50, 720]]),
            lane("single white", [[0, 600], [1280, 600]], direction="vertical"),
            {"category": "traffic light", "attributes": {"trafficLightColor": "red"},
             "box2d": {"x1": 640, "y1": 200, "x2": 660, "y2": 240}},
            {"category": "traffic light", "attributes": {"trafficLightColor": "green"},
             "box2d": {"x1": 10, "y1": 10, "x2": 12, "y2": 14}},
        ]),
        frame("city.jpg", [
            lane("crosswalk", [[400, 600], [800, 600]]),
            lane("crosswalk", [[400, 650], [800, 660]]),
            {"category": "drivable area", "attributes": {"areaType": "direct"},
             "poly2d": [{"vertices": [[300, 720], [600, 450], [700, 450], [1000, 720]], "types": "LLLL", "closed": True}]},
            lane("road curb", [[100, 720], [500, 450]]),
            {"category": "traffic sign", "attributes": {}, "box2d": {"x1": 900, "y1": 300, "x2": 930, "y2": 330}},
        ], scene="city street"),
    ]
    p = tmp_path / "labels.json"
    p.write_text(json.dumps(frames), encoding="utf-8")
    return p


def test_classify_both_layouts():
    assert classify({"category": "lane", "attributes": {"laneType": "road curb"}}) == ("road_curb", "road curb")
    assert classify({"category": "single white"}) == ("lane", "single white")
    assert classify({"category": "drivable area", "attributes": {"areaType": "alternative"}}) == ("drivable", "alternative")
    assert classify({"category": "area/drivable"}) == ("drivable", "direct")
    assert classify({"category": "traffic light", "attributes": {"trafficLightColor": "Y"}})[0] == "traffic_light"


def test_features(labels_file):
    fr = load_frames([labels_file])
    f = sel.features(fr["hwy.jpg"])
    assert f["lanes"] == 3 and f["vertical"] == 1 and f["dashed"] == 1 and f["double_yellow"] == 1
    assert f["lights"] == 1  # the 4 px light is below the 8 px rule
    g = sel.features(fr["city.jpg"])
    assert g["crosswalk"] == 2 and g["direct"] == 1 and g["curb"] == 1 and g["signs"] == 1


def test_select_writes_manifest(labels_file, tmp_path, capsys):
    out, cand = tmp_path / "m.csv", tmp_path / "c.csv"
    assert sel.main(["--labels", str(labels_file), "--out", str(out), "--candidates", str(cand)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["slot"] for r in rows] == [f"A{i:02d}" for i in range(1, 17)]
    assert list(rows[0]) == sel.MANIFEST_COLUMNS
    a01 = rows[0]
    assert a01["file"] == "hwy.jpg" and a01["tier"] == "core" and a01["blur_note"] == "coach kiểm tay"
    picked = [r["file"] for r in rows if r["file"]]
    assert len(picked) == len(set(picked))  # one image per slot
    assert any("KHÔNG có ứng viên" in r["reason"] for r in rows)


def test_convert_frame(labels_file):
    fr = load_frames([labels_file])
    img, todo = conv.convert_frame(fr["hwy.jpg"], "A01")
    assert img.name == "A01_hwy.jpg" and (img.width, img.height) == (1280, 720)
    lanes = [s for s in img.shapes if s.label == "lane"]
    assert len(lanes) == 3  # vertical stop line skipped
    assert all(s.points[0][1] >= s.points[-1][1] for s in lanes)  # oriented near-to-far
    dy = next(s for s in lanes if s.attributes["color"] == "yellow")
    assert dy.attributes["kind"] == "double"
    lights = [s for s in img.shapes if s.label == "traffic_light"]
    assert len(lights) == 1 and lights[0].attributes["color"] == "red"
    assert {t.label: t.attributes["value"] for t in img.tags} == {"camera": "front", "timeofday": "day", "weather": "clear", "source": "real"}
    assert any(t["attribute"] == "position" for t in todo)
    assert any(t["attribute"] == "facing" for t in todo)

    img2, _ = conv.convert_frame(fr["city.jpg"], "A06")
    labels = sorted(s.label for s in img2.shapes)
    assert labels == ["crosswalk", "drivable", "road_curb", "traffic_sign"]
    cw = next(s for s in img2.shapes if s.label == "crosswalk")
    assert cw.kind == "polygon" and len(cw.points) >= 3


def test_convert_cli(labels_file, tmp_path):
    man = tmp_path / "m.csv"
    with man.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sel.MANIFEST_COLUMNS)
        w.writeheader()
        w.writerow({"slot": "A01", "file": "hwy.jpg"})
        w.writerow({"slot": "A06", "file": "city.jpg"})
        w.writerow({"slot": "A13", "file": "missing.jpg"})
    out = tmp_path / "gt" / "draft.xml"
    assert conv.main(["--labels", str(labels_file), "--manifest", str(man), "--out", str(out), "--core-only"]) == 0
    imgs = load(out)
    assert [i.name for i in imgs] == ["A01_hwy.jpg", "A06_city.jpg"]
    assert "BDD100K" in out.read_text(encoding="utf-8")  # copyright comment kept
    assert (tmp_path / "gt" / "draft_todo.csv").exists()


def test_rowanchor(tmp_path, capsys):
    pts = [(640.0, 720.0), (600.0, 640.0), (580.0, 580.0)]
    xs = rowanchor.anchors(pts)
    assert xs[0] == pytest.approx(640.0) and xs[2] == pytest.approx(600.0) and xs[4] is None
    im = Image("A01_x.jpg", 1280, 720)
    im.shapes = [Shape("lane", "polyline", pts, {"position": "R1", "style": "solid", "color": "white", "kind": "single"})]
    p = tmp_path / "a.xml"
    write([im], p)
    assert rowanchor.main([str(p), "--image", "A01"]) == 0
    out = capsys.readouterr().out
    assert "không có làn" in out and "640.0" in out
    assert rowanchor.main([str(p), "--image", "A01", "--position", "L1"]) == 1


def test_weather_mapping_keeps_overcast_separate():
    # Overcast but dry sky is its own tag value, not folded into clear.
    assert conv.WEATHER["overcast"] == "overcast"
    assert conv.WEATHER["partly cloudy"] == "clear"
