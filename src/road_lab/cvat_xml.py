"""Read and write CVAT for images 1.1 annotation files (annotations.xml, or the export .zip)."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

Point = tuple[float, float]

SHAPE_TAGS = {"polyline", "polygon", "box", "points", "ellipse", "mask", "cuboid", "skeleton"}
SHAPE_TYPE = {"box": "rectangle", "polyline": "polyline", "polygon": "polygon"}


class CvatFormatError(ValueError):
    """The file is not a readable CVAT for images 1.1 export."""


@dataclass
class Shape:
    label: str
    kind: str  # rectangle | polyline | polygon | other CVAT tag name
    points: list[Point]
    attributes: dict[str, str] = field(default_factory=dict)
    occluded: bool = False
    index: int = 0  # order inside its image file; CVAT may reorder shapes on re-import

    @property
    def ref(self) -> str:
        """Report id: label#order plus the first point, so a learner can find the shape on CVAT
        even when a re-imported task lists shapes in another order."""
        if not self.points:
            return f"{self.label}#{self.index}"
        x, y = self.points[0]
        return f"{self.label}#{self.index}@({x:.0f},{y:.0f})"

    def copy(self) -> "Shape":
        return Shape(self.label, self.kind, list(self.points), dict(self.attributes), self.occluded, self.index)


@dataclass
class Tag:
    label: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Image:
    name: str
    width: int
    height: int
    shapes: list[Shape] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)

    def tag_value(self, label: str, attr: str = "value") -> str | None:
        for t in self.tags:
            if t.label == label:
                return t.attributes.get(attr)
        return None

    def copy(self) -> "Image":
        return Image(
            self.name,
            self.width,
            self.height,
            [s.copy() for s in self.shapes],
            [Tag(t.label, dict(t.attributes)) for t in self.tags],
        )


def _parse_points(text: str) -> list[Point]:
    pts: list[Point] = []
    for pair in (text or "").strip().split(";"):
        if not pair.strip():
            continue
        x, y = pair.split(",")
        pts.append((float(x), float(y)))
    return pts


def _attrs(el: ET.Element) -> dict[str, str]:
    return {a.get("name", ""): (a.text or "").strip() for a in el.findall("attribute")}


def _read_bytes(path: Path) -> bytes:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "annotations.xml"]
            if not names:
                raise CvatFormatError(f"{path.name}: zip has no annotations.xml (export CVAT for images 1.1)")
            return zf.read(names[0])
    return path.read_bytes()


def parse_bytes(data: bytes, source: str = "<bytes>") -> list[Image]:
    try:
        root = ET.parse(io.BytesIO(data)).getroot()
    except ET.ParseError as exc:
        raise CvatFormatError(f"{source}: XML không đọc được ({exc})") from exc
    if root.tag != "annotations":
        raise CvatFormatError(f"{source}: thẻ gốc là <{root.tag}>, cần <annotations> (CVAT for images 1.1)")
    images: list[Image] = []
    for im in root.findall("image"):
        try:
            img = Image(im.get("name", ""), int(float(im.get("width", 0))), int(float(im.get("height", 0))))
        except ValueError as exc:
            raise CvatFormatError(f"{source}: kích thước ảnh sai ({exc})") from exc
        idx = 0
        for el in im:
            if el.tag == "tag":
                img.tags.append(Tag(el.get("label", ""), _attrs(el)))
                continue
            if el.tag not in SHAPE_TAGS:
                continue
            if el.tag == "box":
                x1, y1 = float(el.get("xtl", 0)), float(el.get("ytl", 0))
                x2, y2 = float(el.get("xbr", 0)), float(el.get("ybr", 0))
                pts = [(x1, y1), (x2, y2)]
            else:
                pts = _parse_points(el.get("points", ""))
            img.shapes.append(
                Shape(
                    label=el.get("label", ""),
                    kind=SHAPE_TYPE.get(el.tag, el.tag),
                    points=pts,
                    attributes=_attrs(el),
                    occluded=el.get("occluded", "0") in {"1", "true", "True"},
                    index=idx,
                )
            )
            idx += 1
        images.append(img)
    if root.find("image") is None and root.find("track") is not None:
        raise CvatFormatError(f"{source}: file là CVAT for video (track); cần CVAT for images 1.1")
    return images


def load(path: str | Path) -> list[Image]:
    p = Path(path)
    return parse_bytes(_read_bytes(p), p.name)


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def to_xml(images: list[Image], comment: str | None = None) -> str:
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    if comment:
        root.append(ET.Comment(f" {comment} "))
    for i, img in enumerate(images):
        im = ET.SubElement(
            root, "image", id=str(i), name=img.name, width=str(img.width), height=str(img.height)
        )
        for s in img.shapes:
            common = {"label": s.label, "source": "manual", "occluded": "1" if s.occluded else "0", "z_order": "0"}
            if s.kind == "rectangle":
                (x1, y1), (x2, y2) = s.points[0], s.points[1]
                el = ET.SubElement(
                    im, "box", **common, xtl=_fmt(x1), ytl=_fmt(y1), xbr=_fmt(x2), ybr=_fmt(y2)
                )
            else:
                tag = {"polyline": "polyline", "polygon": "polygon"}.get(s.kind, s.kind)
                el = ET.SubElement(
                    im, tag, **common, points=";".join(f"{_fmt(x)},{_fmt(y)}" for x, y in s.points)
                )
            for k, v in s.attributes.items():
                ET.SubElement(el, "attribute", name=k).text = v
        for t in img.tags:
            el = ET.SubElement(im, "tag", label=t.label, source="manual")
            for k, v in t.attributes.items():
                ET.SubElement(el, "attribute", name=k).text = v
    ET.indent(root)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write(images: list[Image], path: str | Path, comment: str | None = None) -> None:
    p = Path(path)
    xml = to_xml(images, comment)
    if p.suffix == ".zip":
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("annotations.xml", xml)
    else:
        p.write_text(xml, encoding="utf-8")
