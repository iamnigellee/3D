#!/usr/bin/env python3
"""
Blender拆件脚本 - 将3D模型按品类规则拆分为独立部件
使用方式: blender --background --python part_split.py -- [参数]
"""

import argparse
import os
import sys

import bmesh
import bpy
import yaml
from mathutils import Vector


def parse_args():
    """解析Blender '--' 之后的自定义参数"""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender拆件")
    parser.add_argument("--input", "-i", required=True, help="GLB模型文件路径")
    parser.add_argument("--output-dir", "-o", required=True, help="部件输出目录")
    parser.add_argument("--rules", "-r", default="config/split_rules.yaml", help="拆件规则配置")
    parser.add_argument("--category", "-c", default="figure", help="品类: figure")
    return parser.parse_args(argv)


def load_rules(rules_path: str) -> dict:
    """加载拆件规则"""
    with open(rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear_scene():
    """清空场景"""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_glb(filepath: str):
    """导入GLB并合并所有网格"""
    bpy.ops.import_scene.gltf(filepath=filepath)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        print("[拆件] 错误: 没有找到网格对象", file=sys.stderr)
        sys.exit(1)

    # 合并所有网格为一个对象
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()

    merged = bpy.context.active_object
    merged.name = "Model"

    # 应用变换
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    return merged


def get_bounds(obj):
    """获取对象边界框"""
    min_c = Vector((float("inf"),) * 3)
    max_c = Vector((float("-inf"),) * 3)
    for corner in obj.bound_box:
        wc = obj.matrix_world @ Vector(corner)
        for i in range(3):
            min_c[i] = min(min_c[i], wc[i])
            max_c[i] = max(max_c[i], wc[i])
    return min_c, max_c


def bisect_mesh(obj, plane_co, plane_no, keep="upper"):
    """
    使用平面切割网格

    Args:
        obj: Blender对象
        plane_co: 切割平面上的一点
        plane_no: 切割平面法线
        keep: 保留哪一侧 - "upper"(法线方向) 或 "lower"(反法线方向)

    Returns:
        切割后的新对象
    """
    # 复制对象
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.duplicate()
    new_obj = bpy.context.active_object

    # 进入编辑模式
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    # 执行bisect
    clear_inner = keep == "upper"
    clear_outer = keep == "lower"

    bpy.ops.mesh.bisect(
        plane_co=plane_co,
        plane_no=plane_no,
        clear_inner=clear_inner,
        clear_outer=clear_outer,
        use_fill=True,
    )

    bpy.ops.object.mode_set(mode="OBJECT")

    # 清理孤立顶点
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.delete_loose()
    bpy.ops.object.mode_set(mode="OBJECT")

    return new_obj


def add_joint_cylinder(obj, position, direction, diameter, depth, is_male=True, tolerance=0.2):
    """
    在切割面添加圆柱榫

    Args:
        obj: 目标对象
        position: 榫位置
        direction: 榫方向（法线）
        diameter: 榫径
        depth: 榫深
        is_male: True=公榫(凸), False=母榫(凹)
        tolerance: 公差
    """
    radius = diameter / 2
    if not is_male:
        radius += tolerance

    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=depth,
        location=position,
    )
    cylinder = bpy.context.active_object
    cylinder.name = "Joint_Temp"

    # 对齐方向
    direction = Vector(direction).normalized()
    rot_quat = direction.to_track_quat("Z", "Y")
    cylinder.rotation_euler = rot_quat.to_euler()

    # 偏移使一端对齐切割面
    offset = direction * (depth / 2)
    if is_male:
        cylinder.location = Vector(position) + offset
    else:
        cylinder.location = Vector(position) - offset

    # Boolean操作
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="Joint", type="BOOLEAN")
    modifier.object = cylinder
    modifier.operation = "UNION" if is_male else "DIFFERENCE"
    bpy.ops.object.modifier_apply(modifier="Joint")

    # 删除临时圆柱
    bpy.data.objects.remove(cylinder, do_unlink=True)


def add_joint_ball(obj, position, diameter, is_male=True, tolerance=0.2):
    """
    在切割面添加球榫

    Args:
        obj: 目标对象
        position: 球心位置
        diameter: 球径
        is_male: True=公榫(凸), False=母榫(凹)
        tolerance: 公差
    """
    radius = diameter / 2
    if not is_male:
        radius += tolerance

    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        segments=32,
        ring_count=16,
        location=position,
    )
    sphere = bpy.context.active_object
    sphere.name = "Joint_Ball_Temp"

    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="BallJoint", type="BOOLEAN")
    modifier.object = sphere
    modifier.operation = "UNION" if is_male else "DIFFERENCE"
    bpy.ops.object.modifier_apply(modifier="BallJoint")

    bpy.data.objects.remove(sphere, do_unlink=True)


def split_figure(model, rules, global_cfg):
    """
    按公仔手办规则拆件

    Args:
        model: Blender模型对象
        rules: 品类拆件规则
        global_cfg: 全局配置

    Returns:
        dict: {部件名: Blender对象}
    """
    parts_config = rules["parts"]
    min_bound, max_bound = get_bounds(model)
    model_height = max_bound.z - min_bound.z
    model_width = max_bound.x - min_bound.x
    model_center_x = (min_bound.x + max_bound.x) / 2
    model_center_y = (min_bound.y + max_bound.y) / 2

    print(f"[拆件] 模型高度: {model_height:.2f}, 宽度: {model_width:.2f}")

    parts = {}
    overlap = global_cfg.get("overlap", 0.1)

    # === 头部 ===
    head_cfg = parts_config["head"]
    neck_z = min_bound.z + model_height * head_cfg["plane_position_ratio"]
    print(f"[拆件] 颈部切割高度: Z={neck_z:.2f}")

    head = bisect_mesh(model, plane_co=(0, 0, neck_z), plane_no=(0, 0, 1), keep="upper")
    head.name = "head"
    parts["head"] = head

    # === 腿部切割高度 ===
    leg_cfg = parts_config["leg_left"]
    hip_z = min_bound.z + model_height * leg_cfg["plane_position_ratio"]
    print(f"[拆件] 髋部切割高度: Z={hip_z:.2f}")

    # === 左腿 ===
    lower_body = bisect_mesh(model, plane_co=(0, 0, hip_z), plane_no=(0, 0, 1), keep="lower")
    leg_left = bisect_mesh(lower_body, plane_co=(model_center_x, 0, 0), plane_no=(1, 0, 0), keep="lower")
    leg_left.name = "leg_left"
    parts["leg_left"] = leg_left

    # === 右腿 ===
    leg_right = bisect_mesh(lower_body, plane_co=(model_center_x, 0, 0), plane_no=(1, 0, 0), keep="upper")
    leg_right.name = "leg_right"
    parts["leg_right"] = leg_right

    # 清理临时下半身对象
    bpy.data.objects.remove(lower_body, do_unlink=True)

    # === 手臂 - 从中段切割 ===
    arm_left_cfg = parts_config["arm_left"]
    arm_left_x = min_bound.x + model_width * arm_left_cfg["plane_position_ratio"]

    # 先得到中段（颈部到髋部）
    mid_body = bisect_mesh(model, plane_co=(0, 0, neck_z), plane_no=(0, 0, 1), keep="lower")
    mid_body_upper = bisect_mesh(mid_body, plane_co=(0, 0, hip_z), plane_no=(0, 0, 1), keep="upper")
    bpy.data.objects.remove(mid_body, do_unlink=True)

    # 左臂
    arm_left = bisect_mesh(mid_body_upper, plane_co=(arm_left_x, 0, 0), plane_no=(1, 0, 0), keep="lower")
    arm_left.name = "arm_left"
    parts["arm_left"] = arm_left

    # 右臂
    arm_right_cfg = parts_config["arm_right"]
    arm_right_x = min_bound.x + model_width * arm_right_cfg["plane_position_ratio"]
    arm_right = bisect_mesh(mid_body_upper, plane_co=(arm_right_x, 0, 0), plane_no=(1, 0, 0), keep="upper")
    arm_right.name = "arm_right"
    parts["arm_right"] = arm_right

    # 身体 = 中段去掉两臂
    body = bisect_mesh(mid_body_upper, plane_co=(arm_left_x, 0, 0), plane_no=(1, 0, 0), keep="upper")
    body_final = bisect_mesh(body, plane_co=(arm_right_x, 0, 0), plane_no=(1, 0, 0), keep="lower")
    body_final.name = "body"
    parts["body"] = body_final
    bpy.data.objects.remove(body, do_unlink=True)
    bpy.data.objects.remove(mid_body_upper, do_unlink=True)

    # === 底座 (生成) ===
    base_cfg = parts_config["base"]
    base_diameter = model_width * base_cfg.get("diameter_margin", 1.2)
    base_thickness = base_cfg.get("thickness", 3.0) / 1000  # 转为Blender单位(m)，如模型单位为m
    # 检查模型是否以mm为单位
    if model_height > 10:  # 大于10，可能是mm单位
        base_thickness = base_cfg.get("thickness", 3.0)

    bpy.ops.mesh.primitive_cylinder_add(
        radius=base_diameter / 2,
        depth=base_thickness,
        location=(model_center_x, model_center_y, min_bound.z - base_thickness / 2),
    )
    base = bpy.context.active_object
    base.name = "base"

    # 倒角
    fillet = base_cfg.get("fillet_radius", 0.5)
    bevel_mod = base.modifiers.new("Bevel", "BEVEL")
    bevel_mod.width = fillet
    bevel_mod.segments = 4
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier="Bevel")
    parts["base"] = base

    # === 添加榫卯结构 ===
    print("[拆件] 添加榫卯连接结构...")
    for part_name, part_obj in parts.items():
        if part_name in parts_config and "joint" in parts_config[part_name]:
            joint_cfg = parts_config[part_name]["joint"]
            joint_type = joint_cfg.get("type", "cylinder")
            diameter = joint_cfg.get("diameter", 3.0)
            tolerance = joint_cfg.get("tolerance", 0.2)

            # 确定榫位置（在切割面中心）
            p_min, p_max = get_bounds(part_obj)
            joint_pos = ((p_min.x + p_max.x) / 2, (p_min.y + p_max.y) / 2, 0)

            if part_name == "head":
                joint_pos = (joint_pos[0], joint_pos[1], p_min.z)
                if joint_type == "cylinder":
                    add_joint_cylinder(part_obj, joint_pos, (0, 0, -1),
                                       diameter, joint_cfg.get("depth", 5.0), is_male=True, tolerance=0)
            elif part_name == "body":
                # 身体上方添加母榫（接头部）
                top_pos = (joint_pos[0], joint_pos[1], p_max.z)
                if joint_type == "cylinder":
                    add_joint_cylinder(part_obj, top_pos, (0, 0, 1),
                                       diameter, joint_cfg.get("depth", 5.0), is_male=False, tolerance=tolerance)

    return parts


def export_parts(parts: dict, output_dir: str, export_format: str = "stl"):
    """导出各部件"""
    os.makedirs(output_dir, exist_ok=True)

    for name, obj in parts.items():
        filepath = os.path.join(output_dir, f"{name}.{export_format}")

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        if export_format == "stl":
            bpy.ops.wm.stl_export(
                filepath=filepath,
                export_selected_objects=True,
            ) if bpy.app.version >= (4, 0, 0) else bpy.ops.export_mesh.stl(
                filepath=filepath,
                use_selection=True,
            )
        elif export_format == "obj":
            bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True)

        # 统计信息
        face_count = len(obj.data.polygons)
        vert_count = len(obj.data.vertices)
        p_min, p_max = get_bounds(obj)
        size = p_max - p_min
        print(f"[拆件] {name}: {vert_count}顶点, {face_count}面, 尺寸({size.x:.1f} x {size.y:.1f} x {size.z:.1f}) → {filepath}")


def main():
    args = parse_args()
    rules_data = load_rules(args.rules)

    category_rules = rules_data.get("categories", {}).get(args.category)
    if not category_rules:
        print(f"[拆件] 错误: 找不到品类 '{args.category}' 的规则", file=sys.stderr)
        available = list(rules_data.get("categories", {}).keys())
        print(f"[拆件] 可用品类: {available}", file=sys.stderr)
        sys.exit(1)

    global_cfg = rules_data.get("global", {})

    print(f"[拆件] 模型: {args.input}")
    print(f"[拆件] 品类: {args.category} - {category_rules.get('description', '')}")

    # 清空场景并导入模型
    clear_scene()
    model = import_glb(args.input)

    # 确保单位为毫米（如配置要求）
    if global_cfg.get("scale_to_mm", True):
        min_b, max_b = get_bounds(model)
        height = max_b.z - min_b.z
        if height < 0.5:  # 可能是米为单位，转为毫米
            model.scale = (1000, 1000, 1000)
            bpy.ops.object.transform_apply(scale=True)
            print("[拆件] 已将模型从米缩放到毫米")

    # 执行拆件
    parts = split_figure(model, category_rules, global_cfg)

    # 导出
    export_format = global_cfg.get("export_format", "stl")
    export_parts(parts, args.output_dir, export_format)

    print(f"[拆件] 完成! 共 {len(parts)} 个部件")


if __name__ == "__main__":
    main()
