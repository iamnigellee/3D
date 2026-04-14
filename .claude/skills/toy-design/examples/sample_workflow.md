# 示例工作流：从概念图到CNC加工

## 场景

设计师完成了一个潮玩公仔的概念图 `designs/bunny_concept.png`，需要将其转化为可CNC加工的3D模型。

## 全流程执行

```bash
# 方式1: 通过 skill 调用（在 Claude Code 中）
/toy-design designs/bunny_concept.png --style cute

# 方式2: 直接运行流水线脚本
python3 scripts/pipeline.py \
  --input designs/bunny_concept.png \
  --project bunny_v1 \
  --style cute
```

## 分阶段执行

### 步骤1: 2D → 3D

```bash
python3 scripts/pipeline.py \
  --input designs/bunny_concept.png \
  --project bunny_v1 \
  --stage 2d-to-3d \
  --style cute
```

输出: `output/bunny_v1/model.glb`

### 步骤2: 渲染预览

```bash
# 如果对模型满意，生成多角度渲染图
python3 scripts/pipeline.py \
  --project bunny_v1 \
  --stage render
```

输出:
```
output/bunny_v1/renders/
├── front.png
├── side_left.png
├── side_right.png
├── quarter.png
└── back.png
```

### 步骤3: 拆件

```bash
python3 scripts/pipeline.py \
  --project bunny_v1 \
  --stage split
```

输出:
```
output/bunny_v1/parts/
├── head.stl       # 头部（含圆柱公榫）
├── body.stl       # 身体（顶部含母榫）
├── arm_left.stl   # 左臂
├── arm_right.stl  # 右臂
├── leg_left.stl   # 左腿
├── leg_right.stl  # 右腿
└── base.stl       # 底座（自动生成）
```

### 步骤4: CNC导出

```bash
python3 scripts/pipeline.py \
  --project bunny_v1 \
  --stage cnc
```

输出:
```
output/bunny_v1/gcode/
├── head.gcode
├── body.gcode
├── arm_left.gcode
├── arm_right.gcode
├── leg_left.gcode
├── leg_right.gcode
└── base.gcode
```

## 自定义配置

### 修改API地址

编辑 `config/api.yaml`:
```yaml
api_url: "https://your-actual-api.com/v1/generate3d"
api_key: "your-key-here"
```

### 高质量渲染

编辑 `config/render_presets.yaml`:
```yaml
engine: "CYCLES"        # 改用Cycles渲染器
samples:
  cycles: 256           # 增加采样数
resolution:
  width: 3840           # 4K分辨率
  height: 2160
```

### 调整拆件规则

编辑 `config/split_rules.yaml`:
```yaml
# 调整颈部切割位置（如角色头大身小）
head:
  plane_position_ratio: 0.68  # 降低切割线
```

### 适配新机床

编辑 `config/cnc_params.yaml`:
```yaml
machine:
  name: "my_cnc_machine"
  controller: "fanuc"
gcode:
  dialect: "fanuc"
```
