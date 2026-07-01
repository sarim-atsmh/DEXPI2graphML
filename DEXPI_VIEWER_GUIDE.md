# Viewer guide: parsing & rendering the `*.dexpi.xml` output

This describes exactly how to render the DEXPI Proteus files produced by
`dxf_to_dexpi.export.export_proteus_xml` (e.g. `out/PA-A11090-001-3/PA-A11090-001-3.dexpi.xml`).
It is a DEXPI Proteus 4.2.0 document. The renderer's job: build a symbol library
from `ShapeCatalogue`, then place each instance with its own transform. **No
heuristics for rotation/scale are needed — every instance carries them.**

## 1. Document model
Root is `<PlantModel>` (no XML namespace). Direct children, in order:

| Element | Meaning |
|---|---|
| `PlantInformation` | header (SchemaVersion, Discipline=PID, Is3D=no, Units, ExportMode) |
| `ShapeCatalogue` | the symbol library — geometry definitions in **local** coords |
| `Drawing` | the sheet frame; its `Extent` is the overall drawing bounds |
| `PipingComponent` / `ProcessInstrumentationFunction` / `Equipment` | **component instances** (placed) |
| `PipingNetworkSystem` | pipe segments (centerlines + connections) |

> **Gotcha #1:** `ShapeCatalogue` contains children with the *same tag names* as
> instances (`PipingComponent`, …). Do **not** do `root.findall('.//PipingComponent')`
> — that returns catalogue entries too. Iterate **direct children of `PlantModel`**
> and skip the `ShapeCatalogue` subtree.

## 2. Linking an instance to its symbol
An instance references its catalogue geometry by **(element tag, `ComponentName`)**.
Example: instance `<PipingComponent … ComponentName="ZV">` is drawn with the
catalogue entry `<PipingComponent ComponentName="ZV" ID="shape-ZV">`.

Build a lookup once: `catalogue[(tag, ComponentName)] -> entry`. For each instance,
look up `(instance.tag, instance.ComponentName)`.

- If `ComponentName` is **absent**, the symbol had no DXF geometry (see §7) — draw a
  placeholder, don't look it up.

## 3. The placement transform (the core of the renderer)
Catalogue geometry is in the symbol's **own local coordinates, re-centred so the
origin `(0,0)` is the symbol's bbox centre** (the exporter does this because each
instance's `Location` is the placed-bbox centre). Each instance carries:

```xml
<Position>
  <Location  X="0.358646" Y="0.367836" Z="0"/>   <!-- translation (drawing coords) -->
  <Axis      X="0" Y="0" Z="1"/>                  <!-- rotation axis: +Z, CCW positive -->
  <Reference X="1.0" Y="0.0" Z="0"/>              <!-- rotation as a unit vector (cosθ, sinθ) -->
</Position>
<Scale X="1.0" Y="1.0" Z="1"/>                    <!-- per-axis scale, applied in local frame -->
```

For a local point `p = (x, y)` from the catalogue, compute the world point in this
**exact order — scale, then rotate, then translate**:

```
cosθ = Reference.X        # Reference is already a unit vector
sinθ = Reference.Y

sx, sy = Scale.X * x, Scale.Y * y          # 1) scale (local)
rx = sx*cosθ - sy*sinθ                     # 2) rotate about +Z
ry = sx*sinθ + sy*cosθ
wx, wy = Location.X + rx, Location.Y + ry  # 3) translate
```

That ordering matters: at a 90° rotation the exporter deliberately keeps `Scale≈(1,1)`
and lets the rotation produce the footprint swap, so scaling **must** happen before
rotating. `θ = atan2(Reference.Y, Reference.X)` if you prefer an angle.

## 4. Geometry primitives (children of a catalogue entry)
All coordinates are local; transform every point with §3.

| Element | Shape | Notes |
|---|---|---|
| `<Line>` | 2 `<Coordinate>` | straight segment |
| `<PolyLine>` | N `<Coordinate>` | open or closed; **closed ones already repeat the first point** as the last — just draw the point sequence |
| `<Circle>` | `<Position><Location/></Position><Radius Value=r/>` | center is local; see ellipse note below |
| `<Text>` | `X Y Z Height` attrs, text in element body | label baked into the symbol (e.g. tag letters) |
| `<Extent>` | `<Min/><Max/>` | the symbol's local bounding box (for culling/centring) |

- **Arcs:** there is no Arc element — arcs were tessellated into `<PolyLine>` at export.
  So a viewer only needs Line/PolyLine/Circle/Text.
- **Circle under non-uniform scale** (`Scale.X != Scale.Y`): it becomes an **ellipse**
  with semi-axes `(Scale.X*r, Scale.Y*r)` rotated by θ. If you only support circles,
  using `r*Scale.X` is an acceptable approximation.
- **Text:** transform the position with §3; scale `Height` by `Scale.Y` (or the mean of
  X/Y) and rotate the baseline by θ.

## 5. Nozzles (connection points)
Inside an instance:
```xml
<Nozzle ID="C-001-N1">
  <Position><Location X="0.351646" Y="0.367836" Z="0"/></Position>
  <Node ID="C-001-N1-node"/>
</Nozzle>
```
`Location` here is already in **drawing/world coordinates** (not local) — draw/snap
directly, no transform. Use the `Node` ID as the connection anchor.

## 6. Pipe network
```xml
<PipingNetworkSystem ID="PNS-1">
  <PipingNetworkSegment ID="CONN-0001" TagName="PL-001">
    <Connection FromID="C-001" FromNode="1" ToID="C-002" ToNode="2"/>
    <CenterLine><Coordinate .../><Coordinate .../></CenterLine>
    <GenericAttributes>…PIPENO, NOMINAL_DIAMETER, FLUID_CODE, FlowDirection…</GenericAttributes>
  </PipingNetworkSegment>
</PipingNetworkSegment>
```
- `CenterLine` coordinates are in **drawing/world coordinates** — draw the polyline as-is
  (no transform). These are the real pipe routes; do **not** synthesize orthogonal routes.
- `Connection` links two component instances by `FromID`/`ToID`. Use it for topology.
- Flow direction, line number, diameter etc. live in the segment's `GenericAttributes`.

## 7. Missing-symbol & skipped instances
- **Missing symbol:** instance has **no `ComponentName`** and a generic attribute
  `SHAPE_MISSING="true"`. It still has a valid `<Extent>` (world coords) and `<Position>`.
  Render a **placeholder** — e.g. a rectangle from `Extent` with the `TagName`/`ID` as a
  label. When a real DXF is added later, this instance will start carrying `ComponentName`
  automatically; no viewer change needed.
- **Skipped symbols** (pure annotations/labels) are simply **not present** in the file.
- `conversion_report.json → shape_catalogue` lists `missing_symbols`, `skipped_symbols`,
  and `aspect_warnings` (instances with suspicious bbox/scale data) for diagnostics.

## 8. Coordinate system & the global view transform
- All world coordinates are in the **original drawing units**, **Y-up** (math convention).
- For a screen, apply **one** global transform to the whole scene (this is the only global
  scaling the renderer should do — symbol scale is already per-instance):
  1. translate by `-Drawing/Extent/Min`
  2. one **uniform** scale to fit the viewport
  3. **flip Y once** (screen Y is down)
- `Drawing/Extent` (and each instance/segment lives within it) gives the fit box.
- Don't re-anchor or per-symbol-rescale on screen; the document is already self-consistent.

## 9. Gotchas / non-goals
- **Instance `Extent` is world coords; catalogue-entry `Extent` is local coords.** Don't mix.
- `ComponentClassURI` uses the DEXPI **sandbox** RDL namespace (`sandbox.dexpi.org/rdl/…`);
  treat it as a semantic class label, not a guaranteed-resolvable URL.
- `GenericAttributes Set="dxf_to_dexpi"` mixes our custom attrs (`SOURCE_SYMBOL`, …) with
  DEXPI predefined ones (`…Specialization` names with `AttributeURI`). Ignore unknown names.
- `Units` may be `"unknown"` if the source drawing lacked units — coordinates are still
  internally consistent; only label/measurement display is affected.
- A placeholder symbol (alias) renders the stand-in glyph but keeps the **real**
  `ComponentName`/`ComponentClass` — semantics are correct even when the picture is temporary.

## Minimal render loop (pseudocode)
```
doc = parse(file)
catalogue = { (e.tag, e.ComponentName): e for e in doc.ShapeCatalogue }
fit = global_transform(doc.Drawing.Extent, viewport)   # translate, uniform scale, flip Y

for inst in direct_children(doc) where tag in {PipingComponent, ProcessInstrumentationFunction, Equipment}:
    if inst.ComponentName and (inst.tag, inst.ComponentName) in catalogue:
        M = instance_transform(inst.Position, inst.Scale)   # §3
        for prim in catalogue[(inst.tag, inst.ComponentName)]:
            draw(fit ∘ M ∘ prim)                            # local -> world -> screen
    else:
        draw_placeholder(fit ∘ rect(inst.Extent), label=inst.TagName or inst.ID)
    for noz in inst.Nozzle: draw_node(fit ∘ noz.Location)   # already world coords

for seg in doc.PipingNetworkSystem.PipingNetworkSegment:
    draw_polyline(fit ∘ seg.CenterLine)                     # already world coords
```
