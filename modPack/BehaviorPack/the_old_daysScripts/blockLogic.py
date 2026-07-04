# -*- coding: utf-8 -*-
"""老物件方块特殊逻辑的共享常量与小工具（服务端/客户端通用）。"""

# 方块 / 实体 identifier
STOOL = "tod:red_plastic_stool"
AC = "tod:ac_outdoor_unit"
SEAT = "tod:seat"

# 与 tools/gen_furniture.py 保持一致的堆叠参数
STOOL_MAX = 5
STOOL_DELTA = 4.5        # 每层嵌套抬升（模型单位）
STOOL_SEAT_Y = 17.0      # 单凳座面高度（模型单位，1 方块=16）


def seat_offset_y(count):
    """顶层座面相对方块底面的世界高度（方块单位）。"""
    return (STOOL_SEAT_Y + (max(1, count) - 1) * STOOL_DELTA) / 16.0


def face_is_ground(face):
    """点击面判定：0=down、1=up 视为平放（放地上/顶）；2~5 侧面视为贴墙有支架。"""
    return face in (0, 1)
