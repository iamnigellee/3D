---
name: toy-design
description: >
  潮玩设计自动化流水线 - 从2D概念图到CNC加工的全流程自动化。
  当用户提供概念图并想生成3D模型、渲染预览、拆件或导出CNC加工文件时触发。
user-invocable: true
argument-hint: <image-path> [--stage 2d-to-3d|render|split|cnc|all] [--style cute|realistic|cartoon]
allowed-tools: Bash Read Write Edit Glob Grep WebFetch
when_to_use: >
  当用户要求从2D概念图生成3D模型、潮玩设计、手办建模、3D渲染、
  拆件、CNC加工导出、或提到玩具设计自动化流水线时使用
---

# 潮玩设计自动化流水线

将2D概念图转化为可CNC加工的3D潮玩手办，全流程自动化。

## 流水线概览

```
2D概念图 → 3D建模(API) → 渲染预览 → 拆件 → CNC导出
```

## 使用方式

```
/toy-design path/to/concept.png
/toy-design path/to/concept.png --stage render
/toy-design path/to/concept.png --stage all --style cute
```

## 参数解析

- `$ARGUMENTS` 中第一个参数为图片路径
- `--stage` 指定执行阶段（默认 `all` 全流程）：
  - `2d-to-3d` - 仅执行2D转3D
  - `render` - 仅渲染（需已有GLB文件）
  - `split` - 仅拆件（需已有GLB文件）
  - `cnc` - 仅CNC导出（需已有拆件结果）
  - `all` - 全流程
- `--style` 风格参数传递给3D生成API

## 执行流程

### 阶段1：2D → 3D建模

参考 [2d-to-3d.md](stages/2d-to-3d.md)

1. 读取概念图文件
2. 调用3D生成API，传入图片
3. 接收返回的GLB文件，保存到 `output/{project_name}/model.glb`
4. 验证GLB文件完整性

### 阶段2：3D渲染预览

参考 [rendering.md](stages/rendering.md)

1. 加载GLB模型到Blender
2. 应用预设材质和灯光方案
3. 渲染多角度预览图（正面、侧面、3/4视角、背面）
4. 输出到 `output/{project_name}/renders/`

### 阶段3：拆件

参考 [part-split.md](stages/part-split.md)

1. 加载GLB模型到Blender
2. 根据品类规则（公仔手办）执行自动拆件
3. 标准部件：头、身体、左臂、右臂、左腿、右腿、底座
4. 导出各部件为独立STL文件到 `output/{project_name}/parts/`

### 阶段4：CNC导出

参考 [cnc-export.md](stages/cnc-export.md)

1. 加载各部件STL
2. 根据机床配置生成加工策略
3. 导出G-code到 `output/{project_name}/gcode/`

## 输出目录结构

```
output/{project_name}/
├── model.glb              # 原始3D模型
├── renders/               # 渲染预览图
│   ├── front.png
│   ├── side_left.png
│   ├── side_right.png
│   ├── quarter.png
│   └── back.png
├── parts/                 # 拆件结果
│   ├── head.stl
│   ├── body.stl
│   ├── arm_left.stl
│   ├── arm_right.stl
│   ├── leg_left.stl
│   ├── leg_right.stl
│   └── base.stl
└── gcode/                 # CNC加工文件
    ├── head.gcode
    ├── body.gcode
    └── ...
```

## 配置文件

- API配置：`config/api.yaml`
- 渲染预设：`config/render_presets.yaml`
- 拆件规则：`config/split_rules.yaml`
- CNC参数：`config/cnc_params.yaml`
