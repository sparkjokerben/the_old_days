#!/usr/bin/env python3
"""
Parse Blockbench .bbmodel files.

The .bbmodel format is JSON. This script reads the common Blockbench fields and
prints either a human-readable summary or a normalized JSON document.

Usage:
  python3 parse_bbmodel.py model.bbmodel
  python3 parse_bbmodel.py a.bbmodel b.bbmodel
  python3 parse_bbmodel.py model.bbmodel --format json
  python3 parse_bbmodel.py model.bbmodel --format json --json-kind geo
  python3 parse_bbmodel.py model.bbmodel --geo-json model.geo.json --animation-json model.animation.json
  python3 parse_bbmodel.py model.bbmodel --extract-textures ./textures
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;,]+)?(?:;[^,]*)?;base64,(?P<data>.+)$")


def as_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def parse_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
        return number
    return None


def clean_number(value: float | int) -> float | int:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def as_vector(value: Any) -> list[float | int] | None:
    if not isinstance(value, list):
        return None
    vector: list[float | int] = []
    for item in value:
        number = as_number(item)
        if number is None:
            return None
        vector.append(number)
    return vector


def vector_delta(to_value: Any, from_value: Any) -> list[float | int] | None:
    to_vector = as_vector(to_value)
    from_vector = as_vector(from_value)
    if to_vector is None or from_vector is None or len(to_vector) != len(from_vector):
        return None
    return [to_vector[index] - from_vector[index] for index in range(len(to_vector))]


def element_bounds(element: JsonDict) -> JsonDict | None:
    from_vector = as_vector(element.get("from"))
    to_vector = as_vector(element.get("to"))
    if from_vector is None or to_vector is None or len(from_vector) != 3 or len(to_vector) != 3:
        return None

    minimum = [min(from_vector[index], to_vector[index]) for index in range(3)]
    maximum = [max(from_vector[index], to_vector[index]) for index in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[index] - minimum[index] for index in range(3)],
    }


def model_bounds(elements: list[JsonDict]) -> JsonDict | None:
    bounds = [element.get("bounds") for element in elements if isinstance(element.get("bounds"), dict)]
    if not bounds:
        return None

    minimum = [
        min(bound["min"][axis] for bound in bounds if isinstance(bound.get("min"), list))
        for axis in range(3)
    ]
    maximum = [
        max(bound["max"][axis] for bound in bounds if isinstance(bound.get("max"), list))
        for axis in range(3)
    ]
    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[index] - minimum[index] for index in range(3)],
    }


def safe_filename(name: str, fallback: str) -> str:
    candidate = Path(name).name.strip() or fallback
    candidate = re.sub(r"[^\w._-]+", "_", candidate, flags=re.UNICODE)
    return candidate or fallback


def normalize_path_text(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def join_logical_path(prefix: str | None, filename: str) -> str:
    if not prefix:
        return filename
    return f"{normalize_path_text(prefix)}/{filename}"


def json_time_key(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return str(value)
    return str(clean_number(number))


def model_stem(model: JsonDict) -> str:
    source_name = Path(str(model.get("file") or "model")).stem
    return safe_filename(str(model.get("name") or source_name), safe_filename(source_name, "model"))


def bedrock_identifier(model: JsonDict, override: str | None = None) -> str:
    raw = str(override or model.get("model_identifier") or model.get("name") or model_stem(model)).strip()
    if not raw:
        raw = model_stem(model)
    if raw.startswith("geometry."):
        return raw
    return f"geometry.{raw}"


def load_bbmodel(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def normalize_element(element: JsonDict) -> JsonDict:
    faces = element.get("faces")
    normalized_faces: dict[str, Any] = {}
    if isinstance(faces, dict):
        for direction, face in faces.items():
            if isinstance(face, dict):
                normalized_faces[direction] = {
                    "uv": face.get("uv"),
                    "texture": face.get("texture"),
                    "rotation": face.get("rotation"),
                    "enabled": face.get("enabled", True),
                }
            else:
                normalized_faces[direction] = face

    normalized: JsonDict = {
        "uuid": element.get("uuid"),
        "name": element.get("name"),
        "type": element.get("type", "cube"),
        "export": element.get("export", True),
        "box_uv": element.get("box_uv"),
        "render_order": element.get("render_order"),
        "from": element.get("from"),
        "to": element.get("to"),
        "size": vector_delta(element.get("to"), element.get("from")),
        "bounds": element_bounds(element),
        "inflate": element.get("inflate", 0),
        "origin": element.get("origin"),
        "rotation": element.get("rotation"),
        "color": element.get("color"),
        "face_count": len(normalized_faces),
        "textures_used": sorted(
            {
                face.get("texture")
                for face in normalized_faces.values()
                if isinstance(face, dict) and face.get("texture") is not None
            },
            key=str,
        ),
        "faces": normalized_faces,
    }

    # Mesh elements use vertices/faces instead of cube from/to bounds.
    if "vertices" in element:
        normalized["vertices"] = element.get("vertices")
    if "mesh" in element:
        normalized["mesh"] = element.get("mesh")

    return normalized


def normalize_texture(texture: JsonDict, index: int) -> JsonDict:
    source = texture.get("source")
    embedded = isinstance(source, str) and source.startswith("data:")
    return {
        "index": index,
        "uuid": texture.get("uuid"),
        "id": texture.get("id"),
        "name": texture.get("name"),
        "path": texture.get("path"),
        "relative_path": texture.get("relative_path"),
        "namespace": texture.get("namespace"),
        "folder": texture.get("folder"),
        "width": texture.get("width"),
        "height": texture.get("height"),
        "uv_width": texture.get("uv_width"),
        "uv_height": texture.get("uv_height"),
        "file_format": texture.get("file_format"),
        "visible": texture.get("visible"),
        "internal": texture.get("internal"),
        "use_as_default": texture.get("use_as_default"),
        "particle": texture.get("particle"),
        "render_mode": texture.get("render_mode"),
        "render_sides": texture.get("render_sides"),
        "wrap_mode": texture.get("wrap_mode"),
        "mode": texture.get("mode"),
        "embedded_source": embedded,
        "source_bytes_base64": len(source) if embedded else 0,
    }


def normalize_group(group: JsonDict, index: int) -> JsonDict:
    return {
        "index": index,
        "uuid": group.get("uuid"),
        "name": group.get("name"),
        "export": group.get("export", True),
        "origin": group.get("origin"),
        "rotation": group.get("rotation"),
        "color": group.get("color"),
        "visibility": group.get("visibility"),
        "shade": group.get("shade"),
        "mirror_uv": group.get("mirror_uv"),
        "autouv": group.get("autouv"),
    }


def normalize_keyframe(keyframe: JsonDict) -> JsonDict:
    return {
        "uuid": keyframe.get("uuid"),
        "channel": keyframe.get("channel"),
        "time": keyframe.get("time"),
        "interpolation": keyframe.get("interpolation"),
        "data_points": keyframe.get("data_points") or [],
    }


def keyframes_from_animator(animator: JsonDict) -> list[JsonDict]:
    keyframes = animator.get("keyframes")
    if not isinstance(keyframes, list):
        return []
    return [
        normalize_keyframe(keyframe)
        for keyframe in keyframes
        if isinstance(keyframe, dict)
    ]


def normalize_animation(animation: JsonDict, index: int) -> JsonDict:
    animators = animation.get("animators")
    animator_map = animators if isinstance(animators, dict) else {}

    channels: dict[str, int] = {}
    times: list[float] = []
    normalized_animators: list[JsonDict] = []
    keyframe_total = 0

    for bone_uuid, animator in animator_map.items():
        if not isinstance(animator, dict):
            continue

        keyframe_list = keyframes_from_animator(animator)
        keyframe_total += len(keyframe_list)
        animator_channels: dict[str, int] = {}

        for keyframe in keyframe_list:
            channel = str(keyframe.get("channel", "unknown"))
            channels[channel] = channels.get(channel, 0) + 1
            animator_channels[channel] = animator_channels.get(channel, 0) + 1
            time_value = as_number(keyframe.get("time"))
            if time_value is not None:
                times.append(float(time_value))

        normalized_animators.append(
            {
                "bone_uuid": bone_uuid,
                "name": animator.get("name"),
                "type": animator.get("type"),
                "rotation_global": animator.get("rotation_global"),
                "quaternion_interpolation": animator.get("quaternion_interpolation"),
                "keyframe_count": len(keyframe_list),
                "channels": animator_channels,
                "keyframes": keyframe_list,
            }
        )

    return {
        "index": index,
        "uuid": animation.get("uuid"),
        "name": animation.get("name"),
        "loop": animation.get("loop"),
        "override": animation.get("override"),
        "length": animation.get("length"),
        "snapping": animation.get("snapping"),
        "animator_count": len(normalized_animators),
        "keyframe_count": keyframe_total,
        "channels": channels,
        "first_keyframe_time": min(times) if times else None,
        "last_keyframe_time": max(times) if times else None,
        "animators": normalized_animators,
    }


def normalize_outliner_node(
    node: Any,
    elements_by_uuid: dict[str, JsonDict],
    groups_by_uuid: dict[str, JsonDict],
) -> JsonDict:
    if isinstance(node, str):
        element = elements_by_uuid.get(node)
        if element is None:
            return {"kind": "missing_element", "uuid": node}
        return {
            "kind": "element",
            "uuid": node,
            "name": element.get("name"),
            "type": element.get("type", "cube"),
        }

    if isinstance(node, dict):
        uuid = node.get("uuid")
        group = groups_by_uuid.get(str(uuid)) if uuid is not None else None
        children = node.get("children")
        child_list = children if isinstance(children, list) else []
        return {
            "kind": "group",
            "uuid": uuid,
            "name": node.get("name") or (group or {}).get("name"),
            "origin": node.get("origin") or (group or {}).get("origin"),
            "rotation": node.get("rotation") or (group or {}).get("rotation"),
            "export": (group or {}).get("export"),
            "visibility": (group or {}).get("visibility"),
            "children": [
                normalize_outliner_node(child, elements_by_uuid, groups_by_uuid)
                for child in child_list
            ],
        }

    return {"kind": "unknown", "value": node}


def normalize_model(data: JsonDict, source_path: Path) -> JsonDict:
    elements = data.get("elements")
    element_list = elements if isinstance(elements, list) else []
    normalized_elements = [
        normalize_element(element)
        for element in element_list
        if isinstance(element, dict)
    ]
    elements_by_uuid = {
        str(element["uuid"]): element
        for element in normalized_elements
        if element.get("uuid") is not None
    }

    textures = data.get("textures")
    texture_list = textures if isinstance(textures, list) else []

    groups = data.get("groups")
    group_list = groups if isinstance(groups, list) else []
    normalized_groups = [
        normalize_group(group, index)
        for index, group in enumerate(group_list)
        if isinstance(group, dict)
    ]
    groups_by_uuid = {
        str(group["uuid"]): group
        for group in normalized_groups
        if group.get("uuid") is not None
    }

    animations = data.get("animations")
    animation_list = animations if isinstance(animations, list) else []

    outliner = data.get("outliner")
    outliner_list = outliner if isinstance(outliner, list) else []

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return {
        "file": str(source_path),
        "name": data.get("name") or source_path.stem,
        "model_identifier": data.get("model_identifier"),
        "meta": {
            "format_version": meta.get("format_version"),
            "model_format": meta.get("model_format"),
            "box_uv": meta.get("box_uv"),
        },
        "front_gui_light": data.get("front_gui_light"),
        "bedrock_animation_mode": data.get("bedrock_animation_mode"),
        "resolution": data.get("resolution"),
        "visible_box": data.get("visible_box"),
        "bounds": model_bounds(normalized_elements),
        "element_count": len(normalized_elements),
        "group_count": len(normalized_groups),
        "texture_count": len(texture_list),
        "animation_count": len(animation_list),
        "elements": normalized_elements,
        "groups": normalized_groups,
        "textures": [
            normalize_texture(texture, index)
            for index, texture in enumerate(texture_list)
            if isinstance(texture, dict)
        ],
        "animations": [
            normalize_animation(animation, index)
            for index, animation in enumerate(animation_list)
            if isinstance(animation, dict)
        ],
        "outliner": [
            normalize_outliner_node(node, elements_by_uuid, groups_by_uuid)
            for node in outliner_list
        ],
    }


def compact_vector(value: Any) -> list[Any] | None:
    vector = as_vector(value)
    if vector is not None:
        return [clean_number(item) for item in vector]
    if isinstance(value, list):
        converted = []
        for item in value:
            number = parse_number(item)
            converted.append(clean_number(number) if number is not None else item)
        return converted
    return None


def nonzero_vector(value: Any) -> bool:
    vector = compact_vector(value)
    return bool(vector) and any(parse_number(item) not in (None, 0) for item in vector)


def face_to_bedrock_uv(face: Any) -> JsonDict | None:
    if not isinstance(face, dict) or face.get("enabled", True) is False:
        return None
    uv = compact_vector(face.get("uv"))
    if uv is None or len(uv) < 4:
        return None
    x1, y1, x2, y2 = uv[:4]
    width = parse_number(x2) - parse_number(x1) if parse_number(x1) is not None and parse_number(x2) is not None else 0
    height = parse_number(y2) - parse_number(y1) if parse_number(y1) is not None and parse_number(y2) is not None else 0
    return {
        "uv": [x1, y1],
        "uv_size": [clean_number(width), clean_number(height)],
    }


def element_to_bedrock_cube(element: JsonDict) -> JsonDict | None:
    origin = compact_vector(element.get("from"))
    size = vector_delta(element.get("to"), element.get("from"))
    if origin is None or size is None or len(origin) != 3 or len(size) != 3:
        return None

    cube: JsonDict = {
        "origin": origin,
        "size": [clean_number(item) for item in size],
    }

    inflate = parse_number(element.get("inflate"))
    if inflate not in (None, 0):
        cube["inflate"] = clean_number(inflate)

    if nonzero_vector(element.get("rotation")):
        cube["pivot"] = compact_vector(element.get("origin")) or origin
        cube["rotation"] = compact_vector(element.get("rotation"))

    faces = element.get("faces")
    if isinstance(faces, dict):
        uv_faces: JsonDict = {}
        for direction in ("north", "east", "south", "west", "up", "down"):
            converted = face_to_bedrock_uv(faces.get(direction))
            if converted is not None:
                uv_faces[direction] = converted
        if uv_faces:
            cube["uv"] = uv_faces

    return cube


def unique_name(raw_name: Any, used: set[str], fallback: str) -> str:
    base = str(raw_name or fallback).strip() or fallback
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def build_bedrock_bones(model: JsonDict) -> list[JsonDict]:
    elements_by_uuid = {
        str(element["uuid"]): element
        for element in model.get("elements", [])
        if isinstance(element, dict) and element.get("uuid") is not None
    }
    used_names: set[str] = set()
    bones: list[JsonDict] = []
    placed_elements: set[str] = set()

    def add_group_node(node: JsonDict, parent_name: str | None) -> str:
        bone_name = unique_name(node.get("name"), used_names, "bone")
        bone: JsonDict = {"name": bone_name}
        if parent_name:
            bone["parent"] = parent_name
        origin = compact_vector(node.get("origin"))
        if origin is not None:
            bone["pivot"] = origin
        if nonzero_vector(node.get("rotation")):
            bone["rotation"] = compact_vector(node.get("rotation"))

        cubes: list[JsonDict] = []
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            if child.get("kind") == "element":
                element_uuid = str(child.get("uuid"))
                element = elements_by_uuid.get(element_uuid)
                if element is None or element.get("export") is False:
                    continue
                cube = element_to_bedrock_cube(element)
                if cube is not None:
                    cubes.append(cube)
                    placed_elements.add(element_uuid)
            elif child.get("kind") == "group":
                add_group_node(child, bone_name)

        if cubes:
            bone["cubes"] = cubes
        bones.append(bone)
        return bone_name

    root_cubes: list[JsonDict] = []
    for node in model.get("outliner") or []:
        if not isinstance(node, dict):
            continue
        if node.get("kind") == "group":
            add_group_node(node, None)
        elif node.get("kind") == "element":
            element_uuid = str(node.get("uuid"))
            element = elements_by_uuid.get(element_uuid)
            if element is None or element.get("export") is False:
                continue
            cube = element_to_bedrock_cube(element)
            if cube is not None:
                root_cubes.append(cube)
                placed_elements.add(element_uuid)

    for element_uuid, element in elements_by_uuid.items():
        if element_uuid in placed_elements or element.get("export") is False:
            continue
        cube = element_to_bedrock_cube(element)
        if cube is not None:
            root_cubes.append(cube)

    if root_cubes:
        root_name = unique_name("root", used_names, "root")
        bones.insert(0, {"name": root_name, "pivot": [0, 0, 0], "cubes": root_cubes})

    if not bones:
        bones.append({"name": "root", "pivot": [0, 0, 0], "cubes": []})

    return bones


def first_texture_size(model: JsonDict) -> tuple[int, int]:
    resolution = model.get("resolution") if isinstance(model.get("resolution"), dict) else {}
    width = parse_number((resolution or {}).get("width"))
    height = parse_number((resolution or {}).get("height"))
    if width is not None and height is not None:
        return int(width), int(height)

    for texture in model.get("textures") or []:
        if not isinstance(texture, dict):
            continue
        width = parse_number(texture.get("uv_width") or texture.get("width"))
        height = parse_number(texture.get("uv_height") or texture.get("height"))
        if width is not None and height is not None:
            return int(width), int(height)
    return 16, 16


def build_bedrock_geometry_json(
    model: JsonDict,
    *,
    identifier: str | None = None,
    format_version: str = "1.12.0",
) -> JsonDict:
    texture_width, texture_height = first_texture_size(model)
    visible_box = model.get("visible_box") if isinstance(model.get("visible_box"), list) else []
    description: JsonDict = {
        "identifier": bedrock_identifier(model, identifier),
        "texture_width": texture_width,
        "texture_height": texture_height,
    }

    if len(visible_box) >= 2:
        width = parse_number(visible_box[0])
        height = parse_number(visible_box[1])
        if width is not None:
            description["visible_bounds_width"] = clean_number(width)
        if height is not None:
            description["visible_bounds_height"] = clean_number(height)
    if len(visible_box) >= 3:
        offset_y = parse_number(visible_box[2])
        if offset_y is not None:
            description["visible_bounds_offset"] = [0, clean_number(offset_y), 0]

    return {
        "format_version": format_version,
        "minecraft:geometry": [
            {
                "description": description,
                "bones": build_bedrock_bones(model),
            }
        ],
    }


def keyframe_data_point_to_vector(data_point: Any) -> list[Any] | None:
    if not isinstance(data_point, dict):
        return None
    vector = []
    for axis in ("x", "y", "z"):
        value = data_point.get(axis)
        number = parse_number(value)
        vector.append(clean_number(number) if number is not None else value)
    return vector


def keyframe_to_bedrock_value(keyframe: JsonDict) -> Any:
    data_points = keyframe.get("data_points")
    point_list = data_points if isinstance(data_points, list) else []
    vectors = [
        vector
        for vector in (keyframe_data_point_to_vector(point) for point in point_list)
        if vector is not None
    ]
    if not vectors:
        return [0, 0, 0]

    interpolation = keyframe.get("interpolation")
    if len(vectors) == 1 and interpolation in (None, "", "linear"):
        return vectors[0]

    value: JsonDict = {"post": vectors[-1]}
    if len(vectors) > 1:
        value["pre"] = vectors[0]
    if interpolation not in (None, "", "linear"):
        value["lerp_mode"] = interpolation
    return value


def normalize_animation_name(name: Any, prefix: str) -> str:
    raw = str(name or "animation").strip() or "animation"
    if raw.startswith(f"{prefix}."):
        return raw
    if raw.startswith("animation."):
        return raw
    return f"{prefix}.{raw}"


def build_bedrock_animation_json(
    model: JsonDict,
    *,
    animation_prefix: str = "animation",
    format_version: str = "1.8.0",
) -> JsonDict:
    animations: JsonDict = {}
    for animation in model.get("animations") or []:
        if not isinstance(animation, dict):
            continue

        animation_body: JsonDict = {}
        length = parse_number(animation.get("length"))
        if length is not None:
            animation_body["animation_length"] = clean_number(length)

        loop = animation.get("loop")
        if loop == "loop":
            animation_body["loop"] = True
        elif loop in ("hold", "hold_on_last_frame"):
            animation_body["loop"] = "hold_on_last_frame"
        elif loop:
            animation_body["loop"] = False

        bones: JsonDict = {}
        for animator in animation.get("animators") or []:
            if not isinstance(animator, dict) or not animator.get("keyframes"):
                continue
            bone_name = str(animator.get("name") or animator.get("bone_uuid") or "bone")
            bone_channels: JsonDict = {}

            keyframes = sorted(
                animator.get("keyframes") or [],
                key=lambda keyframe: (
                    parse_number(keyframe.get("time")) is None,
                    parse_number(keyframe.get("time")) or 0,
                )
                if isinstance(keyframe, dict)
                else (True, 0),
            )
            for keyframe in keyframes:
                if not isinstance(keyframe, dict):
                    continue
                channel = str(keyframe.get("channel") or "unknown")
                channel_frames = bone_channels.setdefault(channel, {})
                channel_frames[json_time_key(keyframe.get("time", 0))] = keyframe_to_bedrock_value(keyframe)

            if bone_channels:
                bones[bone_name] = bone_channels

        if bones:
            animation_body["bones"] = bones

        animations[normalize_animation_name(animation.get("name"), animation_prefix)] = animation_body

    return {
        "format_version": format_version,
        "animations": animations,
    }


def texture_reference_records(
    model: JsonDict,
    extracted_records: list[JsonDict],
    texture_prefix: str | None,
) -> list[JsonDict]:
    extracted_by_index = {
        record["index"]: record
        for record in extracted_records
        if isinstance(record, dict) and "index" in record
    }
    records: list[JsonDict] = []
    for texture in model.get("textures") or []:
        if not isinstance(texture, dict):
            continue
        index = texture.get("index")
        extracted = extracted_by_index.get(index)
        if extracted:
            filename = Path(str(extracted.get("path"))).name
        else:
            source_path = texture.get("relative_path") or texture.get("path")
            raw_filename = Path(str(source_path)).name if source_path else str(texture.get("name") or "")
            filename = safe_filename(raw_filename, f"texture_{index}.png")
            if Path(filename).suffix == "":
                file_format = str(texture.get("file_format") or "png").lstrip(".")
                filename = f"{filename}.{file_format}"
        record = {
            "index": index,
            "id": texture.get("id"),
            "uuid": texture.get("uuid"),
            "name": texture.get("name"),
            "width": texture.get("width"),
            "height": texture.get("height"),
            "uv_width": texture.get("uv_width"),
            "uv_height": texture.get("uv_height"),
            "source_path": texture.get("relative_path") or texture.get("path"),
            "embedded_source": texture.get("embedded_source"),
            "extracted_path": extracted.get("path") if extracted else None,
            "logical_path": extracted.get("logical_path") if extracted else join_logical_path(texture_prefix, filename),
        }
        records.append(record)
    return records


def attach_texture_records(model: JsonDict, records: list[JsonDict]) -> None:
    by_index = {record.get("index"): record for record in records if isinstance(record, dict)}
    for texture in model.get("textures") or []:
        if not isinstance(texture, dict):
            continue
        record = by_index.get(texture.get("index"))
        if record:
            texture["extracted_path"] = record.get("extracted_path")
            texture["logical_path"] = record.get("logical_path")


def build_export_manifest(
    *,
    model: JsonDict,
    geo_json_path: Path | None,
    animation_json_path: Path | None,
    normalized_json_path: Path | None,
    texture_records: list[JsonDict],
) -> JsonDict:
    return {
        "source": model.get("file"),
        "name": model.get("name"),
        "model_identifier": model.get("model_identifier"),
        "outputs": {
            "normalized_json": str(normalized_json_path) if normalized_json_path else None,
            "geo_json": str(geo_json_path) if geo_json_path else None,
            "animation_json": str(animation_json_path) if animation_json_path else None,
        },
        "counts": {
            "elements": model.get("element_count"),
            "groups": model.get("group_count"),
            "textures": model.get("texture_count"),
            "animations": model.get("animation_count"),
        },
        "textures": texture_records,
    }


def resolve_output_path(target: Path | None, source_path: Path, suffix: str, multiple: bool) -> Path | None:
    if target is None:
        return None
    if multiple and target.suffix:
        raise ValueError(f"{target} must be a directory when multiple input files are used")
    if multiple or not target.suffix:
        return target / f"{safe_filename(source_path.stem, 'model')}{suffix}"
    return target


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def json_payload_for_kind(bundle: JsonDict, kind: str) -> Any:
    if kind == "all":
        return bundle
    if kind == "normalized":
        return bundle["normalized"]
    if kind == "geo":
        return bundle["geo"]
    if kind == "animations":
        return bundle["animations"]
    if kind == "textures":
        return bundle["textures"]
    if kind == "manifest":
        return bundle["manifest"]
    raise ValueError(f"unknown json kind: {kind}")


def print_outliner(nodes: list[JsonDict], indent: int = 0) -> None:
    prefix = "  " * indent
    for node in nodes:
        kind = node.get("kind")
        if kind == "group":
            print(f"{prefix}- group: {node.get('name') or '<unnamed>'} ({node.get('uuid')})")
            children = node.get("children")
            if isinstance(children, list):
                print_outliner(children, indent + 1)
        elif kind == "element":
            print(
                f"{prefix}- element: {node.get('name') or '<unnamed>'} "
                f"[{node.get('type')}] ({node.get('uuid')})"
            )
        elif kind == "missing_element":
            print(f"{prefix}- missing element uuid: {node.get('uuid')}")
        else:
            print(f"{prefix}- unknown node: {node.get('value')!r}")


def print_summary(model: JsonDict, *, show_elements: bool = True, show_outliner: bool = True) -> None:
    meta = model["meta"]
    print(f"File: {model['file']}")
    print(f"Name: {model['name']}")
    if model.get("model_identifier"):
        print(f"Identifier: {model['model_identifier']}")
    print(
        "Format: "
        f"{meta.get('model_format') or 'unknown'} "
        f"(version {meta.get('format_version') or 'unknown'}, box_uv={meta.get('box_uv')})"
    )
    print(f"Resolution: {model.get('resolution')}")
    print(f"Visible box: {model.get('visible_box')}")
    print(f"Bounds: {model.get('bounds')}")
    print(
        f"Counts: {model['element_count']} elements, "
        f"{model['group_count']} groups, "
        f"{model['texture_count']} textures, {model['animation_count']} animations"
    )

    if model["textures"]:
        print("\nTextures:")
        for texture in model["textures"]:
            embedded = "embedded" if texture["embedded_source"] else "external"
            print(
                f"  [{texture['index']}] {texture.get('name') or '<unnamed>'} "
                f"id={texture.get('id')} {embedded} "
                f"size={texture.get('width')}x{texture.get('height')} "
                f"uv={texture.get('uv_width')}x{texture.get('uv_height')} "
                f"path={texture.get('relative_path') or texture.get('path')}"
            )

    if model["animations"]:
        print("\nAnimations:")
        for animation in model["animations"]:
            print(
                f"  [{animation['index']}] {animation.get('name') or '<unnamed>'} "
                f"length={animation.get('length')} loop={animation.get('loop')} "
                f"animators={animation['animator_count']} "
                f"keyframes={animation['keyframe_count']} channels={animation['channels']}"
            )
            for animator in animation["animators"]:
                if animator["keyframe_count"]:
                    print(
                        f"    - {animator.get('name') or animator.get('bone_uuid')} "
                        f"keyframes={animator['keyframe_count']} channels={animator['channels']}"
                    )

    if show_elements and model["elements"]:
        print("\nElements:")
        for element in model["elements"]:
            print(
                f"  - {element.get('name') or '<unnamed>'} [{element.get('type')}] "
                f"uuid={element.get('uuid')} from={element.get('from')} "
                f"to={element.get('to')} size={element.get('size')}"
            )

    if show_outliner and model["outliner"]:
        print("\nOutliner:")
        print_outliner(model["outliner"])


def decode_data_url(source: str) -> tuple[str | None, bytes]:
    match = DATA_URL_RE.match(source)
    if not match:
        raise ValueError("source is not a base64 data URL")
    mime = match.group("mime")
    try:
        payload = base64.b64decode(match.group("data"), validate=True)
    except binascii.Error as exc:
        raise ValueError("invalid base64 texture source") from exc
    return mime, payload


def extension_from_mime(mime: str | None) -> str:
    if mime == "image/png":
        return ".png"
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".bin"


def extract_textures(data: JsonDict, output_dir: Path, texture_prefix: str | None = None) -> list[JsonDict]:
    textures = data.get("textures")
    if not isinstance(textures, list):
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[JsonDict] = []
    for index, texture in enumerate(textures):
        if not isinstance(texture, dict):
            continue
        source = texture.get("source")
        if not isinstance(source, str) or not source.startswith("data:"):
            continue
        mime, payload = decode_data_url(source)
        fallback = f"texture_{index}{extension_from_mime(mime)}"
        raw_name = str(texture.get("name") or fallback)
        name = safe_filename(raw_name, fallback)
        if Path(name).suffix == "":
            name += extension_from_mime(mime)
        output_path = output_dir / name

        counter = 1
        while output_path.exists():
            stem = output_path.stem
            suffix = output_path.suffix
            output_path = output_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        output_path.write_bytes(payload)
        written.append(
            {
                "index": index,
                "id": texture.get("id"),
                "uuid": texture.get("uuid"),
                "name": texture.get("name"),
                "mime": mime,
                "bytes": len(payload),
                "path": str(output_path),
                "filename": output_path.name,
                "logical_path": join_logical_path(texture_prefix, output_path.name),
            }
        )
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse a Blockbench .bbmodel file.")
    parser.add_argument("files", nargs="+", type=Path, help="Path to one or more .bbmodel files.")
    parser.add_argument(
        "--format",
        choices=("summary", "json"),
        default="summary",
        help="Output format. Default: summary.",
    )
    parser.add_argument(
        "--json-kind",
        choices=("normalized", "geo", "animations", "textures", "manifest", "all"),
        default="normalized",
        help="JSON payload printed to stdout when --format json is used. Default: normalized.",
    )
    parser.add_argument(
        "--no-elements",
        action="store_true",
        help="Hide the element list in summary output.",
    )
    parser.add_argument(
        "--no-outliner",
        action="store_true",
        help="Hide the outliner tree in summary output.",
    )
    parser.add_argument(
        "--extract-textures",
        type=Path,
        help="Directory to write embedded base64 textures into. Alias of --texture-dir.",
    )
    parser.add_argument(
        "--texture-dir",
        type=Path,
        help="Directory to write embedded base64 textures into.",
    )
    parser.add_argument(
        "--texture-prefix",
        help="Logical path prefix recorded for textures, for example textures/blocks.",
    )
    parser.add_argument(
        "--normalized-json",
        "--model-json",
        dest="normalized_json",
        type=Path,
        help="Write normalized parser JSON to this file, or to this directory for multiple inputs.",
    )
    parser.add_argument(
        "--geo-json",
        type=Path,
        help="Write generated Bedrock geometry JSON to this file, or to this directory for multiple inputs.",
    )
    parser.add_argument(
        "--animation-json",
        type=Path,
        help="Write generated Bedrock animation JSON to this file, or to this directory for multiple inputs.",
    )
    parser.add_argument(
        "--manifest-json",
        type=Path,
        help="Write export manifest JSON to this file, or to this directory for multiple inputs.",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        help="Write normalized, geo, animation, manifest JSON and textures into one directory.",
    )
    parser.add_argument(
        "--identifier",
        help="Override geometry identifier. Only allowed for a single input file.",
    )
    parser.add_argument(
        "--animation-prefix",
        default="animation",
        help="Prefix for generated animation names when missing. Default: animation.",
    )
    parser.add_argument(
        "--geo-format-version",
        default="1.12.0",
        help="format_version for generated geometry JSON. Default: 1.12.0.",
    )
    parser.add_argument(
        "--animation-format-version",
        default="1.8.0",
        help="format_version for generated animation JSON. Default: 1.8.0.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.identifier and len(args.files) > 1:
            raise ValueError("--identifier can only be used with a single input file")
        if args.texture_dir and args.extract_textures and args.texture_dir != args.extract_textures:
            raise ValueError("--texture-dir and --extract-textures point to different directories")

        models: list[JsonDict] = []
        source_data: list[tuple[Path, JsonDict]] = []
        for file_path in args.files:
            data = load_bbmodel(file_path)
            source_data.append((file_path, data))
            models.append(normalize_model(data, file_path))

        multiple = len(source_data) > 1
        bundles: list[JsonDict] = []
        all_written_files: list[Path] = []
        all_extracted_textures: list[JsonDict] = []

        texture_target = args.texture_dir or args.extract_textures
        if texture_target is None and args.export_dir:
            texture_target = args.export_dir / "textures"

        for (file_path, data), model in zip(source_data, models):
            stem = safe_filename(file_path.stem, "model")

            normalized_json_path = resolve_output_path(args.normalized_json, file_path, ".normalized.json", multiple)
            geo_json_path = resolve_output_path(args.geo_json, file_path, ".geo.json", multiple)
            animation_json_path = resolve_output_path(args.animation_json, file_path, ".animation.json", multiple)
            manifest_json_path = resolve_output_path(args.manifest_json, file_path, ".manifest.json", multiple)

            if args.export_dir:
                normalized_json_path = normalized_json_path or args.export_dir / f"{stem}.normalized.json"
                geo_json_path = geo_json_path or args.export_dir / f"{stem}.geo.json"
                animation_json_path = animation_json_path or args.export_dir / f"{stem}.animation.json"
                manifest_json_path = manifest_json_path or args.export_dir / f"{stem}.manifest.json"

            extracted_textures: list[JsonDict] = []
            if texture_target:
                texture_output_dir = texture_target / stem if multiple else texture_target
                extracted_textures = extract_textures(data, texture_output_dir, args.texture_prefix)
                all_extracted_textures.extend(extracted_textures)

            texture_records = texture_reference_records(model, extracted_textures, args.texture_prefix)
            attach_texture_records(model, texture_records)

            geo_json = build_bedrock_geometry_json(
                model,
                identifier=args.identifier,
                format_version=args.geo_format_version,
            )
            animation_json = build_bedrock_animation_json(
                model,
                animation_prefix=args.animation_prefix,
                format_version=args.animation_format_version,
            )
            manifest_json = build_export_manifest(
                model=model,
                geo_json_path=geo_json_path,
                animation_json_path=animation_json_path,
                normalized_json_path=normalized_json_path,
                texture_records=texture_records,
            )

            bundle = {
                "normalized": model,
                "geo": geo_json,
                "animations": animation_json,
                "textures": texture_records,
                "manifest": manifest_json,
            }
            bundles.append(bundle)

            if normalized_json_path:
                write_json_file(normalized_json_path, model)
                all_written_files.append(normalized_json_path)
            if geo_json_path:
                write_json_file(geo_json_path, geo_json)
                all_written_files.append(geo_json_path)
            if animation_json_path:
                write_json_file(animation_json_path, animation_json)
                all_written_files.append(animation_json_path)
            if manifest_json_path:
                write_json_file(manifest_json_path, manifest_json)
                all_written_files.append(manifest_json_path)

        if args.format == "json":
            payload: Any
            selected_payloads = [json_payload_for_kind(bundle, args.json_kind) for bundle in bundles]
            payload = selected_payloads[0] if len(selected_payloads) == 1 else selected_payloads
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if all_extracted_textures:
                print(f"Extracted {len(all_extracted_textures)} embedded textures")
                for texture in all_extracted_textures:
                    print(f"  - {texture['path']} -> {texture['logical_path']}")
                print()
            if all_written_files:
                print(f"Wrote {len(all_written_files)} JSON files")
                for path in all_written_files:
                    print(f"  - {path}")
                print()
            for index, model in enumerate(models):
                if index:
                    print("\n" + "=" * 80 + "\n")
                print_summary(
                    model,
                    show_elements=not args.no_elements,
                    show_outliner=not args.no_outliner,
                )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
