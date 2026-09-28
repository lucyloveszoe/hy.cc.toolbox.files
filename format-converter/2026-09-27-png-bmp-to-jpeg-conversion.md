# PNG/BMP 转 JPEG 工具

## 任务说明

递归转换指定文件夹（含所有子文件夹）内的 PNG 和 BMP 图片为 JPEG 格式，
JPEG 保存质量固定为 90。转换成功并校验通过后，删除原始 PNG/BMP 文件，
只保留 JPEG。

## 环境搭建

```
py -3.12 -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

venv 和依赖已在本次会话中创建并验证，无需重复执行，除非 venv 被删除。

### 关于 pip 源

公司内部 Artifactory 源（`usw2p-edge.packages.broadcom.net`）在当前网络下
DNS 无法解析（可能需要连 VPN）。已改用公网 PyPI（`pypi.org`），并写入
`venv/pip.ini`（仅作用于本 venv，不影响系统/用户级 pip 全局配置），
之后在本 venv 下执行 `pip install` 会自动使用公网源，无需每次手动加
`--index-url`。如果 venv 被删除重建，需要重新创建该文件：

```
[global]
index-url = https://pypi.org/simple
```

## 使用方法

```
./venv/Scripts/python.exe convert_to_jpeg.py <目标文件夹路径>
```

- `<目标文件夹路径>` 为命令行参数，可以是任意文件夹。
- 脚本会递归处理该文件夹下所有子文件夹中的 `.png` / `.bmp` 文件
  （大小写不敏感）。

## 转换规则

1. 每张图片以 JPEG quality=90 保存，文件名不变，扩展名改为 `.jpg`。
2. 保存后立即重新打开新 JPEG 文件做校验，确认可正常读取，再删除原始
   PNG/BMP 文件；若校验失败则删除刚生成的坏 JPEG 并保留原图，标记为
   FAILED。
3. 若目标位置已存在同名 `.jpg` 文件，跳过该文件（不覆盖），标记为
   SKIPPED，原始 PNG/BMP 文件保留。
4. 带透明通道（RGBA/LA）或调色板模式（P）的 PNG 会先转换为 RGB 再保存
   为 JPEG（JPEG 不支持透明通道）。

## 输出说明

脚本运行时会逐个打印处理结果（OK / SKIPPED / FAILED），并在末尾输出
汇总统计：转换成功数、跳过数、失败数。

## 测试记录

已在临时测试文件夹中验证以下场景，均符合预期：

| 场景 | 结果 |
|---|---|
| 普通 PNG（顶层文件夹） | 转换成功，原文件删除 |
| 带透明通道的 PNG（子文件夹） | 转换成功，透明区域填充为 RGB |
| 调色板模式（P）PNG | 转换成功 |
| 普通 BMP | 转换成功，原文件删除 |
| 目标 `.jpg` 已存在（同名冲突） | 跳过，原 PNG 保留未删除 |

## 已知限制

- 不支持递归以外的图片格式（如 TIFF、WebP）；如需支持，需扩展
  `SOURCE_EXTENSIONS`。
- 未提供 dry-run（预览不执行）模式；如需在正式执行前先查看将被转换/
  删除的文件清单，需要另行开发。
