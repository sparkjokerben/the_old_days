---
name: parse-bbmodel
description: Parse and convert Blockbench .bbmodel source files into Bedrock-style JSON — generated minecraft:geometry, keyframe animations, extracted embedded textures, and a normalized analysis payload. Use this whenever the input is a .bbmodel file (or a Blockbench model the user wants turned into Bedrock/ModSDK assets): inspecting a model's elements/bones/structure, generating a .geo.json, converting Blockbench keyframe animations to Bedrock animation JSON, pulling out embedded textures, or batch-converting many models — trigger it even when the user says "bb model" or names a model file without the .bbmodel extension.
---

# parse-bbmodel

Parse Blockbench `.bbmodel` JSON and emit Bedrock-style outputs using the bundled
`scripts/parse_bbmodel.py`. The script is self-contained pure Python 3 — no third-party
dependencies, no network. Prefer running it over hand-parsing `.bbmodel` JSON: it handles
outliner→bones, UV conversion, rotation/pivot, keyframe→animation, and base64 texture
extraction consistently.

## When to use which output

The script emits several payloads. Pick by what the user actually needs:

- **normalized** — full parsed structure (elements, groups, textures, animations, outliner).
  Use when reasoning about or explaining a model's structure, or as the source of truth to
  adapt downstream if a target engine needs a stricter schema.
- **geo** — generated Bedrock `minecraft:geometry` JSON. Use to produce a `.geo.json`.
- **animations** — generated Bedrock animation JSON from Blockbench keyframes.
- **textures** — texture reference/extraction records (paths, sizes, embedded flag).
- **manifest** — compact routing file listing where the exported files landed. Downstream
  tools/agents should read this first, then follow `outputs` and `textures` paths.
- **all** — every payload above in one JSON object.

## Core commands

Run the script with `python3`. Paths below are relative to this skill directory; use the
absolute path to `scripts/parse_bbmodel.py` when invoking from elsewhere.

Inspect a model (human summary):

```bash
python3 scripts/parse_bbmodel.py model.bbmodel
```

Get a specific JSON payload to stdout (for programmatic reasoning):

```bash
python3 scripts/parse_bbmodel.py model.bbmodel --format json --json-kind geo
```

`--json-kind` accepts `normalized` (default), `geo`, `animations`, `textures`, `manifest`, `all`.

Export everything into one directory (normalized + geo + animation + manifest + textures):

```bash
python3 scripts/parse_bbmodel.py model.bbmodel \
  --export-dir out/model_export \
  --texture-prefix textures/blocks
```

Write specific outputs to specific paths:

```bash
python3 scripts/parse_bbmodel.py model.bbmodel \
  --geo-json out/model.geo.json \
  --animation-json out/model.animation.json \
  --texture-dir out/textures --texture-prefix textures/blocks
```

Batch-convert many models (with multiple inputs, `--export-dir` names outputs per input
stem, and explicit `--geo-json`/etc. targets must be **directories**, not `.json` files):

```bash
python3 scripts/parse_bbmodel.py models/*.bbmodel --export-dir out/exported --texture-prefix textures/blocks
```

## Guidance

- When the user just wants to understand a model, run the summary or `--json-kind normalized`
  first and describe what you find before generating anything.
- When generating geometry/animation for a Bedrock ModSDK project, prefer `--export-dir` so the
  manifest records every output path, then report those paths back.
- Textures embedded as base64 are extracted only when `--texture-dir`, `--extract-textures`, or
  `--export-dir` is used. External (non-embedded) texture files are not copied — say so if the
  model references external textures.
- Override the geometry identifier with `--identifier` (single input only); set format versions
  with `--geo-format-version` / `--animation-format-version` when a target requires it.

## Full reference

`references/usage.md` is the complete CLI contract: every option, multi-file rules, exact JSON
shapes for each payload, conversion notes (UV, rotation, keyframe interpolation), and caveats.
Read it when you need an option not shown above or the precise output schema.
