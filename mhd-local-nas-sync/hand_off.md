# mhd-local-nas-sync — 交接文档

## 背景 / 目标

三个文件来源：
- `inputs/macbook/`（暂存区，清单会变）
- `inputs/NAS-YuData/`（最终备份目的地，清单会变，且包含其他来源的文件，不要求和4TB-HD/macbook对齐）
- `inputs/NoChange/4TB-HD/`（备份源头，只读，清单不变）

搬运流程：4TB-HD → 复制到 macbook 暂存 → 人工质检、删不合格的 → 上传到 NAS-YuData。

目标：识别三边的差异，找出"该复制""该上传""已完成""改名/移动导致误判"这几类文件。

## 数据格式（实测得到，非文档假设）

每行格式：`<字节数> bytes <完整路径>`。
`macbook/toupload.txt` 例外，多一个前导行号（`3\t123 bytes /path`），用同一条正则 `search` 而非 `match` 兼容，不用单独处理。

三边路径前缀不同（`/Users/yuhan/...`、`/Volumes/YuData/...`、`/Volumes/4TBS/...`），且分类 txt 文件名三边不对应（如 NAS 的"系列西方.23G.txt" vs macbook 的"local-系列西方.txt"，4TB-HD 里根本没有）。**结论：不能按分类文件名分组比对，必须把每边所有 txt 汇总成一张不分类的总表，逐条比对。**

## 匹配设计与理由

**核心信号：字节数（size）**，因为文件名会改、路径会变，但备份下来的文件字节数几乎不变。

- **精确匹配** = `(size, 文件名小写去空格)` 相同 → 判定同一文件。文件名要归一化是因为项目 `CLAUDE.md` 明确要求"所有字符串比较强制全小写+去空格"。允许路径不同，覆盖"移动到别的分类目录"的场景。
- **疑似改名**（同 size、文件名不同）→ **不自动判定为同一文件**，只列入 `suspected_renames.csv` 给人工看。这是用户明确选择的方案（讨论时给了三个选项：自动合并 / 只列疑似清单不自动认定 / 严格只认精确匹配，用户选了中间这个）。原因：字节数相同不代表一定是同一个文件，尤其小文件容易撞车；但完全不提示又会让真实改名被当成新文件重复搬运。
  - 验证效果：实测中成功识别出如"91新人Dr哥新作第七部-双飞女神…" (4TB) vs "第七部-双飞女神…" (macbook，标题被精简过) 这类真实改名，字节数一致（1515663693 bytes）。
- 未做基于文件名相似度的模糊匹配（如 `difflib`），当前只用"同 size 且未被精确匹配"这一个条件产生候选对。如果未来疑似清单噪音太大（尤其小文件、常见 size 撞车），可以加一层文件名相似度打分排序。

## 三组差异对比

1. **4TB-HD vs macbook**：4TB有、macbook没有 → 候选"待复制到暂存区"。
2. **macbook vs NAS-YuData**：macbook有、NAS没有 → "待上传"。
3. **4TB-HD vs NAS-YuData（直接对比，用户在讨论阶段主动要求加的）**：目的是识别"已经完成备份、不需要再经过 macbook 暂存"的文件，因为 macbook 会被清空/变化，不能只靠"现在macbook有没有"来判断是否要重新下载。

由 1+3 推出 `4tb_pending`（真正需要处理的）= 4TB有 AND macbook没有 AND NAS没有。

## 淘汰清单（rejected_ledger）— 解决的歧义

单看一次快照，无法区分"4TB文件不在macbook"是因为：
(a) 还没复制下来，还是
(b) 复制下来质检不合格，已经删除了。

如果不解决，每次跑都会把已经被人工淘汰过的文件重新列入"待复制"，造成重复劳动。

**方案**：脚本每次运行都把当前 macbook 清单存成快照 (`state/macbook_snapshot.csv`)。下次运行时对比新旧快照：如果某文件上次在、这次不在了，且从未出现在 NAS 里 → 判定为"质检淘汰"，自动写入 `state/rejected_ledger.csv`，以后自动从 `4tb_pending` 中排除。

**已知限制**：
- 第一次运行没有历史快照，淘汰识别从第二次运行起才生效（冷启动问题，用户已知晓并接受）。
- 这个判定是启发式的，不是100%准确——如果用户把文件从macbook移到了一个脚本没扫描到的地方（而不是删除），也会被误判为"淘汰"。目前没有反悔/纠正机制，如果误判需要手动编辑 `rejected_ledger.csv` 删除对应行。
- 曾在开发过程中改了垃圾文件过滤规则（新增过滤 `desktop.ini`/`Thumbs.db`），导致两次运行之间 macbook 清单"看起来变了"，产生了9条假的淘汰记录。**教训：以后再改动"哪些文件算垃圾/该被过滤"这类规则时，要先清空 `state/` 重新建立基线，否则会污染淘汰清单。**

## 垃圾文件过滤

过滤名单（大小写不敏感）：`.DS_Store`、`desktop.ini`、`Thumbs.db`。这些是文件系统自动生成的元数据文件，不是真实内容，三边清单里都有混入。发现是在检查 `4tb_pending.txt` 抽样结果时人工找出来的，不是一开始就想到的——**未来如果又发现新的垃圾文件模式，直接加进 `JUNK_FILENAMES` 集合，但要记得清空 state/ 重跑基线**。

## 输出编码（CSV 乱码问题的修复）

Excel/Numbers 打开 `summary.csv` / `suspected_renames.csv` 时中文乱码，原因是这两个软件对不带 BOM 的 UTF-8 CSV 会按系统默认编码猜测。修复：这两个 CSV 用 `encoding="utf-8-sig"` 写入（加 UTF-8 BOM）。

**`.txt` 路径清单没有加 BOM**，是刻意的：这些文件的用途是直接喂给复制脚本（比如 `while read -r path; do cp "$path" ...`），如果加了 BOM，第一行路径开头会多出不可见字符，可能导致脚本处理第一条记录时找不到文件。`state/` 下的内部 CSV（快照、淘汰清单）也没加 BOM，因为不是给用户在 Excel 里看的交付物。

## 技术选型理由

纯 Python 标准库（`csv`/`glob`/`re`/`collections`），没引入 `pandas` 等三方库。数据量级只有一两万行，标准库字典/集合操作足够快，没有必要增加依赖负担。子项目按项目规范建了独立 `venv/`（虽然目前没有任何第三方依赖）。

## 目录结构

```
mhd-local-nas-sync/
  gap_analysis.py          # 主脚本，跑一次出一份报告
  venv/                     # 子项目专属虚拟环境
  inputs/
    macbook/*.txt
    NAS-YuData/*.txt
    NoChange/4TB-HD/*.txt   # 只读源，脚本不会碰
  state/                    # 持久化，跨运行累积，不要手动删除（除非确认要重建基线）
    macbook_snapshot.csv
    rejected_ledger.csv
  outputs/
    YYYY-MM-DD-gap-analysis/
      4tb_pending.txt
      macbook_pending_upload.txt
      already_backed_up.txt
      suspected_renames.csv
      summary.csv
```

## 后续可能的改进方向（未实现，仅记录想法）

- **疑似改名清单加相似度打分**：目前同 size 就全部列成候选对，如果未来候选对数量变多（比如同 size 但完全无关的两个文件），可以用文件名/路径相似度排序，减少人工核对量。
- **淘汰清单的纠错入口**：目前误判淘汰后只能手动改 CSV，可以加一个命令行参数把某条记录从 ledger 里撤销。
- **内容哈希校验**：当前完全依赖"size + 文件名"判断同一文件，理论上存在同 size 同名但内容不同的极端情况（没在实测数据中遇到）。如果以后需要更高置信度，可以在复制阶段顺便算 md5/sha1，逐步替换 size 匹配。
- **通用文件名的噪音**：`images.jpg`、`images (1).jpg` 这类高频重名文件，单靠"size+文件名"匹配容易误判/漏判，目前没有特殊处理，抽样中已经看到这类文件出现在 `4tb_pending.txt` 里，值得留意。
