# parse_bbmodel.py

AI-oriented usage contract for `parse_bbmodel.py`.

The script parses Blockbench `.bbmodel` JSON files and can emit:

- `normalized`: full parsed structure for analysis.
- `geo`: generated Bedrock `minecraft:geometry` JSON.
- `animations`: generated Bedrock animation JSON.
- `textures`: texture reference/extraction records.
- `manifest`: a compact routing file that tells downstream tools where outputs are.
- `all`: all payloads above in one JSON object.

No third-party dependencies are required.

## Quick Start

```bash
python3 parse_bbmodel.py model.bbmodel
```

Print normalized JSON:

```bash
python3 parse_bbmodel.py model.bbmodel --format json
```

Print generated geometry JSON:

```bash
python3 parse_bbmodel.py model.bbmodel --format json --json-kind geo
```

Export all useful files into one directory:

```bash
python3 parse_bbmodel.py model.bbmodel \
  --export-dir out/model_export \
  --texture-prefix textures/blocks
```

Explicitly choose output locations:

```bash
python3 parse_bbmodel.py model.bbmodel \
  --normalized-json out/model.normalized.json \
  --geo-json out/model.geo.json \
  --animation-json out/model.animation.json \
  --texture-dir out/textures \
  --texture-prefix textures/blocks \
  --manifest-json out/model.manifest.json
```

## CLI Contract

```text
python3 parse_bbmodel.py FILE [FILE ...] [OPTIONS]
```

Inputs:

- `FILE`: one or more `.bbmodel` files.
- `.bbmodel` must be UTF-8 JSON.

Primary stdout options:

| Option | Values | Default | Meaning |
| --- | --- | --- | --- |
| `--format` | `summary`, `json` | `summary` | Print human summary or machine JSON to stdout. |
| `--json-kind` | `normalized`, `geo`, `animations`, `textures`, `manifest`, `all` | `normalized` | Select stdout JSON payload. Only used with `--format json`. |

File output options:

| Option | Meaning |
| --- | --- |
| `--export-dir DIR` | Convenience mode. Writes normalized, geo, animation, manifest JSON, and textures under `DIR`. |
| `--normalized-json PATH` | Write normalized parser JSON. Alias: `--model-json`. |
| `--geo-json PATH` | Write generated Bedrock geometry JSON. |
| `--animation-json PATH` | Write generated Bedrock animation JSON. |
| `--manifest-json PATH` | Write export manifest JSON. |
| `--texture-dir DIR` | Extract embedded base64 textures into `DIR`. |
| `--extract-textures DIR` | Backward-compatible alias of `--texture-dir`. |
| `--texture-prefix PREFIX` | Logical texture path prefix recorded in JSON, for example `textures/blocks`. |

Generation options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--identifier ID` | source model identifier | Override geometry identifier. Single input only. |
| `--animation-prefix PREFIX` | `animation` | Prefix generated animation names when missing. |
| `--geo-format-version VERSION` | `1.12.0` | `format_version` for generated geometry JSON. |
| `--animation-format-version VERSION` | `1.8.0` | `format_version` for generated animation JSON. |

Summary-only options:

| Option | Meaning |
| --- | --- |
| `--no-elements` | Hide element list in summary output. |
| `--no-outliner` | Hide outliner tree in summary output. |

## Multi-File Behavior

Multiple inputs are supported:

```bash
python3 parse_bbmodel.py models/a.bbmodel models/b.bbmodel --export-dir out
```

Rules:

- With `--format json`, stdout becomes a JSON array.
- With `--export-dir out`, outputs are named from each input stem:
  - `out/a.normalized.json`
  - `out/a.geo.json`
  - `out/a.animation.json`
  - `out/a.manifest.json`
- Textures go under `out/textures/<input_stem>/` for multiple inputs.
- If multiple inputs are used, explicit JSON output targets such as `--geo-json` must be directories, not single `.json` files.
- `--identifier` is only valid for one input file.

## JSON Kinds

### normalized

Purpose: loss-minimized analysis payload.

Top-level fields:

```json
{
  "file": "model.bbmodel",
  "name": "model",
  "model_identifier": "model",
  "meta": {},
  "resolution": {},
  "visible_box": [],
  "bounds": {},
  "element_count": 0,
  "group_count": 0,
  "texture_count": 0,
  "animation_count": 0,
  "elements": [],
  "groups": [],
  "textures": [],
  "animations": [],
  "outliner": []
}
```

Use this when an AI needs to reason about original Blockbench structure.

### geo

Purpose: generated Bedrock geometry JSON.

Top-level shape:

```json
{
  "format_version": "1.12.0",
  "minecraft:geometry": [
    {
      "description": {
        "identifier": "geometry.model",
        "texture_width": 64,
        "texture_height": 64
      },
      "bones": []
    }
  ]
}
```

Conversion notes:

- Outliner groups become bones.
- Ungrouped cubes are placed in a generated `root` bone.
- Element `from` becomes cube `origin`.
- Element `to - from` becomes cube `size`.
- Element rotation becomes cube `pivot` and `rotation`.
- Face UV `[x1, y1, x2, y2]` becomes `{ "uv": [x1, y1], "uv_size": [x2-x1, y2-y1] }`.

### animations

Purpose: generated Bedrock animation JSON.

Top-level shape:

```json
{
  "format_version": "1.8.0",
  "animations": {
    "animation.name": {
      "animation_length": 1,
      "loop": true,
      "bones": {}
    }
  }
}
```

Conversion notes:

- Reads Blockbench animation data from `animations[].animators[bone_uuid].keyframes[]`.
- Bone names come from animator names.
- Keyframe `channel` becomes a bone channel, such as `rotation`, `position`, or `scale`.
- Keyframe `time` becomes the animation time key.
- Keyframe data point `{x,y,z}` becomes `[x,y,z]`.
- Non-linear interpolation is preserved as `lerp_mode` where possible.

### textures

Purpose: list texture locations for downstream copy/reference logic.

Shape:

```json
[
  {
    "index": 0,
    "id": "0",
    "uuid": "...",
    "name": "texture",
    "width": 128,
    "height": 128,
    "uv_width": 64,
    "uv_height": 64,
    "source_path": "",
    "embedded_source": true,
    "extracted_path": "out/textures/texture.png",
    "logical_path": "textures/blocks/texture.png"
  }
]
```

`extracted_path` is only set when `--texture-dir`, `--extract-textures`, or `--export-dir` extracts an embedded texture.

### manifest

Purpose: small routing file for agents and build scripts.

Shape:

```json
{
  "source": "model.bbmodel",
  "name": "model",
  "model_identifier": "model",
  "outputs": {
    "normalized_json": "out/model.normalized.json",
    "geo_json": "out/model.geo.json",
    "animation_json": "out/model.animation.json"
  },
  "counts": {
    "elements": 0,
    "groups": 0,
    "textures": 0,
    "animations": 0
  },
  "textures": []
}
```

Recommended downstream behavior: read `manifest` first, then use the paths in `outputs` and `textures`.

## Common Recipes

Inspect model structure:

```bash
python3 parse_bbmodel.py model.bbmodel --format json --json-kind normalized
```

Generate only geometry JSON to stdout:

```bash
python3 parse_bbmodel.py model.bbmodel --format json --json-kind geo
```

Generate only animation JSON to stdout:

```bash
python3 parse_bbmodel.py model.bbmodel --format json --json-kind animations
```

Export geometry and animations to separate files:

```bash
python3 parse_bbmodel.py model.bbmodel \
  --geo-json out/geometry/model.geo.json \
  --animation-json out/animations/model.animation.json
```

Extract textures and record logical texture locations:

```bash
python3 parse_bbmodel.py model.bbmodel \
  --texture-dir out/textures \
  --texture-prefix textures/blocks \
  --format json \
  --json-kind textures
```

Batch export many models:

```bash
python3 parse_bbmodel.py models/*.bbmodel \
  --export-dir out/exported \
  --texture-prefix textures/blocks
```

## Caveats

- The script is a parser/export helper, not a full Blockbench renderer.
- `bounds` is computed from element `from` and `to`; rotated bounds are not expanded into world-space bounds.
- External texture files are not copied unless they are embedded as base64 in `.bbmodel`.
- Generated `geo` and `animations` JSON are intended as practical Bedrock-style output. If a target engine requires a stricter schema, use `normalized` as the source of truth and adapt downstream.
