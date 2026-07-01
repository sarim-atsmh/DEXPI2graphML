"""Render a DEXPI Proteus 4.2.0 document (``*.dexpi.xml``) to PNG/SVG.

This targets the self-contained Proteus 4.2.0 files produced by
``dxf_to_dexpi.export.export_proteus_xml`` (see ``DEXPI_VIEWER_GUIDE.md``):

* ``<PlantModel>`` root (no XML namespace),
* a ``ShapeCatalogue`` of symbol geometry in **local** coordinates,
* component instances that link to the catalogue by ``(tag, ComponentName)`` and
  carry their own affine transform (``Position`` + ``Scale``),
* a ``PipingNetworkSystem`` whose segment ``CenterLine``s are already in world
  coordinates.

Every instance carries its own transform, so no rotation/scale heuristics are
needed and no external symbol library is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

DEFAULT_DPI = 100
# Drawings are tiny in world units (a sheet is ~0.5 wide); blow them up so the
# rasterised output has usable resolution. This is the single global scale of
# §8 — per-instance scale is already baked into each transform.
SMALL_MODEL_SCALE = 5000.0
LINE_WIDTH = 0.9
NOZZLE_RADIUS_PX = 1.6


@dataclass(frozen=True)
class ViewBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass(frozen=True)
class BBox:
    left: float
    bottom: float
    right: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class Transform:
    """Instance placement transform: scale, then rotate about +Z, then translate."""

    tx: float = 0.0
    ty: float = 0.0
    rotation_deg: float = 0.0
    sx: float = 1.0
    sy: float = 1.0

    def apply(self, x: float, y: float) -> tuple[float, float]:
        px = x * self.sx
        py = y * self.sy
        angle = math.radians(self.rotation_deg)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        return (self.tx + rx, self.ty + ry)


# Direct children of <PlantModel> that are placed component instances.
INSTANCE_TAGS = {"PipingComponent", "ProcessInstrumentationFunction", "Equipment"}
# Geometry primitives that may appear inside a catalogue entry.
PRIMITIVE_TAGS = {"Line", "PolyLine", "Circle", "Text"}


def render_dexpi_plot(path_xml: str, path_plot_stem: str) -> None:
    """Render ``path_xml`` to two variants:

    ``<stem>.png``/``.svg``          — clean (no block-name labels)
    ``<stem>_labeled.png``/``.svg``  — each component's ``ComponentName`` overlaid
    """
    stem = _normalized_output_stem(path_plot_stem)
    root = ET.parse(Path(path_xml)).getroot()
    _render_plantmodel(root, stem, show_component_labels=False)
    _render_plantmodel(root, Path(f"{stem}_labeled"), show_component_labels=True)


def _render_plantmodel(
    root, output_stem: Path, show_component_labels: bool = False
) -> None:
    view_box = _extract_view_box(root)
    pixel_scale = _pixel_scale(view_box)
    figure, axis = _build_figure(view_box, pixel_scale)
    axis.set_facecolor("white")

    catalogue = _build_component_map(_find_child_local(root, "ShapeCatalogue"))

    # Pipe centerlines sit underneath the symbols.
    for segment in _iter_segments(root):
        _draw_centerline(axis, segment, view_box, pixel_scale)

    for instance in _iter_instances(root):
        component_name = instance.get("ComponentName")
        definition = (
            catalogue.get((_local_name(instance.tag), component_name))
            if component_name
            else None
        )
        if definition is not None:
            _draw_catalogue_definition(
                axis,
                definition,
                _transform_from_element(instance),
                view_box,
                pixel_scale,
            )
            if show_component_labels and component_name:
                bbox = _instance_bbox(instance, view_box, pixel_scale)
                if bbox is not None:
                    _draw_component_label(axis, bbox, [component_name])
        else:
            _draw_placeholder(axis, instance, view_box, pixel_scale)

        for nozzle in _find_children_local(instance, "Nozzle"):
            _draw_nozzle(axis, nozzle, view_box, pixel_scale)

    _finalize_figure(figure, axis, output_stem)


# --------------------------------------------------------------------------- #
# Catalogue + instances
# --------------------------------------------------------------------------- #
def _build_component_map(shape_catalogue) -> dict:
    """Map ``(element tag, ComponentName)`` -> catalogue entry.

    Keyed by the pair, not ComponentName alone: instances and catalogue entries
    share tag names and a name can repeat across element types.
    """
    component_map: dict = {}
    if shape_catalogue is None:
        return component_map
    for element in list(shape_catalogue):
        component_name = element.get("ComponentName")
        if component_name:
            component_map[(_local_name(element.tag), component_name)] = element
    return component_map


def _iter_instances(root):
    for element in list(root):
        if _local_name(element.tag) in INSTANCE_TAGS:
            yield element


def _iter_segments(root):
    for system in _find_children_local(root, "PipingNetworkSystem"):
        yield from _find_children_local(system, "PipingNetworkSegment")


def _draw_catalogue_definition(
    axis, definition, transform: Transform, view_box: ViewBox, pixel_scale: float
) -> None:
    for child in list(definition):
        if _local_name(child.tag) in PRIMITIVE_TAGS:
            _draw_primitive(axis, child, view_box, pixel_scale, transform)


def _draw_placeholder(
    axis, instance, view_box: ViewBox, pixel_scale: float
) -> None:
    """Draw a dashed box + label for an instance with no catalogue geometry."""
    bbox = _instance_bbox(instance, view_box, pixel_scale)
    if bbox is None:
        return
    axis.add_patch(
        Rectangle(
            (bbox.left, bbox.bottom),
            bbox.width,
            bbox.height,
            fill=False,
            edgecolor="#cc0000",
            linewidth=LINE_WIDTH,
            linestyle="--",
            zorder=3,
        )
    )
    label = instance.get("TagName") or instance.get("ID") or ""
    if label:
        _draw_component_label(axis, bbox, [label])


# --------------------------------------------------------------------------- #
# Primitives (local coordinates, transformed per instance)
# --------------------------------------------------------------------------- #
def _draw_primitive(
    axis, primitive, view_box: ViewBox, pixel_scale: float, transform: Transform | None
) -> None:
    tag = _local_name(primitive.tag)

    if tag in {"Line", "PolyLine"}:
        points = _coordinates_from_primitive(primitive, transform)
        if len(points) < 2:
            return
        axis.plot(
            [_to_canvas_x(x, view_box, pixel_scale) for x, _ in points],
            [_to_canvas_y(y, view_box, pixel_scale) for _, y in points],
            color="#000000",
            linewidth=LINE_WIDTH,
            solid_capstyle="round",
            zorder=2,
        )
        return

    if tag == "Circle":
        center = _circle_center(primitive, transform)
        radius_element = _find_child_local(primitive, "Radius")
        radius_local = _float_attr(radius_element, "Value") if radius_element is not None else 0.0
        scale = math.sqrt(abs(transform.sx * transform.sy)) if transform is not None else 1.0
        axis.add_patch(
            Circle(
                _to_canvas(center[0], center[1], view_box, pixel_scale),
                radius=radius_local * pixel_scale * scale,
                fill=False,
                edgecolor="#000000",
                linewidth=LINE_WIDTH,
                zorder=3,
            )
        )
        return

    if tag == "Text":
        string = (primitive.text or "").strip()
        if not string:
            return
        x = _float_attr(primitive, "X")
        y = _float_attr(primitive, "Y")
        if transform is not None:
            x, y = transform.apply(x, y)
        sy = abs(transform.sy) if transform is not None else 1.0
        rotation = transform.rotation_deg if transform is not None else 0.0
        axis.text(
            _to_canvas_x(x, view_box, pixel_scale),
            _to_canvas_y(y, view_box, pixel_scale),
            string,
            fontsize=max(5.0, _float_attr(primitive, "Height", 0.002) * pixel_scale * sy),
            color="#000000",
            ha="center",
            va="center",
            rotation=-rotation,
            zorder=4,
        )


def _coordinates_from_primitive(primitive, transform: Transform | None):
    points = []
    for coordinate in _find_children_local(primitive, "Coordinate"):
        x = _float_attr(coordinate, "X")
        y = _float_attr(coordinate, "Y")
        if transform is not None:
            x, y = transform.apply(x, y)
        points.append((x, y))
    return points


def _circle_center(primitive, transform: Transform | None):
    location = primitive.find("Position/Location")
    if location is None:
        x, y = 0.0, 0.0
    else:
        x = _float_attr(location, "X")
        y = _float_attr(location, "Y")
    if transform is not None:
        x, y = transform.apply(x, y)
    return (x, y)


def _transform_from_element(element) -> Transform:
    position = element.find("Position")
    scale = element.find("Scale")
    tx = ty = 0.0
    rotation_deg = 0.0
    sx = sy = 1.0

    if position is not None:
        location = position.find("Location")
        reference = position.find("Reference")
        if location is not None:
            tx = _float_attr(location, "X")
            ty = _float_attr(location, "Y")
        if reference is not None:
            # Reference is a unit vector (cosθ, sinθ); θ is CCW about +Z.
            rotation_deg = math.degrees(
                math.atan2(_float_attr(reference, "Y", 0.0), _float_attr(reference, "X", 1.0))
            )
    if scale is not None:
        sx = _float_attr(scale, "X", 1.0)
        sy = _float_attr(scale, "Y", 1.0)

    return Transform(tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)


# --------------------------------------------------------------------------- #
# Pipe network + nozzles (already in world coordinates)
# --------------------------------------------------------------------------- #
def _draw_centerline(axis, segment, view_box: ViewBox, pixel_scale: float) -> None:
    center_line = _find_child_local(segment, "CenterLine")
    if center_line is None:
        return
    points = _coordinates_from_primitive(center_line, None)
    if len(points) < 2:
        return
    axis.plot(
        [_to_canvas_x(x, view_box, pixel_scale) for x, _ in points],
        [_to_canvas_y(y, view_box, pixel_scale) for _, y in points],
        color="#000000",
        linewidth=LINE_WIDTH,
        solid_capstyle="round",
        zorder=1,
    )


def _draw_nozzle(axis, nozzle, view_box: ViewBox, pixel_scale: float) -> None:
    location = nozzle.find("Position/Location")
    if location is None:
        return
    axis.add_patch(
        Circle(
            _to_canvas(
                _float_attr(location, "X"),
                _float_attr(location, "Y"),
                view_box,
                pixel_scale,
            ),
            radius=NOZZLE_RADIUS_PX,
            fill=True,
            facecolor="#000000",
            edgecolor="none",
            zorder=5,
        )
    )


def _instance_bbox(instance, view_box: ViewBox, pixel_scale: float) -> BBox | None:
    """Instance ``Extent`` (world coords) mapped to canvas space."""
    extent = _find_child_local(instance, "Extent")
    if extent is None:
        return None
    min_node = _find_child_local(extent, "Min")
    max_node = _find_child_local(extent, "Max")
    if min_node is None or max_node is None:
        return None
    xs = [
        _to_canvas_x(_float_attr(min_node, "X"), view_box, pixel_scale),
        _to_canvas_x(_float_attr(max_node, "X"), view_box, pixel_scale),
    ]
    ys = [
        _to_canvas_y(_float_attr(min_node, "Y"), view_box, pixel_scale),
        _to_canvas_y(_float_attr(max_node, "Y"), view_box, pixel_scale),
    ]
    return BBox(left=min(xs), bottom=min(ys), right=max(xs), top=max(ys))


def _draw_component_label(axis, bbox: BBox, labels: list[str]) -> None:
    axis.text(
        bbox.right + 4.0,
        (bbox.top + bbox.bottom) / 2.0,
        "\n".join(labels[:3]),
        fontsize=2.0,
        color="#111111",
        ha="left",
        va="center",
        zorder=5,
    )


# --------------------------------------------------------------------------- #
# View box, figure, canvas mapping
# --------------------------------------------------------------------------- #
def _extract_view_box(root) -> ViewBox:
    extent = root.find("Drawing/Extent")
    if extent is not None:
        min_node = extent.find("Min")
        max_node = extent.find("Max")
        if min_node is not None and max_node is not None:
            return ViewBox(
                _float_attr(min_node, "X"),
                _float_attr(min_node, "Y"),
                _float_attr(max_node, "X"),
                _float_attr(max_node, "Y"),
            )

    # Fallback: bound everything we would draw (world-coord coordinates only).
    coords = []
    for instance in _iter_instances(root):
        bbox_extent = _find_child_local(instance, "Extent")
        if bbox_extent is None:
            continue
        for corner in ("Min", "Max"):
            node = _find_child_local(bbox_extent, corner)
            if node is not None:
                coords.append((_float_attr(node, "X"), _float_attr(node, "Y")))
    if not coords:
        return ViewBox(0.0, 0.0, 1.0, 1.0)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return ViewBox(min(xs), min(ys), max(xs), max(ys))


def _pixel_scale(view_box: ViewBox) -> float:
    if view_box.width <= 10.0 and view_box.height <= 10.0:
        return SMALL_MODEL_SCALE
    return 1.0


def _build_figure(view_box: ViewBox, pixel_scale: float):
    width_px = view_box.width * pixel_scale
    height_px = view_box.height * pixel_scale
    figure = plt.figure(
        figsize=(max(8.0, width_px / DEFAULT_DPI), max(6.0, height_px / DEFAULT_DPI)),
        dpi=DEFAULT_DPI,
    )
    axis = figure.add_subplot(111)
    axis.set_xlim(0, width_px)
    axis.set_ylim(height_px, 0)  # flip Y once: screen Y is down
    return figure, axis


def _finalize_figure(figure, axis, output_stem: Path) -> None:
    axis.set_aspect("equal")
    axis.axis("off")
    with mpl.rc_context({"svg.fonttype": "path"}):
        for extension in (".png", ".svg"):
            figure.savefig(
                _output_file(output_stem, extension),
                dpi=DEFAULT_DPI,
                bbox_inches="tight",
                pad_inches=0.02,
            )
    plt.close(figure)


def _to_canvas(x: float, y: float, view_box: ViewBox, pixel_scale: float):
    return (
        _to_canvas_x(x, view_box, pixel_scale),
        _to_canvas_y(y, view_box, pixel_scale),
    )


def _to_canvas_x(x: float, view_box: ViewBox, pixel_scale: float) -> float:
    return (x - view_box.min_x) * pixel_scale


def _to_canvas_y(y: float, view_box: ViewBox, pixel_scale: float) -> float:
    return (view_box.max_y - y) * pixel_scale


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _normalized_output_stem(path_plot_stem: str) -> Path:
    path = Path(path_plot_stem)
    if path.suffix.lower() in {".png", ".svg"}:
        path = path.with_suffix("")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _output_file(stem: Path, extension: str) -> Path:
    return Path(f"{stem}{extension}")


def _float_attr(element, key: str, default: float = 0.0) -> float:
    if element is None:
        return default
    value = element.get(key)
    if value in (None, ""):
        return default
    return float(str(value).replace(",", "."))


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _find_child_local(element, name: str):
    if element is None:
        return None
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _find_children_local(element, name: str):
    if element is None:
        return []
    return [child for child in list(element) if _local_name(child.tag) == name]
