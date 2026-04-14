#!/usr/bin/env python3
"""
潮玩设计自动化流水线 - 主编排脚本
将2D概念图经过完整流水线转化为CNC加工文件

用法:
  python3 scripts/pipeline.py --input concept.png --project my_figure
  python3 scripts/pipeline.py --input concept.png --project my_figure --stage render
  python3 scripts/pipeline.py --input concept.png --project my_figure --stage all --style cute
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


STAGES = ["2d-to-3d", "render", "split", "cnc"]


def run_command(cmd: list[str], description: str) -> bool:
    """执行子命令并打印输出"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    print(f"  命令: {' '.join(cmd)}\n")

    start = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n[流水线] 错误: {description} 失败 (退出码: {result.returncode})")
        return False

    print(f"\n[流水线] {description} 完成 ({elapsed:.1f}s)")
    return True


def ensure_dir(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)


def stage_2d_to_3d(args, project_dir: str) -> bool:
    """阶段1: 2D → 3D"""
    output_glb = os.path.join(project_dir, "model.glb")
    cmd = [
        "python3", "scripts/api_convert.py",
        "--input", args.input,
        "--output", output_glb,
        "--style", args.style,
        "--config", "config/api.yaml",
    ]
    return run_command(cmd, "阶段1: 2D概念图 → 3D模型")


def stage_render(args, project_dir: str) -> bool:
    """阶段2: 渲染"""
    input_glb = os.path.join(project_dir, "model.glb")
    if not os.path.exists(input_glb):
        print(f"[流水线] 错误: 找不到模型文件 {input_glb}")
        print("[流水线] 请先执行 2d-to-3d 阶段，或手动放置GLB文件")
        return False

    renders_dir = os.path.join(project_dir, "renders")
    ensure_dir(renders_dir)

    cmd = [
        "blender", "--background", "--python", "scripts/render_turntable.py",
        "--",
        "--input", input_glb,
        "--output-dir", renders_dir,
        "--preset", "config/render_presets.yaml",
    ]
    return run_command(cmd, "阶段2: 3D渲染预览")


def stage_split(args, project_dir: str) -> bool:
    """阶段3: 拆件"""
    input_glb = os.path.join(project_dir, "model.glb")
    if not os.path.exists(input_glb):
        print(f"[流水线] 错误: 找不到模型文件 {input_glb}")
        return False

    parts_dir = os.path.join(project_dir, "parts")
    ensure_dir(parts_dir)

    cmd = [
        "blender", "--background", "--python", "scripts/part_split.py",
        "--",
        "--input", input_glb,
        "--output-dir", parts_dir,
        "--rules", "config/split_rules.yaml",
        "--category", "figure",
    ]
    return run_command(cmd, "阶段3: 拆件")


def stage_cnc(args, project_dir: str) -> bool:
    """阶段4: CNC导出"""
    parts_dir = os.path.join(project_dir, "parts")
    if not os.path.exists(parts_dir) or not list(Path(parts_dir).glob("*.stl")):
        print(f"[流水线] 错误: 在 {parts_dir} 中没有找到STL部件文件")
        print("[流水线] 请先执行 split 阶段")
        return False

    gcode_dir = os.path.join(project_dir, "gcode")
    ensure_dir(gcode_dir)

    cmd = [
        "python3", "scripts/generate_gcode.py",
        "--input-dir", parts_dir,
        "--output-dir", gcode_dir,
        "--config", "config/cnc_params.yaml",
    ]
    return run_command(cmd, "阶段4: CNC G-code导出")


def print_summary(project_dir: str):
    """打印项目输出摘要"""
    print(f"\n{'='*60}")
    print("  流水线完成 - 输出摘要")
    print(f"{'='*60}")

    for root, dirs, files in os.walk(project_dir):
        level = root.replace(project_dir, "").count(os.sep)
        indent = "  " * level
        folder = os.path.basename(root)
        print(f"{indent}{folder}/")
        sub_indent = "  " * (level + 1)
        for file in sorted(files):
            filepath = os.path.join(root, file)
            size = os.path.getsize(filepath)
            if size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            print(f"{sub_indent}{file}  ({size_str})")


def main():
    parser = argparse.ArgumentParser(
        description="潮玩设计自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 全流程
  python3 scripts/pipeline.py --input concept.png --project my_figure

  # 仅2D转3D
  python3 scripts/pipeline.py --input concept.png --project my_figure --stage 2d-to-3d

  # 从渲染开始（已有GLB）
  python3 scripts/pipeline.py --project my_figure --stage render

  # 仅CNC导出
  python3 scripts/pipeline.py --project my_figure --stage cnc
        """,
    )
    parser.add_argument("--input", "-i", default=None, help="概念图文件路径（2d-to-3d阶段必需）")
    parser.add_argument("--project", "-p", required=True, help="项目名称（用于输出目录）")
    parser.add_argument("--stage", "-s", default="all",
                        choices=["2d-to-3d", "render", "split", "cnc", "all"],
                        help="执行阶段（默认: all）")
    parser.add_argument("--style", default="standard",
                        choices=["standard", "cute", "realistic", "cartoon"],
                        help="风格参数（默认: standard）")
    parser.add_argument("--output-root", default="output", help="输出根目录（默认: output）")
    args = parser.parse_args()

    project_dir = os.path.join(args.output_root, args.project)
    ensure_dir(project_dir)

    print(f"[流水线] 项目: {args.project}")
    print(f"[流水线] 输出: {project_dir}")
    print(f"[流水线] 阶段: {args.stage}")
    if args.input:
        print(f"[流水线] 输入: {args.input}")

    # 确定要执行的阶段
    if args.stage == "all":
        stages_to_run = STAGES
    else:
        stages_to_run = [args.stage]

    # 2d-to-3d 需要输入图片
    if "2d-to-3d" in stages_to_run and not args.input:
        print("[流水线] 错误: 2d-to-3d 阶段需要 --input 参数指定概念图", file=sys.stderr)
        sys.exit(1)

    stage_funcs = {
        "2d-to-3d": stage_2d_to_3d,
        "render": stage_render,
        "split": stage_split,
        "cnc": stage_cnc,
    }

    total_start = time.time()
    success_count = 0

    for stage_name in stages_to_run:
        func = stage_funcs[stage_name]
        if func(args, project_dir):
            success_count += 1
        else:
            print(f"\n[流水线] 在阶段 '{stage_name}' 中止")
            sys.exit(1)

    total_elapsed = time.time() - total_start

    print_summary(project_dir)
    print(f"\n[流水线] 全部完成! {success_count}/{len(stages_to_run)} 阶段成功, 总耗时 {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
