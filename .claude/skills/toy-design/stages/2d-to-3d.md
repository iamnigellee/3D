# 阶段1：2D → 3D建模

## 流程

1. **验证输入**：检查概念图文件存在且格式正确（PNG/JPG/WEBP）
2. **调用API**：将图片发送到3D生成API
3. **接收模型**：下载返回的GLB文件
4. **质量检查**：验证GLB文件完整性（文件大小、格式头）

## API调用

使用 `scripts/api_convert.py` 执行转换：

```bash
python3 scripts/api_convert.py \
  --input <image_path> \
  --output output/<project>/model.glb \
  --style <style>
```

API配置从 `config/api.yaml` 读取：
- `api_url`：API端点地址
- `api_key`：鉴权密钥（如需要）
- `timeout`：超时时间（秒）
- `output_format`：固定为 `glb`

## 执行指令

当执行此阶段时，Claude应该：

1. 确认 `config/api.yaml` 中已配置API地址
2. 运行转换脚本
3. 检查输出文件是否生成成功
4. 报告模型基本信息（文件大小、顶点数等）

## 错误处理

- API不可达：提示用户检查网络和API配置
- 返回格式错误：提示用户检查API版本
- 文件过大（>100MB）：警告用户可能需要减面
