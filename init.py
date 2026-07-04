# -*- coding: utf-8 -*-
"""
项目初始化脚本
功能:
  1. 重命名 scripts 文件夹（BehaviorPack/EmptyScripts -> 新名称）
  2. 重新生成项目内所有 UUID（BehaviorPack 和 ResourcePack 的 manifest.json）
"""
import os
import sys
import json
import uuid

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BEHAVIOR_PACK_DIR = os.path.join(ROOT_DIR, "modPack", "BehaviorPack")
RESOURCE_PACK_DIR = os.path.join(ROOT_DIR, "modPack", "ResourcePack")
DEFAULT_SCRIPTS_NAME = "EmptyScripts"


def find_scripts_folder():
    """查找当前的 scripts 文件夹名称"""
    for name in os.listdir(BEHAVIOR_PACK_DIR):
        full_path = os.path.join(BEHAVIOR_PACK_DIR, name)
        if os.path.isdir(full_path) and name != "entities":
            # 检查是否包含 modMain.py（标志性脚本文件）
            if os.path.exists(os.path.join(full_path, "modMain.py")):
                return name
    return None


def rename_scripts_folder(new_name):
    """重命名 scripts 文件夹"""
    current_name = find_scripts_folder()
    if current_name is None:
        print("[错误] 未找到 scripts 文件夹（需包含 modMain.py）")
        return False

    if current_name == new_name:
        print("[跳过] scripts 文件夹名称已经是 '{}'".format(new_name))
        return True

    old_path = os.path.join(BEHAVIOR_PACK_DIR, current_name)
    new_path = os.path.join(BEHAVIOR_PACK_DIR, new_name)

    if os.path.exists(new_path):
        print("[错误] 目标文件夹 '{}' 已存在".format(new_name))
        return False

    os.rename(old_path, new_path)
    print("[完成] scripts 文件夹已重命名: '{}' -> '{}'".format(current_name, new_name))
    return True


def regenerate_uuids():
    """重新生成所有 manifest.json 中的 UUID"""
    manifest_files = [
        os.path.join(BEHAVIOR_PACK_DIR, "manifest.json"),
        os.path.join(RESOURCE_PACK_DIR, "manifest.json"),
    ]

    for manifest_path in manifest_files:
        if not os.path.exists(manifest_path):
            print("[警告] 未找到 manifest 文件: {}".format(manifest_path))
            continue

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pack_type = os.path.basename(os.path.dirname(manifest_path))

        # 替换 header UUID
        if "header" in data and "uuid" in data["header"]:
            new_uuid = str(uuid.uuid4())
            print("[UUID] {} header: {} -> {}".format(pack_type, data["header"]["uuid"], new_uuid))
            data["header"]["uuid"] = new_uuid

        # 替换 modules 中的 UUID
        for i, module in enumerate(data.get("modules", [])):
            if "uuid" in module:
                new_uuid = str(uuid.uuid4())
                print("[UUID] {} module[{}]: {} -> {}".format(pack_type, i, module["uuid"], new_uuid))
                module["uuid"] = new_uuid

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    print("[完成] 所有 UUID 已重新生成")


def main():
    print("=" * 50)
    print("  Minecraft Mod 项目初始化工具")
    print("=" * 50)

    # 获取当前 scripts 文件夹信息
    current_name = find_scripts_folder()
    if current_name:
        print("\n当前 scripts 文件夹名称: '{}'".format(current_name))
    else:
        print("\n[警告] 未找到 scripts 文件夹")

    # 从根目录名称自动获取项目名称
    project_name = os.path.basename(ROOT_DIR)
    print("\n项目名称 (从根目录获取): '{}'".format(project_name))

    # scripts 文件夹名称 = ProjectName + "Scripts"
    new_name = project_name + "Scripts"
    print("scripts 文件夹将重命名为: '{}'".format(new_name))

    print("\n--- 重命名 scripts 文件夹 ---")
    if not rename_scripts_folder(new_name):
        sys.exit(1)

    # 重新生成 UUID
    print("\n--- 重新生成 UUID ---")
    regenerate_uuids()

    # 删除自身
    script_path = os.path.abspath(__file__)
    print("\n--- 清理临时文件 ---")
    os.remove(script_path)
    print("[完成] 已删除初始化脚本: {}".format(os.path.basename(script_path)))

    print("\n" + "=" * 50)
    print("  初始化完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
