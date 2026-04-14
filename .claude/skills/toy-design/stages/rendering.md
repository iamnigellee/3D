# 阶段2：3D渲染预览

## 流程

1. **加载模型**：在Blender中导入GLB文件
2. **场景设置**：应用预设灯光、材质、相机方案
3. **多角度渲染**：正面、左侧、右侧、3/4视角、背面
4. **输出图片**：保存到 renders/ 目录

## 执行

使用 Blender headless 模式运行渲染脚本：

```bash
blender --background --python scripts/render_turntable.py -- \
  --input output/<project>/model.glb \
  --output-dir output/<project>/renders/ \
  --preset config/render_presets.yaml
```

## 渲染预设

从 `config/render_presets.yaml` 读取：

- **分辨率**：1920x1080（默认）
- **渲染引擎**：EEVEE（快速预览）或 Cycles（高质量）
- **灯光方案**：三点布光（Key + Fill + Rim）
- **背景**：纯色/渐变/透明
- **相机角度**：
  - front: (0, -3, 1.2) 看向原点
  - side_left: (-3, 0, 1.2)
  - side_right: (3, 0, 1.2)
  - quarter: (-2.1, -2.1, 1.5)
  - back: (0, 3, 1.2)

## 执行指令

当执行此阶段时，Claude应该：

1. 检查GLB模型文件是否存在
2. 生成或更新渲染脚本（如模板需要定制）
3. 调用 Blender headless 执行渲染
4. 确认所有角度图片已生成
5. 向用户展示渲染结果路径
