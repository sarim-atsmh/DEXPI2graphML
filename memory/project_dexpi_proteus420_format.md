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

**STATUS (done 2026-06-14):** `dexpi_xml_renderer.py` was fully rewritten (1643→~430
lines) as a single `_render_plantmodel` renderer for this format. `dxf_renderer.py`
and `assets/dxf_components/` (185 files) were deleted; `plot_graph`/`plot_graph2` and
the no-match graph fallback are gone. `functions.render_plot(Path_dexpi, Path_plot)`
is the entry. Verified rendering the sample to PNG/SVG. STILL TODO: the input files
are switching to this format too, so `Dexpi2graph` (DEXPI→GraphML conversion in
functions.py) needs porting to read PlantModel/PipingNetworkSystem topology.

**Why it broke before the rewrite:** `_is_xmplant_bbox_root` matched on PlantModel +
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

**Confirmed from real sample** (`.../ConvertingDXFtoDEXPI/out/PA-A11090-001-3/PA-A11090-001-3.dexpi.xml`, 3599 lines, ~84 instances C-001..C-146, ~50 segments):
- Catalogue uses `<Line>` (2 coords), `<PolyLine>`, `<Circle><Position><Location/></Position><Radius Value="r"/></Circle>`, `<Text X Y Z Height>body</Text>`. No `<Shape>`, no `<Presentation>`/colors, no `<Arc>` (tessellated into PolyLine).
- DATA QUIRK: a few catalogue `Extent`s carry absurd WCS coords (e.g. `shape-ball_valve_with_flange_closed` Min X≈2654) while its geometry coords match — don't trust catalogue Extent for sizing; use the primitive coords.
- Instances: every one here has `ComponentName` (no `SHAPE_MISSING` in this file, but still implement the placeholder path). Rotation comes via `Reference` unit vector incl. 90°/180°/270° (e.g. `(0,1)`, `(-1,0)`, `(0,-1)`); non-uniform `Scale` is common (e.g. `1.75,2.0`; `2.26,1.14`).
- Arrowheads are real `ProcessInstrumentationFunction` instances (`ComponentName="arrow_head"`/`arrow_head_small`) oriented purely by `Reference` — no special arrow heuristics needed for this format.
- `PipingNetworkSystem/PipingNetworkSegment`: `Connection FromID/FromNode/ToID/ToNode` (FromNode/ToNode are "1"/"2" = N1/N2 nozzles). Self-loop segments (`FromID==ToID`) are common = stubs/T-junction pieces. `CenterLine` has exactly 2 world-coord Coordinates per segment. Segment `GenericAttributes`: `PIPENO` + optional `FlowDirectionSpecialization` (Forward/Reverse/DualFlowPipingNetworkSegment).

Related: [[project_arrowhead_connection_fix]].
