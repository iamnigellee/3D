# 阶段4：CNC导出

## 流程

1. **加载部件**：读取各STL部件文件
2. **加工策略**：根据部件特征生成刀路
3. **参数应用**：加载机床和材料参数
4. **G-code生成**：导出加工文件
5. **模拟验证**：（可选）检查刀路碰撞

## 执行

```bash
python3 scripts/generate_gcode.py \
  --input-dir output/<project>/parts/ \
  --output-dir output/<project>/gcode/ \
  --config config/cnc_params.yaml
```

## 加工策略

| 工序 | 刀具 | 说明 |
|------|------|------|
| 粗加工 | 平底刀 6mm | 快速去料，留余量0.5mm |
| 半精加工 | 球头刀 3mm | 接近最终形状，留余量0.1mm |
| 精加工 | 球头刀 1mm | 最终表面，步距0.05mm |

## 机床参数（通用模板）

从 `config/cnc_params.yaml` 读取，机床型号待定时使用保守参数：

```yaml
spindle_speed: 12000    # 主轴转速 RPM
feed_rate: 800          # 进给速度 mm/min
plunge_rate: 300        # 下刀速度 mm/min
safe_height: 10         # 安全高度 mm
stock_margin: 2         # 毛坯余量 mm
```

## 材料预设

- **发泡PU**：高转速低进给，适合原型
- **代木（Renshape）**：中等参数，精度好
- **铝合金**：低转速低进给，需冷却液
- **树脂**：中等参数，注意排屑

## 执行指令

当执行此阶段时，Claude应该：

1. 检查parts/目录中的STL文件
2. 确认机床参数配置（如未配置，使用通用保守参数并警告用户）
3. 为每个部件生成G-code
4. 报告预计加工时间和各文件路径

## 注意事项

- 机床型号未确定前使用保守参数
- 生成的G-code应先在模拟器中验证再上机
- 用户应根据实际机床调整 `config/cnc_params.yaml`
