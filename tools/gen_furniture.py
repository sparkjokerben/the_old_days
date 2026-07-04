# -*- coding: utf-8 -*-
"""
老物件家具方块 —— 生成器（单一数据源）。

修改 BLOCKS / MODELS 表后重跑即可，自动同步生成/覆盖行为包、资源包里所有同构文件。

外观策略：
  - 无 bbmodel 的方块：用「自定义方块实体外观」复用原版盔甲架 geometry.armor_stand 占位。
  - 有 bbmodel 的方块（见 MODELS）：调用 tools/parse_bbmodels/parse_bbmodel.py 把 bbmodel 转成
    Bedrock 几何体/动画/贴图，接为真实方块实体外观。空调外机=按放置面切几何体，红凳=1~5 层堆叠切几何体。

运行：  python3 tools/gen_furniture.py
纯标准库（parse_bbmodel 也是纯标准库）。
"""
import os
import sys
import copy
import json
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
NAMESPACE = "tod"
TAB_NAME = "old_days"                                # 自定义创造分页名（小写）
TAB_LABEL_CN = "老物件"
ICON_RES_NAME = "tod_placeholder_icon"               # 占位 icon 的 terrain_texture 资源名
ICON_TEX_PATH = "textures/blocks/tod_placeholder"    # 占位贴图相对路径（无后缀）
PLACEHOLDER_RC = "controller.render.tod_placeholder"
DEFAULT_RC = "controller.render.tod_default"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BP = os.path.join(ROOT, "modPack", "BehaviorPack")
RP = os.path.join(ROOT, "modPack", "ResourcePack")
ASSETS = os.path.join(ROOT, "assets")

# 引入 bbmodel 解析器（用户提供，纯标准库）
sys.path.insert(0, os.path.join(ROOT, "tools", "parse_bbmodels"))
import parse_bbmodel as pb  # noqa: E402

# ---------------------------------------------------------------------------
# 方块登记表：(identifier, 中文名, 是否光源)
# ---------------------------------------------------------------------------
BLOCKS = [
    # 客厅/娱乐
    ("crt_tv", "大屁股CRT电视", False),
    ("stereo_system", "组合音响", False),
    ("quartz_wall_clock", "挂墙石英钟", False),
    ("bead_curtain", "珠帘", False),
    ("leather_sofa", "皮革沙发", False),
    ("wainscoting_green", "墙裙护墙板（绿色）", False),
    ("wainscoting_brown", "墙裙护墙板（棕色）", False),
    ("terrazzo_floor", "水磨石地板砖", False),
    # 厨房/餐饮
    ("enamel_basin", "搪瓷盆", False),
    ("aluminum_lunchbox", "铝制饭盒", False),
    ("thermos_bamboo", "保温瓶（竹编壳）", False),
    ("thermos_red", "保温瓶（红色铁壳）", False),
    ("pressure_cooker", "老式高压锅", False),
    ("mesh_food_cover", "塑料菜罩", False),
    ("gas_tank", "煤气罐", False),
    ("old_fridge_green", "老式冰箱（绿色）", False),
    ("old_fridge_yellow", "老式冰箱（黄色）", False),
    ("microwave_oven", "微波炉", False),
    ("glass_turntable_table", "玻璃转盘餐桌", False),
    # 卧室/起居
    ("floral_bedsheet_plaid", "花床单（格子）", False),
    ("floral_bedsheet_peony", "花床单（牡丹图案）", False),
    ("embroidered_pillow_towel", "枕巾", False),
    ("green_glass_lamp", "老式台灯", True),
    ("folding_table", "折叠桌", False),
    ("tear_off_desk_calendar", "台历", False),
    # 阳台/室外
    ("solar_water_heater", "太阳能热水器", False),
    ("satellite_dish", "卫星锅盖", False),
    ("water_meter", "老式水表", False),
    ("cloth_mop", "拖把", False),
    ("asbestos_awning", "雨棚", False),
    ("cement_flowerpot", "花盆（水泥）", False),
    ("clay_flowerpot", "花盆（陶土）", False),
    ("rusty_birdcage", "鸟笼", False),
    # 电器/电子
    ("game_console", "小霸王学习机", False),
    ("repeater_recorder", "复读机", False),
    ("rotary_phone", "座机电话", False),
    ("charger_block", "充电器", True),
    ("transformer_block", "变压器", False),
    # 交通工具/玩具
    ("bicycle", "自行车（二八大杠）", False),
    ("tricycle", "三轮车", False),
    ("kick_scooter", "滑板车", False),
    # 墙体/装饰
    ("star_poster", "明星海报", False),
    ("framed_award", "奖状", False),
    ("eye_chart", "视力表", False),
    ("wall_calendar", "日历", False),
    ("window_screen", "纱窗", False),
    ("sliding_window", "推拉窗", False),
    ("security_grille", "防盗网", False),
    ("exhaust_fan", "排气扇", False),
    ("meter_box", "电表箱", False),
    ("corridor_light", "楼道灯", True),
    # ---- 第二阶段新增（有真实 bbmodel）----
    ("advertisement", "广告牌", False),
    ("wooden_chair", "老式木椅子", False),
    ("ceiling_fan", "吊扇", False),
    ("ac_outdoor_unit", "空调外机", False),
    ("red_plastic_stool", "红色塑料凳", False),
]

# ---------------------------------------------------------------------------
# 模型登记表：block id -> bbmodel 接入配置
#   bb        : assets/ 下 bbmodel 文件名（不含扩展名）列表
#   kind      : simple / animated / ac / stool
#   face_dir  : 是否加 netease:face_directional（六面向）
# ---------------------------------------------------------------------------
MODELS = {
    "framed_award": {"bb": ["奖状"], "kind": "simple"},
    "advertisement": {"bb": ["广告"], "kind": "simple"},
    "wooden_chair": {"bb": ["老式木椅子"], "kind": "simple"},
    "ceiling_fan": {"bb": ["吊扇"], "kind": "animated"},
    "ac_outdoor_unit": {"bb": ["空调外机_无支架", "空调外机"], "kind": "ac", "face_dir": True},
    "red_plastic_stool": {"bb": ["红色塑料凳"], "kind": "stool", "stack_max": 5, "stack_delta": 4.5},
}

FAN_ANIM = "animation.tod_ceiling_fan.spin"
FAN_ANIM_CTRL = "controller.animation.tod_ceiling_fan.fan"


def fid(bid):
    return "{}:{}".format(NAMESPACE, bid)


def geo_id(bid, suffix=""):
    return "geometry.tod_{}{}".format(bid, ("_" + suffix) if suffix else "")


def tex_name(bid):
    return "tod_{}".format(bid)                       # terrain_texture 资源名


def tex_path(bid):
    return "textures/entity/tod_{}".format(bid)       # 无后缀相对路径


def ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)


def write_json(path, data, compact=False):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# bbmodel -> 几何体 / 贴图 / 动画
# ---------------------------------------------------------------------------
def _translate_geo(geo, dx, dz):
    """整体平移几何体的 X/Z（Y 不动），用于把以原点为中心编辑的模型居中到方块格内。"""
    for g in geo.get("minecraft:geometry", []):
        for bone in g.get("bones", []):
            piv = bone.get("pivot")
            if piv:
                piv[0] += dx
                piv[2] += dz
            for cube in bone.get("cubes", []):
                cube["origin"][0] += dx
                cube["origin"][2] += dz
                if cube.get("pivot"):
                    cube["pivot"][0] += dx
                    cube["pivot"][2] += dz


def _load_geo(bbname, identifier):
    """解析单个 bbmodel，返回 (居中后的单几何体 dict, model, raw_data)。"""
    bbpath = Path(os.path.join(ASSETS, bbname + ".bbmodel"))
    data = pb.load_bbmodel(bbpath)
    model = pb.normalize_model(data, bbpath)
    geo = pb.build_bedrock_geometry_json(model, identifier=identifier, format_version="1.12.0")
    b = model.get("bounds") or {}
    mn = b.get("min") or [0, 0, 0]
    mx = b.get("max") or [0, 0, 0]
    dx = 8.0 - (mn[0] + mx[0]) / 2.0
    dz = 8.0 - (mn[2] + mx[2]) / 2.0
    _translate_geo(geo, dx, dz)
    return geo["minecraft:geometry"][0], model, data


def _extract_texture(data, bid):
    """把 bbmodel 内嵌 base64 贴图写到 textures/entity/tod_<id>.png。"""
    src = (data.get("textures") or [{}])[0].get("source", "")
    if not isinstance(src, str) or not src.startswith("data:"):
        raise ValueError("bbmodel 缺少内嵌贴图: {}".format(bid))
    _mime, payload = pb.decode_data_url(src)
    out = os.path.join(RP, "textures", "entity", "tod_{}.png".format(bid))
    ensure_dir(os.path.dirname(out))
    with open(out, "wb") as f:
        f.write(payload)


def _make_stack_geo(base_geo_entry, identifier, layers, delta):
    """把单凳几何体沿 Y 克隆 layers 层（嵌套抬升 delta），生成堆叠几何体。"""
    desc = copy.deepcopy(base_geo_entry["description"])
    desc["identifier"] = identifier
    base_bones = base_geo_entry.get("bones", [])
    bones = []
    for j in range(layers):
        dy = j * delta
        for bone in base_bones:
            nb = copy.deepcopy(bone)
            nb["name"] = "l{}_{}".format(j, bone["name"])
            if nb.get("parent"):
                nb["parent"] = "l{}_{}".format(j, nb["parent"])
            if nb.get("pivot"):
                nb["pivot"][1] += dy
            for cube in nb.get("cubes", []):
                cube["origin"][1] += dy
                if cube.get("pivot"):
                    cube["pivot"][1] += dy
            bones.append(nb)
    return {"description": desc, "bones": bones}


def gen_models():
    """转换所有 bbmodel，写几何体/贴图/动画/动画控制器。返回每个 block 的几何体名映射。"""
    ensure_dir(os.path.join(RP, "models", "entity"))
    geo_map = {}  # bid -> {"geoms": {key: identifier}}

    for bid, spec in MODELS.items():
        kind = spec["kind"]
        if kind in ("simple", "animated"):
            entry, model, data = _load_geo(spec["bb"][0], geo_id(bid))
            write_json(os.path.join(RP, "models", "entity", bid + ".geo.json"),
                       {"format_version": "1.12.0", "minecraft:geometry": [entry]}, compact=True)
            _extract_texture(data, bid)
            geo_map[bid] = {"default": geo_id(bid)}
            if kind == "animated":
                _gen_fan_animation(model)

        elif kind == "ac":
            flat, _m0, d0 = _load_geo(spec["bb"][0], geo_id(bid, "flat"))
            bracket, _m1, _d1 = _load_geo(spec["bb"][1], geo_id(bid, "bracket"))
            write_json(os.path.join(RP, "models", "entity", bid + ".geo.json"),
                       {"format_version": "1.12.0", "minecraft:geometry": [flat, bracket]}, compact=True)
            _extract_texture(d0, bid)  # 两个几何体共用同一张贴图
            geo_map[bid] = {"default": geo_id(bid, "flat"), "bracket": geo_id(bid, "bracket")}

        elif kind == "stool":
            base, _m, data = _load_geo(spec["bb"][0], geo_id(bid, "1"))
            delta = spec["stack_delta"]
            entries, keys = [], {}
            for k in range(1, spec["stack_max"] + 1):
                ident = geo_id(bid, str(k))
                entries.append(_make_stack_geo(base, ident, k, delta))
                keys["default" if k == 1 else "s{}".format(k)] = ident
            write_json(os.path.join(RP, "models", "entity", bid + ".geo.json"),
                       {"format_version": "1.12.0", "minecraft:geometry": entries}, compact=True)
            _extract_texture(data, bid)
            geo_map[bid] = keys
    return geo_map


def _gen_fan_animation(model):
    """取吊扇的循环动画，规整名字为 animation.tod_ceiling_fan.spin，写动画与动画控制器。"""
    anim = pb.build_bedrock_animation_json(model, format_version="1.8.0")
    body = None
    for _name, b in (anim.get("animations") or {}).items():
        if b.get("loop") is True:
            body = b
            break
    if body is None and anim.get("animations"):
        body = list(anim["animations"].values())[0]
    body = body or {"loop": True, "animation_length": 1, "bones": {}}
    body["loop"] = True
    write_json(os.path.join(RP, "animations", "ceiling_fan.animation.json"),
               {"format_version": "1.8.0", "animations": {FAN_ANIM: body}})
    write_json(os.path.join(RP, "animation_controllers", "ceiling_fan.animation_controllers.json"),
               {"format_version": "1.10.0", "animation_controllers": {
                   FAN_ANIM_CTRL: {"initial_state": "default", "states": {"default": {"animations": ["spin"]}}}}})


# ---------------------------------------------------------------------------
# 渲染控制器
# ---------------------------------------------------------------------------
def _rc(geometry):
    return {"geometry": geometry, "materials": [{"*": "Material.default"}], "textures": ["Texture.default"]}


def gen_render_controllers():
    controllers = {
        PLACEHOLDER_RC: _rc("Geometry.default"),
        DEFAULT_RC: _rc("Geometry.default"),
        "controller.render.tod_ac_flat": _rc("Geometry.default"),
        "controller.render.tod_ac_bracket": _rc("Geometry.bracket"),
    }
    for k in range(1, MODELS["red_plastic_stool"]["stack_max"] + 1):
        controllers["controller.render.tod_stool_{}".format(k)] = _rc(
            "Geometry.default" if k == 1 else "Geometry.s{}".format(k))
    write_json(os.path.join(RP, "render_controllers", "tod_models.render_controllers.json"),
               {"format_version": "1.10.0", "render_controllers": controllers})


# ---------------------------------------------------------------------------
# 行为包方块
# ---------------------------------------------------------------------------
def gen_behavior_blocks():
    out_dir = os.path.join(BP, "netease_blocks")
    ensure_dir(out_dir)
    for bid, _name, is_light in BLOCKS:
        components = {
            "netease:block_entity": {"movable": True},
            "minecraft:destroy_time": 0.6,
            "minecraft:explosion_resistance": 1.0,
        }
        if is_light:
            components["minecraft:block_light_emission"] = 0.6
        spec = MODELS.get(bid)
        if spec and spec.get("face_dir"):
            components["netease:face_directional"] = {"type": "facing_direction"}
        write_json(os.path.join(out_dir, bid + ".json"), {
            "format_version": "1.16.0",
            "minecraft:block": {
                "description": {
                    "identifier": fid(bid),
                    "register_to_create_menu": True,
                    "category": TAB_NAME,
                },
                "components": components,
            },
        })


# ---------------------------------------------------------------------------
# 方块实体外观定义 entity.json
# ---------------------------------------------------------------------------
def _placeholder_entity(bid):
    return {
        "format_version": "1.10.0",
        "minecraft:client_entity": {"description": {
            "identifier": fid(bid),
            "geometry": {"default": "geometry.armor_stand"},
            "textures": {"default": "textures/entity/armor_stand"},
            "materials": {"default": "entity_alphatest"},
            "render_controllers": [PLACEHOLDER_RC],
            "scripts": {"animate": []},
        }},
    }


def _model_entity(bid, geoms):
    spec = MODELS[bid]
    kind = spec["kind"]
    desc = {
        "identifier": fid(bid),
        "geometry": dict(geoms),
        "textures": {"default": tex_path(bid)},
        "materials": {"default": "entity_alphatest"},
    }
    if kind in ("simple",):
        desc["render_controllers"] = [DEFAULT_RC]
        desc["scripts"] = {"animate": []}
    elif kind == "animated":
        desc["render_controllers"] = [DEFAULT_RC]
        desc["animations"] = {"spin": FAN_ANIM, "fan": FAN_ANIM_CTRL}
        desc["scripts"] = {"animate": ["fan"]}
    elif kind == "ac":
        desc["render_controllers"] = [
            {"controller.render.tod_ac_flat": "variable.ac_mounted < 0.5"},
            {"controller.render.tod_ac_bracket": "variable.ac_mounted >= 0.5"},
        ]
        desc["scripts"] = {"initialize": ["variable.ac_mounted = 0.0;"], "animate": []}
    elif kind == "stool":
        rcs = []
        n = spec["stack_max"]
        for k in range(1, n + 1):
            if k == 1:
                cond = "variable.stool_count < 1.5"
            elif k == n:
                cond = "variable.stool_count >= {}.5".format(k - 1)
            else:
                cond = "variable.stool_count >= {}.5 && variable.stool_count < {}.5".format(k - 1, k)
            rcs.append({"controller.render.tod_stool_{}".format(k): cond})
        desc["render_controllers"] = rcs
        desc["scripts"] = {"initialize": ["variable.stool_count = 1.0;"], "animate": []}
    return {"format_version": "1.10.0", "minecraft:client_entity": {"description": desc}}


def gen_entities(geo_map):
    out_dir = os.path.join(RP, "entity")
    ensure_dir(out_dir)
    for bid, _name, _is_light in BLOCKS:
        if bid in MODELS:
            data = _model_entity(bid, geo_map[bid])
        else:
            data = _placeholder_entity(bid)
        write_json(os.path.join(out_dir, bid + ".entity.json"), data)


# ---------------------------------------------------------------------------
# 资源列表 / 贴图 / 语言 / 分页
# ---------------------------------------------------------------------------
def gen_blocks_json():
    data = {"format_version": [1, 1, 0]}
    for bid, _name, _is_light in BLOCKS:
        icon = tex_name(bid) if bid in MODELS else ICON_RES_NAME
        data[fid(bid)] = {
            "sound": "stone",
            "client_entity": {
                "identifier": fid(bid),
                "hand_model_use_client_entity": True,
                "block_icon": icon,
            },
        }
    write_json(os.path.join(RP, "blocks.json"), data)


def gen_tab():
    write_json(os.path.join(BP, "netease_tab", "tab_config.json"), {
        "category": [{
            "name": TAB_NAME,
            "labelText": "itemCategory.name.{}".format(TAB_NAME),
            "icon": ICON_TEX_PATH,
            "sort_by_identifier": True,
        }],
    })


def gen_terrain_texture():
    texture_data = {ICON_RES_NAME: {"textures": ICON_TEX_PATH}}
    for bid in MODELS:
        texture_data[tex_name(bid)] = {"textures": tex_path(bid)}
    write_json(os.path.join(RP, "textures", "terrain_texture.json"), {
        "resource_pack_name": "vanilla",
        "texture_name": "atlas.terrain",
        "texture_data": texture_data,
    })


def gen_item_texture():
    # 本阶段无自定义物品，清空脚手架残留。
    write_json(os.path.join(RP, "textures", "item_texture.json"), {
        "resource_pack_name": "vanilla",
        "texture_name": "atlas.items",
        "texture_data": {},
    })


def gen_lang():
    lines = ["## 自动生成，请勿手改：数据源见 tools/gen_furniture.py", ""]
    for bid, name, _is_light in BLOCKS:
        lines.append("tile.{}.name={}".format(fid(bid), name))
    lines.append("")
    lines.append("itemCategory.name.{}={}".format(TAB_NAME, TAB_LABEL_CN))
    lines.append("")
    path = os.path.join(RP, "texts", "zh_CN.lang")
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def gen_placeholder_png():
    """16x16 纯色占位 PNG（复古米黄），纯标准库。"""
    w = h = 16
    r, g, b, a = 198, 156, 109, 255
    raw = bytearray()
    row = bytes([r, g, b, a]) * w
    for _ in range(h):
        raw.append(0)
        raw.extend(row)

    def chunk(tag, payload):
        c = tag + payload
        return struct.pack(">I", len(payload)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path = os.path.join(RP, "textures", "blocks", "tod_placeholder.png")
    ensure_dir(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(png)


def main():
    geo_map = gen_models()
    gen_render_controllers()
    gen_behavior_blocks()
    gen_entities(geo_map)
    gen_blocks_json()
    gen_tab()
    gen_terrain_texture()
    gen_item_texture()
    gen_lang()
    gen_placeholder_png()
    print("[完成] {} 个方块（其中 {} 个接入真实 bbmodel 模型）".format(len(BLOCKS), len(MODELS)))


if __name__ == "__main__":
    main()
