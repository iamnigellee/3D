#!/usr/bin/env python3
"""
Blender渲染脚本 - 多角度自动渲染
使用方式: blender --background --python render_turntable.py -- [参数]
"""

import argparse
import math
import os
import sys

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

    parser = argparse.ArgumentParser(description="Blender多角度渲染")
    parser.add_argument("--input", "-i", required=True, help="GLB模型文件路径")
    parser.add_argument("--output-dir", "-o", required=True, help="渲染图片输出目录")
    parser.add_argument("--preset", "-p", default="config/render_presets.yaml", help="渲染预设配置")
    return parser.parse_args(argv)


def load_preset(preset_path: str) -> dict:
    """加载渲染预设"""
    with open(preset_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear_scene():
    """清空场景"""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_glb(filepath: str):
    """导入GLB模型"""
    bpy.ops.import_scene.gltf(filepath=filepath)
    # 选中所有导入的网格对象
    imported = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not imported:
        print("[渲染] 错误: GLB文件中没有找到网格对象", file=sys.stderr)
        sys.exit(1)
    return imported


def get_model_bounds(objects):
    """计算模型的边界框"""
    min_coord = Vector((float("inf"),) * 3)
    max_coord = Vector((float("-inf"),) * 3)

    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            for i in range(3):
                min_coord[i] = min(min_coord[i], world_corner[i])
                max_coord[i] = max(max_coord[i], world_corner[i])

    center = (min_coord + max_coord) / 2
    size = max_coord - min_coord
    return center, size


def setup_lighting(preset: dict):
    """设置三点布光"""
    lighting = preset.get("lighting", {})

    for name, config in lighting.items():
        bpy.ops.object.light_add(
            type=config.get("type", "AREA"),
            location=tuple(config["position"]),
        )
        light = bpy.context.active_object
        light.name = name
        light.data.energy = config.get("energy", 300)
        light.data.color = tuple(config.get("color", [1, 1, 1]))
        if hasattr(light.data, "size"):
            light.data.size = config.get("size", 2)


def setup_background(preset: dict):
    """设置背景"""
    bg = preset.get("background", {})
    bg_type = bg.get("type", "gradient")

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    if bg_type == "transparent":
        bpy.context.scene.render.film_transparent = True
    elif bg_type == "gradient":
        # 渐变背景
        output = nodes.new("ShaderNodeOutputWorld")
        bg_node = nodes.new("ShaderNodeBackground")
        gradient = nodes.new("ShaderNodeTexGradient")
        mapping = nodes.new("ShaderNodeMapping")
        texcoord = nodes.new("ShaderNodeTexCoord")
        mix = nodes.new("ShaderNodeMixRGB")

        mix.inputs[1].default_value = (*bg.get("color_bottom", [0.85, 0.85, 0.90]), 1)
        mix.inputs[2].default_value = (*bg.get("color_top", [0.95, 0.95, 0.98]), 1)
        bg_node.inputs["Strength"].default_value = 1.0

        links.new(texcoord.outputs["Window"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])
        links.new(gradient.outputs["Fac"], mix.inputs["Fac"])
        links.new(mix.outputs["Color"], bg_node.inputs["Color"])
        links.new(bg_node.outputs["Background"], output.inputs["Surface"])
    else:
        # 纯色背景
        output = nodes.new("ShaderNodeOutputWorld")
        bg_node = nodes.new("ShaderNodeBackground")
        color = bg.get("color_top", [0.95, 0.95, 0.98])
        bg_node.inputs["Color"].default_value = (*color, 1)
        links.new(bg_node.outputs["Background"], output.inputs["Surface"])


def setup_ground_plane(preset: dict, model_center, model_size):
    """设置地面（仅投影）"""
    ground = preset.get("ground_plane", {})
    if not ground.get("enabled", False):
        return

    plane_size = max(model_size.x, model_size.y) * 3
    bpy.ops.mesh.primitive_plane_add(
        size=plane_size,
        location=(model_center.x, model_center.y, model_center.z - model_size.z / 2),
    )
    plane = bpy.context.active_object
    plane.name = "GroundPlane"

    if ground.get("shadow_only", True):
        mat = bpy.data.materials.new("ShadowCatcher")
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0
        mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else None
        plane.data.materials.append(mat)
        plane.is_shadow_catcher = True


def setup_render_settings(preset: dict):
    """配置渲染参数"""
    scene = bpy.context.scene
    engine = preset.get("engine", "EEVEE").upper()

    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = preset.get("samples", {}).get("cycles", 128)
        scene.cycles.use_denoising = True
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 0, 0) else "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = preset.get("samples", {}).get("eevee", 64)

    res = preset.get("resolution", {})
    scene.render.resolution_x = res.get("width", 1920)
    scene.render.resolution_y = res.get("height", 1080)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def create_camera(position, look_at, name="Camera"):
    """创建并定位相机"""
    bpy.ops.object.camera_add(location=tuple(position))
    camera = bpy.context.active_object
    camera.name = name

    # 计算相机朝向
    direction = Vector(look_at) - Vector(position)
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera.rotation_euler = rot_quat.to_euler()

    camera.data.lens = 85  # 85mm镜头，适合产品摄影
    camera.data.clip_start = 0.1
    camera.data.clip_end = 100

    return camera


def render_view(camera, output_path):
    """使用指定相机渲染一帧"""
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    print(f"[渲染] 已保存: {output_path}")


def auto_frame_camera(camera, model_center, model_size):
    """自动调整相机距离以框住模型"""
    cam_pos = Vector(camera.location)
    direction = (cam_pos - model_center).normalized()
    max_dim = max(model_size.x, model_size.y, model_size.z)
    # 根据FOV计算合适距离
    fov = camera.data.angle
    distance = (max_dim / 2) / math.tan(fov / 2) * 1.3  # 1.3倍余量
    camera.location = model_center + direction * distance


def main():
    args = parse_args()
    preset = load_preset(args.preset)

    print(f"[渲染] 模型: {args.input}")
    print(f"[渲染] 引擎: {preset.get('engine', 'EEVEE')}")
    print(f"[渲染] 输出: {args.output_dir}")

    # 清空场景
    clear_scene()

    # 导入模型
    objects = import_glb(args.input)
    model_center, model_size = get_model_bounds(objects)
    print(f"[渲染] 模型中心: {model_center}, 尺寸: {model_size}")

    # 设置场景
    setup_render_settings(preset)
    setup_lighting(preset)
    setup_background(preset)
    setup_ground_plane(preset, model_center, model_size)

    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 渲染各角度
    cameras = preset.get("cameras", {})
    for view_name, cam_config in cameras.items():
        camera = create_camera(
            position=cam_config["position"],
            look_at=cam_config.get("look_at", [0, 0, 0.6]),
            name=f"Camera_{view_name}",
        )
        auto_frame_camera(camera, model_center, model_size)

        output_path = os.path.join(args.output_dir, f"{view_name}.png")
        render_view(camera, output_path)

        # 删除临时相机
        bpy.data.objects.remove(camera, do_unlink=True)

    print(f"[渲染] 全部完成! 共渲染 {len(cameras)} 个视角")


if __name__ == "__main__":
    main()
