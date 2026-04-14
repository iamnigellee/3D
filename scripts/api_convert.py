#!/usr/bin/env python3
"""
2D概念图 → 3D模型 转换脚本
调用外部API将概念图转换为GLB格式3D模型
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml


def load_config(config_path: str = "config/api.yaml") -> dict:
    """加载API配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def encode_image(image_path: str) -> str:
    """将图片编码为base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_mime_type(image_path: str) -> str:
    """根据文件扩展名返回MIME类型"""
    ext = Path(image_path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return mime_map.get(ext, "image/png")


def call_api(image_path: str, config: dict, style: str = "standard") -> bytes:
    """
    调用3D生成API

    Args:
        image_path: 概念图路径
        config: API配置
        style: 风格参数

    Returns:
        GLB文件的二进制数据
    """
    api_url = config["api_url"]
    api_key = config.get("api_key", "")
    timeout = config.get("timeout", 120)
    params = config.get("params", {})

    # 构建请求头
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 构建请求体
    image_b64 = encode_image(image_path)
    mime_type = get_mime_type(image_path)

    payload = {
        "image": f"data:{mime_type};base64,{image_b64}",
        "output_format": "glb",
        "style": style,
        **params,
    }

    print(f"[2D→3D] 正在调用API: {api_url}")
    print(f"[2D→3D] 图片: {image_path} ({os.path.getsize(image_path) / 1024:.1f} KB)")
    print(f"[2D→3D] 风格: {style}")

    start_time = time.time()
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    elapsed = time.time() - start_time

    if response.status_code != 200:
        print(f"[2D→3D] API错误: HTTP {response.status_code}", file=sys.stderr)
        print(f"[2D→3D] 响应: {response.text[:500]}", file=sys.stderr)
        sys.exit(1)

    # 处理响应 - 支持两种格式：直接二进制 或 JSON包装
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = response.json()
        if "model" in data:
            glb_data = base64.b64decode(data["model"])
        elif "url" in data:
            print(f"[2D→3D] 从URL下载模型: {data['url']}")
            model_resp = requests.get(data["url"], timeout=timeout)
            glb_data = model_resp.content
        else:
            print("[2D→3D] 无法解析API响应格式", file=sys.stderr)
            sys.exit(1)
    else:
        glb_data = response.content

    print(f"[2D→3D] 完成! 耗时: {elapsed:.1f}s, 模型大小: {len(glb_data) / 1024:.1f} KB")
    return glb_data


def validate_glb(data: bytes) -> bool:
    """验证GLB文件格式"""
    # GLB文件魔数: 0x46546C67 ("glTF")
    if len(data) < 12:
        return False
    magic = data[:4]
    return magic == b"glTF"


def main():
    parser = argparse.ArgumentParser(description="2D概念图转3D模型")
    parser.add_argument("--input", "-i", required=True, help="概念图文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出GLB文件路径")
    parser.add_argument("--style", "-s", default="standard", help="风格: standard/cute/realistic/cartoon")
    parser.add_argument("--config", "-c", default="config/api.yaml", help="API配置文件路径")
    args = parser.parse_args()

    # 验证输入文件
    if not os.path.exists(args.input):
        print(f"[2D→3D] 错误: 找不到输入文件 {args.input}", file=sys.stderr)
        sys.exit(1)

    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    if Path(args.input).suffix.lower() not in valid_exts:
        print(f"[2D→3D] 错误: 不支持的图片格式，支持: {valid_exts}", file=sys.stderr)
        sys.exit(1)

    # 加载配置
    config = load_config(args.config)

    # 检查API配置
    if config["api_url"] == "https://your-api-endpoint.com/v1/generate3d":
        print("[2D→3D] 警告: 请先在 config/api.yaml 中配置实际的API地址", file=sys.stderr)
        sys.exit(1)

    # 创建输出目录
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # 调用API
    glb_data = call_api(args.input, config, style=args.style)

    # 验证GLB
    if not validate_glb(glb_data):
        print("[2D→3D] 错误: API返回的数据不是有效的GLB格式", file=sys.stderr)
        sys.exit(1)

    # 保存文件
    with open(args.output, "wb") as f:
        f.write(glb_data)

    file_size_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"[2D→3D] 模型已保存: {args.output} ({file_size_mb:.2f} MB)")

    if file_size_mb > 100:
        print("[2D→3D] 警告: 模型文件超过100MB，可能需要减面处理")


if __name__ == "__main__":
    main()
