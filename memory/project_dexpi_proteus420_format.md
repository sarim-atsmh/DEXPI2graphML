---
name: project_dexpi_proteus420_format
description: New dxf_to_dexpi Proteus 4.2.0 (.dexpi.xml) format is misclassified by the renderer; what the format is and what needs updating
metadata:
  type: project
---

`DEXPI_VIEWER_GUIDE.md` (added 2026-06-14) specifies a NEW input format the
renderer must handle: the Proteus 4.2.0 document produced by
`dxf_to_dexpi.export.export_proteus_xml` (the reverse pipeline; this repo is the
DEXPI→GraphML direction). It is distinct from all three pathways in
`dexpi_xml_renderer.py` (proteusxml / xmplant_bbox / graphical_dexpi).

**The format:** root `<PlantModel>` (no namespace). Children in order:
`PlantInformation`, `ShapeCatalogue` (symbol geometry in LOCAL coords),
`Drawing` (has `Extent` = overall bounds), then instances
(`PipingComponent` / `ProcessInstrumentationFunction` / `Equipment`) and
`PipingNetworkSystem`. Instances link to catalogue by `(tag, ComponentName)`
and carry a full transform: `Position` (Location=translate, Reference=(cosθ,sinθ)
unit vector, Axis=+Z) + `Scale`. Apply **scale → rotate → translate** (matches
existing `Transform.apply`). Nozzle `Location` and `CenterLine`/segment coords are
already WORLD coords (no transform). Missing symbols have no `ComponentName` +
`SHAPE_MISSING="true"` + world-coord `Extent` → draw placeholder rect.

**Why it breaks today:** `_is_xmplant_bbox_root` matches on PlantModel +
PipingComponent + PipingNetworkSegment + GenericAttribute + Position + Extent —
ALL present in the new format — and is checked BEFORE graphical_dexpi in
`render_dexpi_plot`. So the new format routes to `_render_xmplant_bbox` (bbox +
DXF-asset-library fallback), ignoring the inline ShapeCatalogue geometry entirely.
It's also gated behind `include_xmplant=False` → returns without drawing.

**How to apply (update plan):**
1. Add a detector (PlantModel + ShapeCatalogue containing geometry + instances
   with ComponentName) and dispatch it BEFORE `_is_xmplant_bbox_root`.
2. Key the catalogue map by `(tag, ComponentName)`, not ComponentName alone
   (`_build_component_map` currently collides across element types).
3. Extend `_draw_primitive`/`PRIMITIVE_TAGS` for the guide's §4 primitives:
   `<Line>` (2 coords, NOT currently handled), `<Circle>` radius is child
   `<Radius Value=r/>` (code reads a `Radius` attribute), `<Text>` content in
   element body + X/Y/Z/Height attrs (code reads `String` attr + Position/Location).
4. Use `Drawing/Extent` Min/Max for the view box (already supported by
   `_extract_view_box`; xmplant path ignores it).
5. Draw `PipingNetworkSegment/CenterLine` polylines and `Nozzle` anchors in WORLD
   coords (no transform); placeholders from instance `Extent` for missing symbols.

Related: [[project_arrowhead_connection_fix]].
