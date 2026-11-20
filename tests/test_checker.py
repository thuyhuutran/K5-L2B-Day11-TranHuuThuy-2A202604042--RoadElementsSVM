"""The checker must pass its own mandatory self-test and keep the rubric identical to lab/AGENTS.md."""
import io
import re
from collections import Counter
from pathlib import Path

from road_lab import road_check as rc
from road_lab.cvat_xml import Shape
from road_lab.synthetic import synthetic_gt

ROOT = Path(__file__).resolve().parents[1]


def test_selftest_passes():
    out = io.StringIO()
    assert rc.selftest(synthetic_gt(), out), out.getvalue()


def test_gt_against_itself_is_perfect():
    gt = synthetic_gt()
    res = rc.check(gt, gt, "gt")
    assert res.findings == []
    assert res.auto_score == rc.AUTO_MAX == 78
    assert res.decision == "Release"


def test_each_perturbation_caught_exactly_once():
    gt = synthetic_gt()
    sub, expected = rc.perturb(gt)
    res = rc.check(gt, sub, "p")
    assert Counter((f.image, f.code) for f in res.findings) == Counter(expected)
    assert sorted(c for _, c in expected) == ["QC1-01", "QC1-04", "QC1-04", "QC1-05", "QC1-08"]
    assert res.decision == "Rework"  # camera tag and front light colour are critical


def test_missing_core_image_lowers_attempted_not_score_rate():
    gt = synthetic_gt()
    sub = [im for im in gt if not im.name.startswith("A12")]
    res = rc.check(gt, sub, "partial")
    assert "A12" in res.missing
    assert res.auto_score == rc.AUTO_MAX  # criteria are rated on attempted images only


def test_rubric_totals():
    assert sum(p for *_, p, _a in [(r[0], r[1], r[2], r[3]) for r in rc.RUBRIC]) == 100
    manual = {rid: p for rid, _, p, auto in rc.RUBRIC if not auto}
    assert manual == {"screens": 2, "qc1": 15, "report": 5}


def _table_points(md: str) -> list[int]:
    m = re.search(r"<!-- rubric:start -->(.*?)<!-- rubric:end -->", md, re.S)
    assert m, "rubric markers missing"
    return [int(x) for x in re.findall(r"^\|[^|]+\|[^|]+\|\s*(\d+)\s*\|\s*$", m.group(1), re.M)]


def test_rubric_identical_in_agents_and_rubric_md():
    agents = (ROOT / "lab" / "AGENTS.md").read_text(encoding="utf-8")
    rubric = (ROOT / "RUBRIC.md").read_text(encoding="utf-8")
    a = re.search(r"<!-- rubric:start -->(.*?)<!-- rubric:end -->", agents, re.S).group(1)
    b = re.search(r"<!-- rubric:start -->(.*?)<!-- rubric:end -->", rubric, re.S).group(1)
    assert a.strip() == b.strip()
    pts = _table_points(agents)
    assert pts == [10, 25, 10, 10, 15, 10, 15, 5]
    assert "+0,5" in a and "+4" in a


def test_lint_flags_far_to_near_and_missing_tag():
    gt = synthetic_gt()
    im = gt[0].copy()
    im.tags = [t for t in im.tags if t.label != "weather"]
    lane = next(s for s in im.shapes if s.label == "lane")
    lane.points = list(reversed(lane.points))
    codes = {f.code for f in rc.lint([im])}
    assert "QC1-01" in codes or "QC1-12" in codes
    assert "QC1-04" in codes


def test_lint_warns_repeated_point():
    im = synthetic_gt()[0].copy()
    lane = next(s for s in im.shapes if s.label == "lane")
    lane.points = [lane.points[0]] + lane.points
    hits = [f for f in rc.lint([im]) if "điểm lặp" in f.message]
    assert len(hits) == 1 and hits[0].severity == "minor" and hits[0].ref == lane.ref


def test_lint_clean_on_gt():
    assert [f for f in rc.lint(synthetic_gt()) if f.severity != "minor"] == []


def test_cli_selftest_and_check(tmp_path, capsys):
    from road_lab.cvat_xml import write
    gt = synthetic_gt()
    p = tmp_path / "gt.xml"
    write(gt, p)
    assert rc.main(["selftest", "--gt", str(p)]) == 0
    assert "SELFTEST PASS" in capsys.readouterr().out
    md = tmp_path / "qc1.md"
    assert rc.main(["check", "--gt", str(p), "--sub", str(p), "--name", "x", "--qc1-md", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    for code in rc.CODE_TITLES:
        assert code in text


def test_unknown_label_is_file_error():
    gt = synthetic_gt()
    sub = [im.copy() for im in gt]
    sub[0].shapes.append(Shape("pothole", "polygon", [(0, 0), (10, 0), (10, 10)], {}))
    res = rc.check(gt, sub, "bad")
    assert any(f.code == "QC1-12" for f in res.findings)


def test_duplicate_slot_grades_labelled_copy_and_warns():
    gt = synthetic_gt()
    sub = [im.copy() for im in gt]
    empty = sub[0].copy()
    empty.shapes, empty.tags = [], []
    sub.insert(0, empty)  # an empty duplicate listed first must not hide the labelled copy
    res = rc.check(gt, sub, "dup")
    slot = rc.image_slot(gt[0].name)
    assert slot in res.attempted and slot not in res.missing
    assert res.auto_score == rc.AUTO_MAX
    assert [f.image for f in res.findings if f.code == "QC1-12"] == [slot]
    assert any(f.image == slot and "2 lần" in f.message for f in rc.lint(sub))
    assert len(rc.label_counts(sub)) == len(sub)


def test_lint_writes_delivery_manifest(tmp_path, capsys):
    import json
    import zipfile

    from road_lab.cvat_xml import write
    gt = synthetic_gt()
    z = tmp_path / "an-front.zip"
    write(gt, z)
    m = tmp_path / "an-manifest.json"
    assert rc.main(["lint", str(z), "--manifest", str(m), "--name", "an", "--revision", "2"]) == 0
    d = json.loads(m.read_text(encoding="utf-8"))
    assert d["format"] == "CVAT for images 1.1" and d["guideline"] == rc.GUIDELINE_VERSION
    assert d["name"] == "an" and d["revision"] == 2
    f = d["files"][0]
    assert f["file"] == "an-front.zip" and len(f["sha256"]) == 64 and f["contains_images"] is False
    assert f["images"] == len(gt) and f["images_all_tags"] == len(gt) and f["images_unlabelled"] == 0
    assert set(d["lint"]) == {"nặng", "chính", "nhẹ"} and d["lint"]["nặng"] == 0
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("images/A01.jpg", b"x")
    assert rc.main(["lint", str(z), "--manifest", str(m)]) == 0
    assert json.loads(m.read_text(encoding="utf-8"))["files"][0]["contains_images"] is True
    assert "kèm ảnh" in capsys.readouterr().out


def test_lint_manifest_refuses_bad_inputs_and_destination(tmp_path):
    from road_lab.cvat_xml import write
    z = tmp_path / "an-front.zip"
    write(synthetic_gt(), z)
    before = z.read_bytes()
    # destination equal to an input must not overwrite the label file
    assert rc.main(["lint", str(z), "--manifest", str(z)]) == 2
    assert z.read_bytes() == before
    # an unopenable input yields no manifest and no crash
    m = tmp_path / "an-manifest.json"
    assert rc.main(["lint", str(z), str(tmp_path / "missing.zip"), "--manifest", str(m)]) == 1
    assert not m.exists()
