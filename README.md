# ToyDesign Pipeline

AI赋能的潮玩设计自动化流水线，从2D概念图到CNC加工的全流程自动化。

```
2D概念图 → 3D建模(API) → 渲染预览 → 拆件 → CNC导出
```

## 快速开始

### 环境准备

```bash
pip install -r requirements.txt
```

依赖：
- Python 3.10+
- Blender 3.6+（需在 PATH 中可用）
- 已配置的3D生成API

### 配置API

编辑 `config/api.yaml`，填入你的3D生成API地址：

```yaml
api_url: "https://your-api-endpoint.com/v1/generate3d"
api_key: "your-key-here"
```

### 运行

```bash
# 全流程
python3 scripts/pipeline.py --input concept.png --project my_figure

# 指定阶段
python3 scripts/pipeline.py --input concept.png --project my_figure --stage 2d-to-3d
python3 scripts/pipeline.py --project my_figure --stage render
python3 scripts/pipeline.py --project my_figure --stage split
python3 scripts/pipeline.py --project my_figure --stage cnc
```

在 Claude Code 中也可以通过 skill 调用：

```
/toy-design concept.png --style cute
```

## 流水线阶段

| 阶段 | 说明 | 输入 | 输出 |
|------|------|------|------|
| **2d-to-3d** | 调用API将概念图转为3D模型 | PNG/JPG/WEBP | `model.glb` |
| **render** | Blender headless 五角度渲染 | GLB | `renders/*.png` |
| **split** | 按公仔规则自动拆件，含榫卯结构 | GLB | `parts/*.stl` |
| **cnc** | 生成粗加工+精加工G-code | STL | `gcode/*.gcode` |

## 输出结构

```
output/{project}/
├── model.glb              # 3D模型
├── renders/               # 渲染图
│   ├── front.png
│   ├── side_left.png
│   ├── side_right.png
│   ├── quarter.png
│   └── back.png
├── parts/                 # 拆件
│   ├── head.stl
│   ├── body.stl
│   ├── arm_left.stl
│   ├── arm_right.stl
│   ├── leg_left.stl
│   ├── leg_right.stl
│   └── base.stl
└── gcode/                 # 加工文件
    ├── head.gcode
    └── ...
```

## 项目结构

```
├── .claude/skills/toy-design/   # Claude Code Skill 定义
│   ├── SKILL.md                 # Skill 入口
│   ├── stages/                  # 各阶段指令文档
│   └── examples/                # 示例工作流
├── config/                      # 配置文件
│   ├── api.yaml                 # 3D生成API
│   ├── render_presets.yaml      # 渲染预设（引擎/灯光/相机）
│   ├── split_rules.yaml         # 拆件规则（品类/切割位置/榫卯）
│   └── cnc_params.yaml          # CNC参数（机床/刀具/材料）
├── scripts/                     # 核心脚本
│   ├── pipeline.py              # 流水线编排器
│   ├── api_convert.py           # 2D→3D API调用
│   ├── render_turntable.py      # Blender渲染
│   ├── part_split.py            # Blender拆件
│   └── generate_gcode.py        # G-code生成
└── requirements.txt
```

## 配置说明

### 渲染 (`config/render_presets.yaml`)

- **引擎**：EEVEE（快速预览）/ CYCLES（高质量）
- **灯光**：三点布光（主光 + 补光 + 轮廓光）
- **相机**：5个预设角度，85mm镜头，自动框取模型

### 拆件 (`config/split_rules.yaml`)

当前支持品类：
- **figure**（公仔手办）：头 / 身体 / 左臂 / 右臂 / 左腿 / 右腿 / 底座

连接方式：
- 圆柱榫：头部、腿部（可拆卸）
- 球榫：手臂关节（可转动）
- 默认公差 0.2mm

### CNC (`config/cnc_params.yaml`)

三道工序：
1. **粗加工**：平底刀 6mm，步距40%刀径
2. **半精加工**：球头刀 3mm
3. **精加工**：球头刀 1mm，步距0.05mm

材料预设：发泡PU / 代木 / 树脂 / 铝合金

## License

MIT
