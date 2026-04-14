#!/usr/bin/env python3
"""
G-code生成脚本 - 从STL部件生成CNC加工文件
基于简化的3轴铣削刀路规划
"""

import argparse
import datetime
import os
import struct
import sys
from pathlib import Path

import numpy as np
import yaml


def load_config(config_path: str = "config/cnc_params.yaml") -> dict:
    """加载CNC参数配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_stl_binary(filepath: str) -> dict:
    """
    读取二进制STL文件

    Returns:
        dict with 'vertices', 'normals', 'faces' as numpy arrays
    """
    with open(filepath, "rb") as f:
        header = f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]

        vertices = []
        normals = []

        for _ in range(num_triangles):
            normal = struct.unpack("<3f", f.read(12))
            v1 = struct.unpack("<3f", f.read(12))
            v2 = struct.unpack("<3f", f.read(12))
            v3 = struct.unpack("<3f", f.read(12))
            _ = f.read(2)  # attribute byte count

            normals.append(normal)
            vertices.extend([v1, v2, v3])

    return {
        "vertices": np.array(vertices),
        "normals": np.array(normals),
        "num_triangles": num_triangles,
    }


def read_stl_ascii(filepath: str) -> dict:
    """读取ASCII STL文件"""
    vertices = []
    normals = []

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("facet normal"):
                parts = line.split()
                normals.append([float(parts[2]), float(parts[3]), float(parts[4])])
            elif line.startswith("vertex"):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])

    return {
        "vertices": np.array(vertices),
        "normals": np.array(normals),
        "num_triangles": len(normals),
    }


def read_stl(filepath: str) -> dict:
    """自动检测并读取STL文件"""
    with open(filepath, "rb") as f:
        header = f.read(80)

    if header[:5] == b"solid" and b"\x00" not in header:
        try:
            return read_stl_ascii(filepath)
        except (ValueError, IndexError):
            pass
    return read_stl_binary(filepath)


def get_model_bounds(stl_data: dict):
    """计算模型边界"""
    verts = stl_data["vertices"]
    min_bound = verts.min(axis=0)
    max_bound = verts.max(axis=0)
    return min_bound, max_bound


def get_heightmap(stl_data: dict, resolution: float, min_bound, max_bound):
    """
    从STL生成高度图 (从Z+方向俯视)

    Args:
        stl_data: STL数据
        resolution: 栅格分辨率 (mm)
        min_bound: 最小边界
        max_bound: 最大边界

    Returns:
        2D numpy array, 每个栅格存储该位置的最大Z值
    """
    verts = stl_data["vertices"]
    nx = int(np.ceil((max_bound[0] - min_bound[0]) / resolution)) + 1
    ny = int(np.ceil((max_bound[1] - min_bound[1]) / resolution)) + 1

    heightmap = np.full((ny, nx), min_bound[2])

    # 对每个三角面片光栅化
    num_tri = stl_data["num_triangles"]
    for i in range(num_tri):
        tri = verts[i * 3: i * 3 + 3]
        # 简化：取三角形在XY平面的包围盒
        tri_min_x = max(0, int((tri[:, 0].min() - min_bound[0]) / resolution))
        tri_max_x = min(nx - 1, int((tri[:, 0].max() - min_bound[0]) / resolution))
        tri_min_y = max(0, int((tri[:, 1].min() - min_bound[1]) / resolution))
        tri_max_y = min(ny - 1, int((tri[:, 1].max() - min_bound[1]) / resolution))

        z_max = tri[:, 2].max()

        for iy in range(tri_min_y, tri_max_y + 1):
            for ix in range(tri_min_x, tri_max_x + 1):
                heightmap[iy, ix] = max(heightmap[iy, ix], z_max)

    return heightmap


def apply_material(config: dict, material_name: str, operation: dict) -> dict:
    """根据材料调整加工参数"""
    materials = config.get("materials", {})
    mat = materials.get(material_name, {})

    adjusted = dict(operation["params"])
    if "spindle_speed" in adjusted:
        adjusted["spindle_speed"] = int(adjusted["spindle_speed"] * mat.get("spindle_multiplier", 1.0))
    if "feed_rate" in adjusted:
        adjusted["feed_rate"] = int(adjusted["feed_rate"] * mat.get("feed_multiplier", 1.0))
    if "plunge_rate" in adjusted:
        adjusted["plunge_rate"] = int(adjusted["plunge_rate"] * mat.get("feed_multiplier", 1.0))

    return adjusted


def generate_roughing_gcode(heightmap, params, safety, min_bound, resolution, stock_z):
    """
    生成粗加工刀路 (分层等高线加工)

    Returns:
        list of G-code lines
    """
    lines = []
    stepdown = params.get("stepdown", 2.0)
    stepover = params.get("stepover_ratio", 0.4) * params.get("tool_diameter", 6.0)
    safe_h = safety["safe_height"]
    feed = params["feed_rate"]
    plunge = params["plunge_rate"]
    stock_to_leave = params.get("stock_to_leave", 0.5)

    lines.append(f"S{params['spindle_speed']} M3 ; 主轴启动")
    lines.append(f"G0 Z{safe_h} ; 移至安全高度")

    ny, nx = heightmap.shape

    # 分层下切
    current_z = stock_z
    target_min = heightmap.min() + stock_to_leave

    while current_z > target_min:
        current_z = max(current_z - stepdown, target_min)
        lines.append(f"; --- 层 Z={current_z:.2f} ---")

        # Zigzag刀路
        row_step = max(1, int(stepover / resolution))
        direction = 1

        for iy in range(0, ny, row_step):
            y = min_bound[1] + iy * resolution

            if direction == 1:
                x_range = range(nx)
            else:
                x_range = range(nx - 1, -1, -1)

            first_move = True
            for ix in x_range:
                x = min_bound[0] + ix * resolution
                target_z = max(current_z, heightmap[iy, ix] + stock_to_leave)

                if first_move:
                    lines.append(f"G0 X{x:.3f} Y{y:.3f}")
                    lines.append(f"G1 Z{target_z:.3f} F{plunge}")
                    first_move = False
                else:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{target_z:.3f} F{feed}")

            lines.append(f"G0 Z{safe_h}")
            direction *= -1

    return lines


def generate_finishing_gcode(heightmap, params, safety, min_bound, resolution):
    """
    生成精加工刀路 (等距行切)

    Returns:
        list of G-code lines
    """
    lines = []
    stepover = params.get("stepover", 0.05)
    safe_h = safety["safe_height"]
    feed = params["feed_rate"]
    plunge = params["plunge_rate"]

    lines.append(f"S{params['spindle_speed']} M3 ; 主轴启动")
    lines.append(f"G0 Z{safe_h}")

    ny, nx = heightmap.shape
    row_step = max(1, int(stepover / resolution))
    direction = 1

    for iy in range(0, ny, row_step):
        y = min_bound[1] + iy * resolution

        if direction == 1:
            x_range = range(nx)
        else:
            x_range = range(nx - 1, -1, -1)

        first_move = True
        for ix in x_range:
            x = min_bound[0] + ix * resolution
            z = heightmap[iy, ix]

            if first_move:
                lines.append(f"G0 X{x:.3f} Y{y:.3f}")
                lines.append(f"G1 Z{z:.3f} F{plunge}")
                first_move = False
            else:
                lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feed}")

        lines.append(f"G0 Z{safe_h}")
        direction *= -1

    return lines


def generate_gcode_for_part(stl_path: str, output_path: str, config: dict):
    """
    为单个部件生成完整G-code

    Args:
        stl_path: STL文件路径
        output_path: G-code输出路径
        config: CNC参数配置
    """
    part_name = Path(stl_path).stem
    material_name = config.get("default_material", "foam_pu")
    safety = config["safety"]
    gcode_cfg = config.get("gcode", {})
    operations = config["operations"]

    print(f"[CNC] 处理部件: {part_name}")

    # 读取STL
    stl_data = read_stl(stl_path)
    min_bound, max_bound = get_model_bounds(stl_data)
    print(f"[CNC]   尺寸: X={max_bound[0]-min_bound[0]:.1f} Y={max_bound[1]-min_bound[1]:.1f} Z={max_bound[2]-min_bound[2]:.1f} mm")
    print(f"[CNC]   三角面数: {stl_data['num_triangles']}")

    # 毛坯高度
    stock_margin = safety.get("stock_margin", 2)
    stock_z = max_bound[2] + stock_margin

    # 生成高度图
    resolution = 0.5  # 粗加工分辨率 0.5mm
    heightmap = get_heightmap(stl_data, resolution, min_bound, max_bound)

    # 组装G-code
    lines = []

    # 文件头
    header = gcode_cfg.get("header_template", "").format(
        part_name=part_name,
        material=material_name,
        date=datetime.date.today().isoformat(),
    )
    lines.append(header)

    # 粗加工
    roughing = operations.get("roughing", {})
    if roughing:
        rough_params = apply_material(config, material_name, roughing)
        rough_params["tool_diameter"] = roughing["tool"]["diameter"]
        lines.append(f"; === 粗加工: {roughing.get('description', '')} ===")
        lines.append(f"; 刀具: {roughing['tool']['type']} D{roughing['tool']['diameter']}")
        lines.append("M0 ; 请装载粗加工刀具，按继续")
        lines.extend(generate_roughing_gcode(heightmap, rough_params, safety, min_bound, resolution, stock_z))
        lines.append("M5 ; 主轴停止")
        lines.append("")

    # 精加工（使用更高分辨率）
    finishing = operations.get("finishing", {})
    if finishing:
        resolution_fine = 0.1  # 精加工 0.1mm
        heightmap_fine = get_heightmap(stl_data, resolution_fine, min_bound, max_bound)
        finish_params = apply_material(config, material_name, finishing)
        lines.append(f"; === 精加工: {finishing.get('description', '')} ===")
        lines.append(f"; 刀具: {finishing['tool']['type']} D{finishing['tool']['diameter']}")
        lines.append("M0 ; 请装载精加工刀具，按继续")
        lines.extend(generate_finishing_gcode(heightmap_fine, finish_params, safety, min_bound, resolution_fine))
        lines.append("M5 ; 主轴停止")

    # 文件尾
    footer = gcode_cfg.get("footer_template", "M5\nG28\nM30")
    lines.append(footer)

    # 写入文件
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"[CNC]   G-code已保存: {output_path} ({len(lines)} 行)")


def main():
    parser = argparse.ArgumentParser(description="STL → G-code 生成器")
    parser.add_argument("--input-dir", "-i", required=True, help="STL部件目录")
    parser.add_argument("--output-dir", "-o", required=True, help="G-code输出目录")
    parser.add_argument("--config", "-c", default="config/cnc_params.yaml", help="CNC参数配置")
    parser.add_argument("--material", "-m", default=None, help="覆盖默认材料")
    parser.add_argument("--part", "-p", default=None, help="只处理指定部件（不含扩展名）")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.material:
        config["default_material"] = args.material

    # 检查机床配置
    machine = config.get("machine", {})
    if machine.get("name") == "generic_3axis":
        print("[CNC] 警告: 使用通用机床参数，请根据实际机床调整 config/cnc_params.yaml")

    # 查找所有STL文件
    stl_files = sorted(Path(args.input_dir).glob("*.stl"))
    if args.part:
        stl_files = [f for f in stl_files if f.stem == args.part]

    if not stl_files:
        print(f"[CNC] 错误: 在 {args.input_dir} 中没有找到STL文件", file=sys.stderr)
        sys.exit(1)

    print(f"[CNC] 找到 {len(stl_files)} 个部件")
    print(f"[CNC] 材料: {config.get('default_material', 'unknown')}")

    os.makedirs(args.output_dir, exist_ok=True)

    for stl_path in stl_files:
        output_path = os.path.join(args.output_dir, f"{stl_path.stem}.gcode")
        generate_gcode_for_part(str(stl_path), output_path, config)

    print(f"\n[CNC] 全部完成! 共生成 {len(stl_files)} 个G-code文件")
    print("[CNC] 提醒: 上机前请在G-code模拟器中验证刀路")


if __name__ == "__main__":
    main()
