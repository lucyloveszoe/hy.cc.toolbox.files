# gap_precheck.py — 交接文档

## 背景 / 目标

在跑 [gap_analysis.py](gap_analysis.md) 的三方对比之前，先检查每个来源**内部**有没有重复文件。三方对比的前提是"每边内部干净"，如果来源本身混入大量重复文件，会污染后续"待上传"/"待复制"的判断（比如同一个文件被算了两次占用空间）。

目前检查的来源：`inputs/NAS-YuData/`、`inputs/macbook/`。

## 判定逻辑

复用 [gap_analysis.py](gap_analysis.md) 的 `Record` / `load_dir`（同一套"字节数 + 归一化文件名"匹配规则，见该文档"匹配设计与理由"一节），只是比对范围从"跨来源"收窄到"单一来源内部"：

- **confirmed duplicate（确定重复）**：同一来源内，`(size, 归一化文件名)` 完全一致，出现超过1次。
- **suspected duplicate（疑似重复）**：同一来源内，size 相同但文件名不同，只列出人工核对，不自动判定。

## 输出

```
outputs/YYYY-MM-DD-precheck/
  NAS-YuData_duplicates_confirmed.csv
  NAS-YuData_duplicates_suspected.csv
  macbook_duplicates_confirmed.csv
  macbook_duplicates_suspected.csv
  summary.csv
```

每个 duplicates csv 列：`group_id, size_bytes, filename, path`——同一 group_id 的多行就是被判定为重复/疑似重复的一组文件。

`summary.csv` 列：`category, group_count, file_count, redundant_file_count, total_size_gb`。`redundant_file_count` 只在 confirmed 类别里有意义（= 总文件数 - 组数，即"多出来的、可以删的份数"）；suspected 类别这一列留空，因为疑似重复不能自动判定该删哪一份。

## 编码

所有输出统一用 `encoding="utf-8-sig"`（带 BOM），因为这些 csv 是给人在 Excel 里核对重复文件用的，不喂给下游脚本，不存在 [gap_analysis.md](gap_analysis.md) 里提到的"BOM 会破坏 cp 脚本第一行"的顾虑。

## 依赖关系

直接从 `gap_analysis.py` import `MACBOOK_DIR`、`NAS_DIR`、`OUTPUTS_DIR`、`gb`、`load_dir`，不重复实现文件扫描/解析逻辑，只加了"同来源内部分组"这一层（`find_confirmed_duplicates` / `find_suspected_duplicates`）。
