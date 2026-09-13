# gap_zone.py — 交接文档

## 背景 / 目标

[gap_analysis.py](gap_analysis.md) 比较的是三个固定角色（4TB-HD / macbook / NAS-YuData）。这里的场景不同：多个"zone"文件夹（`inputs/zones/zone-I/`、`inputs/zones/zone-II/`……），彼此是平级关系，没有谁是"源头"谁是"暂存区"的角色划分，只需要知道"这个 zone 有、那个 zone 没有"的差异。

## 输入

```
inputs/zones/<zone-name>/*.txt
```

每行格式与 [gap_analysis.py](gap_analysis.md) 一致：`<字节数> bytes <完整路径>`。`<zone-name>` 就是文件夹名（如 `zone-I`），脚本自动扫描 `inputs/zones/` 下的所有子文件夹当作 zone，不需要在代码里写死名字。

## 匹配逻辑

与 [gap_analysis.py](gap_analysis.md) 完全一致，直接 import 复用其函数（`Record` / `load_dir` / `keys_of` / `first_path_by_key` / `suspected_renames` / `write_path_list`），没有重新实现比对逻辑：

- 精确匹配 = `(size, 文件名小写去空格)` 相同。
- 疑似改名 = 同 size、不同文件名 → 只列 `suspected_renames.csv` 给人工看，不自动判定。

不同点：`gap_zone.py` 会对发现的所有 zone 两两组合（`itertools.combinations`）逐对比较，不限于2个 zone——如果以后加了 `zone-III`，会自动多出 `zone-I_vs_zone-III`、`zone-II_vs_zone-III` 两组对比，不用改代码。

## 输出

```
outputs/YYYY-MM-DD-zone-gap/
  {zone_a}_vs_{zone_b}_only_in_{zone_a}.txt   # zone_a 有、zone_b 没有
  {zone_a}_vs_{zone_b}_only_in_{zone_b}.txt   # zone_b 有、zone_a 没有
  {zone_a}_vs_{zone_b}_in_both.txt            # 两边都有（路径取 zone_a 那边的）
  {zone_a}_vs_{zone_b}_suspected_renames.csv
  summary.csv                                  # 汇总所有 zone 对
```

`zone_a` / `zone_b` 按文件夹名排序后两两配对，保证同一对 zone 每次跑出来的文件名前缀一致。

## 编码

统一用 `encoding="utf-8-sig"`（带 BOM），包括 `.txt` 路径清单——这一点和 [gap_analysis.py 历史设计](gap_analysis.md#输出编码)不同，那边的 `.txt` 最初刻意不加 BOM 是为了直接喂给 `cp` 脚本。2026-09-12 已确认全项目统一优先保证 Excel 可读性，改为都加 BOM。**如果以后要写消费 `gap_zone.py` 输出 `.txt` 的自动化脚本（比如批量 `cp` 同步 zone 差异），第一行需要先剥掉 BOM**，处理方式同 [gap_analysis.md](gap_analysis.md#输出编码) 里写的一样。

## 没有淘汰清单（rejected_ledger）机制

zone 之间是平级关系，不存在"暂存区会被清空重来"的语义，所以没有移植 [gap_analysis.py](gap_analysis.md) 里 `state/` 下的 snapshot + ledger 机制。每次跑都是无状态的全量对比。
