# Processing logic: zips → reports / images-only / txt-only → de-duplicated, topic-routed library

Mid-point consolidation (2026-11-27). This is the file to follow for new batches. It condenses three older docs, now in `history_backup/` (look there for evidence, counts and per-run detail; section numbers below like "H§63" mean `history_backup/PROCESSING_RULES.md` section 63):

| Old doc | Covers |
|---|---|
| `history_backup/DOC_PROCESSING_RULES.md` | first `.doc` / saved-page noise rules |
| `history_backup/PROCESSING_RULES.md` (H§1-64) | everything done 2026-11-16 → 25, run by run |
| `history_backup/Reports.series_PROCESSING.md` | txt library (`locations/`, `series/`), report-root invariants (R§1-12) |

## 0. Ground rules (apply to every step)

1. **Originals are read-only.** `inputs/` is never modified. Zips are extracted into a fresh scratch folder (one empty dir per zip), never into the data folder.
2. **Venv first.** Activate `venv`, then run Python. Standard library only (no network). Project scripts that import siblings run from the project folder **without** `-I`; throw-away scripts that read untrusted data run with `python3 -I`, with paths passed as arguments.
3. **String comparison** (project rule): lowercase + strip whitespace before comparing (titles, names, text signatures, keywords).
4. **Numbers** (project rule): report all computed values (ratios, shares, sizes, percentages) rounded to 2 decimals.
5. **Look before delete/overwrite.** List the target first. Overwrite only files this run generated. Never `rm -rf` an output folder. Duplicates go to a **quarantine** (same relative paths + `removed_to_kept.tsv`); delete the quarantine only on the user's word after a byte/text check.
6. **Dry run by default, `--go` to act.** Back up every CSV/page you rewrite. After `--go`, inspect one written page and one CSV row (H§63.3 pitfall).
7. **Never print document bodies** (explicit content). Counts, titles and short context only.
8. **Re-list the real state at the start of every step.** The user moves/renames/deletes between turns (`txt/`, `images.only/`, whole roots).
9. **Report honestly:** counts before/after, what was skipped, what could not be resolved.

## 1. Pipeline at a glance

```
(1) inventory zips ──► (2) extract ──► (3) classify content ──► (4) clean + convert + route ──► (5) per-bucket de-dup / blank removal ──► (6) merge + topic routing ──► (7) audit
```

Three buckets are produced at step 4 and each gets its own step-5/6 treatment:

| Bucket | Content | Final form |
|---|---|---|
| **reports** | html pages **with images embedded/linked** (+ their images) | flat `reports_merged/<set>/` + `images/`, CSVs; then routed by topic/location into roots |
| **images-only** | images with no report | one flat folder `<first folder>__<name>`, manifest with SHA-256 |
| **txt-only** | all text: pages without images (html → txt), loose txt, doc/docx/pdf text | one `txt_merged.txt` + manifest; then split into topic files |

## 2. Step 1 - Inventory the zips

1. List `inputs/`; process only what exists, and name any requested folder that is missing.
2. **md5 every zip first.** Byte-identical zips under different names are processed once (H§63.5-1: 3 of 22 were copies).
3. Peek into each zip (names only) and tag the case:

| Case | Zip content | Route |
|---|---|---|
| **I** reports | saved pages `.htm/.html` + `_files/` (images) | §4 saved-page pipeline → reports (+ txt for pages without images) |
| **II** images only | jpg/png/gif/bmp, no pages | §4.3 → images-only |
| **III** text | `.doc/.docx/.pdf/.txt` and/or html **without image links** | §4.4 → txt-only |
| **IV** mixed | any combination of I-III (and junk: js/css/php, `Thumbs.db`, `.exe`, `.wav`) | split by **file**, not by zip: apply I, II, III to each file group |

4. Pilot **one** zip per kind before the batch (H§41-1: wrong layout adapters gave 0 reports on the first zip). Fix adapters on the pilot, then batch.

## 3. Step 2 - Unzip

- Use Python `zipfile` (not `unzip`): if flag bit 0x800 is not set decode names `cp437 → gbk` (fallback `big5hkscs`); replace `\` with `/`; names ending `/` are directories; guard against path traversal. Tool: `session_tools_2026.11.19/extract_zip.py`.
- One empty scratch dir per zip. Keep extractions until the audit is done (they are needed for the page-coverage check, §10-7).
- Nested zips: extract the inner zip into its own new dir, then treat as another zip.

## 4. Step 3-4 - Classify, clean, convert, route

### 4.1 Classify every extracted file

| File | Test | Goes to |
|---|---|---|
| `.htm/.html` (suffix **case-insensitive**) with ≥1 resolvable local `jpg/jpeg/png/bmp` | image exists on disk | **reports** |
| `.htm/.html` with no images (or images never saved) | falls back to txt; check `unresolved_img_refs` | **txt-only** |
| `.htm/.html` inside a `*_files/` folder | image-host error pages, `cnad.htm`, `mix.htm`, `stat.htm` | `unsupported` on purpose (not missing) |
| `.doc` | `textutil -convert html` has `<img>` **or** text has `INCLUDEPICTURE` | with pictures → report (`doc_to_html.py`, carved images); else txt-only |
| `.docx/.rtf` | `textutil` | txt-only (images inside → see 4.5) |
| `.pdf` | no `pdftotext` on this machine | txt-only only if extractable; otherwise hash-only, listed (gap, §11) |
| `.txt` | strict decode: BOM `FF FE` → UTF-16, else UTF-8, else `gb18030` | txt-only |
| `jpg/jpeg/png/bmp/gif` not referenced by a page | header sniff | **images-only** |
| `Thumbs.db`, `.DS_Store`, `~$*.doc`, `.js/.css/.php` page assets | – | skipped (listed) |

Header-sniff every image (`FF D8 FF` jpg, `89 50 4E 47` png, `GIF8`, `BM`). Files that are really HTML/XML error pages or 0 bytes are **fake images**: quarantine them, list in `not_images.tsv`, never count them as images (H§30). Wrong extension → rename to the sniffed one and repoint links/CSVs (`ext_fix` logic, H§59.11).

### 4.2 Saved web pages → reports (`process_html_posts.py <folder> -o outputs/<zip>`)

- **Decode** with the declared charset (`big5`→`big5hkscs`, `gbk/gb2312`→`gb18030`); pages declared latin-1 but saved as Big5 are re-decoded when >20 CJK chars and <2 % replacement chars.
- **Posts:** adapters per forum layout (Discuz `pid` tables, `doc_txt`, `t_msgfont`, phpBB, PHPWind, vBulletin, LB5000, Tieba, Tianya, plain article ≥1,500 CJK, …; full list H§3.B, H§39, H§41). Add a small last-resort adapter for each new layout; never silently skip pages.
- **Decision per page:** any image in the primary post or a reply → HTML report (primary post always included, plus replies with images); no images → txt (title, author, primary post).
- **Images:** copied (not moved) as `p<NNN>_<name>`; avatars are never post images; broken names (`L&amp`) are accepted by header sniff; forum smilies are ignored (a broken-link count for UI gifs on raw saved pages is normal, H§60.3).
- **Layout A per zip:** `reports/<folder>/…html`, `images/<folder>/p<NNN>_…`, `images.only/<folder>/` (unreferenced), `txt/<folder>/…`, `<folder>_summary.csv` (one row per source page, with `output`), `<folder>_images_manifest.csv` (one row per source file).
- Then: `add_summary_output.py` (adds `output` column) → `fix_manifest_gaps.py --go` (rows for `p<NNN>_` copies used by two pages; skip image-only roots).
- Batch scripts: `session_tools_2026.11.23/batch_extract_process.sh`, `session_tools_2026.11.24/batch_141.sh` (extract + process + add_summary_output, skip identical zips).

### 4.3 Images-only (case II and unreferenced images)

- Source: image-only zips, `_files` folders of pages that became txt, `images.only/`.
- Copy to `images-only/<folder>/` as `p<NN>_<name>` (`collect_images.py`) or keep the zip's own names; `manifest.csv` maps new name → source path. Skip `Thumbs.db`.
- Fake images quarantined (4.1). Carving from `.doc`: `carve_doc_images.py` (only when carved count == `INCLUDEPICTURE` count; else do not store the report, ask).

### 4.4 Text → txt-only (case III and pages without images)

1. **Extract**: `textutil -convert txt -encoding UTF-8` for doc/docx/rtf; strict decode for loose txt; page txt from 4.2.
2. **Normalize**: NFC; BOM off; U+2028/2029 and `\r\n` → `\n`; NBSP/U+3000 → space; `&#N;` → character; remove control, zero-width/bidi, U+FFFD and private-use characters; trailing spaces stripped; 3+ blank lines → 1.
3. **Noise removal** (order matters; always scan first, noise varies per file):
   1. Watermark `本帖来源\s*https?://www.maichun.org\s*买春堂版权所有` + the garbage run after it (tokens of 1-2 printable ASCII chars separated by space/NBSP; run stops at line break or non-ASCII). The separator must be a **single-character class** (lazy-quantifier bug, H§4.1).
   2. Spam phrases: `军团,招财进宝,华人性息网站第一`, `ＭＣ军团（招財進寶）[关闭注册]`, board footer in titles (`- …春色…关闭注册`).
   3. Garbage tails/heads: `doc_to_txt.strip_tail`, `clean_loose_txt.strip_edges`, compact garbage (`doc_to_html.strip_compact`), field codes (`HYPERLINK "url" …`, `INCLUDEPICTURE`). Do **not** use `BEFORE/AFTER` of `clean_loose_txt.py` on merged text (eats real `www.maichun.org` URLs).
   4. Forum boilerplate: edit stamps with and without brackets (+ trailing garbage run, may contain `&amp; &quot; &#x27;`; do not eat `<`), reply-to-see notices (simplified, traditional, Big5-garbled forms, `需要积分高于 N 才可浏览`, bare `本帖隐藏的内容`), `[image missing]` and bare `[img]`/`[/img]`, placeholder `以下内容需要回复才能看到` (only on the user's word).
   5. Footers on titles/file names: peel loop (`…买春堂`, `★军密档案★…Powered by Discuz!`, spaced board names).
   - **Keep**: `KJ ML`, `16 -- 28`, ratings, list numbering `1.`, `www.maichun.org` inside real URLs, `[youtube]`-type brackets. Never apply "1-2 char line" pass 2 blindly (dry-run, list distinct lines, never remove `\d{1,2}[.、)）]`; only for roots with hundreds of garbage lines).
4. **Hidden-text rule for HTML sources** (the reliable one): drop elements with `font-size:0` (keep images inside), `display:none`, `visibility:hidden`, white font without CJK, and ads (`id` starts `ad_` / contains `overture`). Do not pattern-clean short ASCII afterwards.
5. **Safety checks per cleaning pass:** removed CJK ⊆ CJK of the removed stamp/notice matches (multiset); no removed fragment contains a ≥3-letter word, ≥4-digit number or CJK; kept story's CJK is an in-order subset of its source (loss <0.5 % total, no story >20 %).
6. Empty-after-cleaning check **runs after** placeholder removal (some stories only become empty then).

### 4.5 HTML simplification and report clean-up

- Reports are single-column `<section>` posts; images linked relatively (never remote, never percent-encoded: write `html.escape(name, quote=True)`).
- Clean only **text nodes** (`re.split(r'(<[^>]*>)')`, `html.unescape` → clean → `html.escape`); collapse 3+ `<br>` to 2; drop `<br>` runs before `</section>`.
- Strip footers from file name, `<title>`, `<h1>` together; check 0 name clashes (NFC, lower case, no whitespace); name ≤240 bytes.
- Numeric-named reports: rename to the first text line of the primary post, then fix `<title>`/`<h1>` (H§59.10-12).
- Embedded `.docx` pictures (6,050 in `data.frozen` docx) are not extracted by the pipeline yet (gap, §11).

## 5. Step 5 - De-duplication and blank removal, per bucket

Run **noise cleaning first, then dedupe** (cleaning exposes more duplicates), and **re-run dedupe after any text-changing pass**.

### 5.1 reports

Order: fix-fake → exact → same-images/≤20 chars → flagged near → merge identical images → chain fix → audit.

| Layer | Test | Action |
|---|---|---|
| **Blank** | no text characters AND no images | delete (a title+pictures page is kept, H§63.4) |
| **Exact** | md5 of normalized visible text (no `<head>`/`<h1>`, lower case, whitespace-free) + tuple of SHA-256 of images in order | keep most unique images → longest name → folder priority → path; quarantine rest |
| **Same images, tiny text diff** | same image sequence, text subset/≤20 chars each side, ≥0.95 similar | delete, keep longest text (H§40.4) |
| **Subset** | one page's image set ⊂ the other's, every extra picture of the keeper ≥5 KB, text share ≥0.90 | delete the subset page (H§63.6) |
| **Near (flag only)** | ≥300 chars, Jaccard >0.70 **and** containment >0.80 | write `<set>_flagged_duplicates.csv`; classify by hand: no common image = different posts (keep); thin copy with no image the other lacks = remove; mixed = keep both |
| **Same text, different image bytes** | – | **HELD**, never auto-delete. Compare size and a 16×16 downscale difference (0.4-0.8 same picture, 44+ different photo); keep larger JPEG under the kept name only on the user's word |

Hard rules: before removing a report check that every image used only by it has a byte-identical copy in the kept one (else restore, H§31-3). Thumbnails (≤150 px or <8 KB) do not count as "image the other lacks". After sequential deletes run `fix_chains_and_counts.py` (A→B→C chains; `images_copied` = distinct images per page). Then `merge_identical_images.py` (SHA-256, keep shortest path, repoint links + CSV, delete verified copies; `images.only` copies of linked images deleted).

Cross-set comparison (new zip vs library): signature = md5(normalized text) + image SHA-256 tuple against `data.done/**/reports_merged` and `html/**`; exact match → delete the new copy + images no remaining page uses; unique → keep (H§62, `report_vs_library.py` / `apply_library_dups.py`).

### 5.2 images-only

1. Read-only scan (`img_scan.py`): SHA-256 groups, header sniff, name clashes.
2. A **set** is a folder of images. Never strip single pictures out of a set that has unique pictures; remove whole folders whose hash set is contained in a kept folder, then extra copies inside one folder (H§37), **or** choose the flat merge (preferred since H§47).
3. **Flat merge** (`img_merge.py [src] [dest] [--go]`, dry run by default): one file per SHA-256 named `<first folder>__<original name>`; assert 0 clashes (case/NFC) and names <255 bytes; verify SHA-256 of each copy; `images_merged.manifest.csv` (`no,file,sha256,bytes,copies_merged,original_paths`, BOM, LF); repoint every referencing CSV row; fakes out to `not_images.tsv`.
4. Against the existing library: SHA-256 index of `images-only.done`; delete a file only after `filecmp.cmp(shallow=False)` (H§62.7).
5. **Resized / re-saved copies (SHA-256 cannot see them): `img_near.py <root> [<root> ...]`, read-only.** `sips` makes a 16×16 thumbnail (pyramid 128→32→16; a single big jump aliases), stdlib parses the BMP; dHash + LSH bands find candidates, then a pair must pass: aspect ratio ±8 %, Hamming ≤18/240, mean abs difference ≤4.00, worst 4×4 block ≤6.80. Groups are cut greedily around the keeper (most pixels, then bytes) and every candidate must match the **keeper directly** (no A~B~C chains). Output `near_images.tsv`: `relation` (`same-size-resave` | `resized`) and `confidence` (`high` = mad ≤2, Hamming ≤8, block ≤3; else `review`). Thumbnails are cached by SHA-256 (`near_cache.json`), so a re-run only handles new files (4,245 images in ~44 s).
   - Calibration (real library pictures): 15 of 15 synthetic half-size / JPEG-q25 / PNG variants found, 0 false hits among the unrelated pictures; true copies max Hamming 17, block 6.55. On `mc_2026.11.19/images`: 21 groups, 26 candidates (12 high, 14 review).
   - **Limit:** consecutive frames of one video (same room, timestamps a few seconds apart) look alike: at looser thresholds they were false hits (Hamming 21+, block 7+); at the current thresholds a few can still land in `review`. **Only `high` is near-certain; look at `review` pairs by eye.**
   - The report is advice only. Before removing a candidate: check which reports link it (a candidate linked by a report that does not contain the keeper breaks that page), then use quarantine + `removed_to_kept.tsv` (§0.5), repoint links/CSVs, keep the larger picture under the kept name.
6. Re-check file count after any user move; do not restore/delete on a guess (H§64.3).

### 5.3 txt-only (`merge_txt_only.py <src> <out>`; writes a new folder, refuses to overwrite)

1. Clean (§4.4) → **drop empty** (no body line ≥5 chars after dropping title and `作者` line) → **exact duplicates** (md5 of lower-case, whitespace-free text; keep the longest file name) → **near duplicates** only when title core equal/contained (≥6 chars, punctuation, `b`, `新提醒`, `神州…`, `賽後報告` stripped) **and** `SequenceMatcher` ≥0.95 on the first 3,000 normalized chars; keep longer, tie → earlier. Never body-only ratio (139 false pairs).
2. Output: `txt_merged.txt` (UTF-8, LF, no BOM, one story per page: title line, `作者…` line 2, one blank line between stories, one trailing `\n`) + `txt_merged.manifest.csv` (`no,title,start_line,end_line,chars`; BOM, LF).
3. Verify: every segment equals the cleaned source; kept CJK in-order subset of source; `sources = kept + duplicates + empty`, 0 unaccounted.
4. **Manifest rebuild** from the merged file: a story starts at a non-blank line after a blank line (or file start) **and** directly followed by a `作者` line. A single blank line is *not* a boundary (H§64.2); verify against the known count first.
5. Compare against the library txt by cutting each target story by its manifest and testing exact equality of lower-case, whitespace-free text (`compare_txt_only.py`); delete verified duplicates via a verifying script (`delete_txt_only_dups.py`).

## 6. Step 6 - Merge with topic-specific routing

### 6.1 reports → roots by topic / location

Target library: `data.done/mc_2026.11.19/html/{merges,topics,locations}/<root>/{reports,images,<root>_summary.csv,<root>_images_manifest.csv}`; flat sets under `<set>/reports_merged/`.

1. **Flatten first** (all pages to `reports/`, `images/<root>/` flat; rewrite `<img src>` with `relpath`; own CSVs repointed).
2. **Clean** (noise, footers) → **dedupe** against `topics` + `locations` + inside the source (§5.1) → only then route.
3. **Routing priority** (first hit wins):
   1. **Series folder** in the source chain → topic root named after it (`大盗贼`, `学生妹`, `Great_Redarmy`, `十里洋场`, …).
   2. **Region folder** (`川渝精品收藏馆`, `江苏军区`, `东北军区藏经阁`, …) → canonical region root.
   3. **Keyword score** (region table): title ×6 + `【地址/地点/位置/店名】` field ×6 + body ×1. **Confident** = best ≥8 and ≥2× second, or board tag agrees (`[桂总阅]`→广西, `[云总阅]`→云南, `[川参]`→川渝, `[湘总阅]`→湖南 … tag only breaks ties). Move only `keyword` and `keyword+tag`.
   4. **Tier A/B for the rest:** A = target region's own word in the title; B = best ≥10 and ≥3× second. **Read every selected title before moving** (tiers are guesses). A region word followed by an origin noun (`四川巨乳妹`, `…妹/女/姐/少妇`) names the girl's origin, not the place.
   5. **Learned venue words** (3-4-grams in ≥5 confident stories with ≥90 % in one region): second pass only, never moved on their own.
   6. Otherwise stays in `merges` / `待定义`. **Do not guess** location: list evidence, ask.
4. **Region keyword hygiene:** remove ambiguous words (长安, 南海, 沙田, 白云, 南山, 天河, 朝阳区, 大兴, 通州, 昌平, 房山, 南京路, 川沙-as-川渝, 澳门路, 延安西路 = 上海, 韩庄 = 山东). Titles that only give the girl's origin say nothing about place. Overseas: Europe/Africa words → `欧非`, other → `海外`; 京津 split by place counts. New root when ≥3 reports, else stay.
5. **Mechanics:** copy reports with relative-path rewrite; name clash (NFC/lower/no-space) → ` (<source root>)`; same image name + same bytes reused, other bytes → `<source root>__<name>`; summary/manifest rows **move** to target CSVs (`note` column added if missing); an image leaves the source only when every report linking it moved; assert no image is shared by reports bound for different targets; source copies → quarantine, not deleted.
6. **Merging a source into an existing root:** compare against the target + the other roots (a report that already lives in a sibling or series root is a duplicate). Near copy replaces the target copy only if it has more images (back up first). A source that adds nothing → say so, change nothing (cmp CSVs against backups; restore if an empty `note` column appeared).
7. **Moving a root:** one `mv` per root (folder + its two CSVs). Same depth → no CSV rewrite; depth change → resolve every `output` against the old folder and rewrite relative to the new, back up first.
8. **Incremental rule:** route new stories with the combined run, **freeze old topics**, append only.

### 6.2 txt → topic files

Library: `txt/topics/mc_<topic>.txt` + `.manifest.csv` (`no,file,start_line,end_line,chars`) + `routing_report.csv` (`no,file,topic,basis,top_scores`); older `locations/` + `series/` library per R§1-8.

1. Same priority as 6.1 (series folder in chain incl. removed duplicates' folders → region folder → keyword score → relaxed pass → `待定义`).
2. **Weak evidence stays pending** (single-mention / first-mention placements were wrong ~1 in 5 and were moved back to `待定义`; keep candidate in `basis`, e.g. `mention-single(held:江浙)`).
3. **Series extraction:** ≥3 parts with same title/numbering (上中下, 之一/之二, 第N篇), or a cross-location serial by one author; 2-part series only on user request. Within a series keep the labelled/longer copy; `part` renumbered from 1.
4. **Append algorithm:** `old = read().rstrip('\n')`; new story starts at `old.count('\n') + 3`; write `'\n' + text + '\n'`; numbering continues; new region = new file. After any delete/move **rebuild** the manifest from the file (trim, one blank line between stories, recompute start/end/chars, renumber); never just delete rows.
5. **Duplicate tests vs library (dry run first):** exact = md5 of whitespace-free lower-case text; near = 8-gram share >0.6 (both ≥300 chars; use all 8-grams on both sides). Superset of a library story → replace in place. Sources deleted only after the user agrees and each text is found in the target.
6. Mojibake in names/first lines (GBK read as iso8859-5 / cp874): fix only confirmed cases with `.encode(...).decode('gbk')` after NFC.
7. Manifest checks (strict): columns/BOM/LF; `no` 1..N; first story at line 1; ranges valid; consecutive stories exactly one blank line apart; no story starts/ends on a blank line; `chars == len('\n'.join(lines[s-1:e]))`; every non-empty line covered; no duplicates across files; titles vs first line listed for hand review.

## 7. CSV contract (applies to every move/delete)

- `output` is relative to the CSV's own folder. Resolve → act → write back with `os.path.relpath`. Keep BOM, original EOL (process_html_posts CSVs are CRLF; `mcjt-total`/`gochina` are LF) and column order. `utf-8-sig` read, same write.
- Row whose file is gone: blank `output`; manifest `status` += ` [output file no longer in data.done]`; summary gets trailing `note` column with the reason. **Never delete rows** (exception: user-approved removal of fake images/manifest renumber).
- After any move/rename/dedupe scan **all** CSVs under `data.done`, not only the touched root: missing = 0. Repoint with the removed→kept log (follow chains).
- `images_copied` = distinct image files per page. Per-report `images/<stem>/manifest.csv` (Word-derived) is not an image.
- A tool that takes a **set name** must not pass it through `os.path.abspath` (H§63.3 pitfall).

## 8. Final layouts

```
data.done/<batch>/
  reports_merged/<set>_summary.csv, <set>_images_manifest.csv, <set>/<page>.html, <set>/images/<set>/<img>   (flat, layout B)
  txt_merged.txt + txt_merged.manifest.csv                                                                   (txt-only)
  images-only.merged/ + images_merged.manifest.csv                                                           (images-only)
data.done/mc_2026.11.19/{html/{merges,topics,locations}/<root>/…, images/, txt/topics/}                      (routed library)
```

Flat-layout naming: plain names; a clashing name gets `<zip>__` on every member (and `<zip>__<folder>__` if still clashing); strip the prefix afterwards only where unique (`strip_prefixes.py`).

## 9. Script map

| Stage | Script | Folder |
|---|---|---|
| extract | `extract_zip.py`, `batch_extract_process.sh`, `batch_141.sh` | `session_tools_2026.11.19/`, `.23`, `.24` |
| pages → reports/txt | `process_html_posts.py`, `htmltree.py`, `add_summary_output.py`, `fix_manifest_gaps.py` | project root |
| `.doc` | `doc_to_txt.py`, `doc_to_html.py`, `carve_doc_images.py`, `clean_doc_noise.py`, `doc_clean.py`, `doc_ole_text.py` | project root |
| loose txt / images | `clean_loose_txt.py`, `collect_images.py` | project root |
| noise passes | `clean_noise_pass.py`, `clean_pages_noise.py` | `session_tools_2026.11.24/` |
| report dedupe/audit | `merge_report_folders.py` (`audit near dedupe merge repoint fix-fake remove-source`), `scan_pages.py`, `dedupe_pages.py`, `dedupe_near_and_flag.py`, `dedupe_flagged_batches.py`, `fix_chains_and_counts.py`, `merge_identical_images.py` | root, `.24` |
| cross-set | `report_vs_library.py`, `apply_library_dups.py`, `flatten_set.py`, `to_reports_merged.py`, `move_into_library.py`, `strip_prefixes.py`, `csv_outputs_moved_away.py` | `.23`, `.24` |
| images | `dedupe_loose_images.py`, `img_scan.py`, `img_merge.py [src] [dest] [--go]`, `img_near.py` (resized/re-saved copies, read-only), `delete_images_only_dups.py` | root, `.25`, `.23` |
| txt | `merge_txt_pages.py`, `merge_txt_only.py`, `txt_build.py`, `route_topics.py`, `compare_txt_only.py`, `delete_txt_only_dups.py`, `audit_txt_library.py` | `.23`-`.25`, `.19`, root |
| routing / final audit | `route_topics.py` (region table lines 26-64), `final_audit.py`, `diag.py`, `repoint_to_topics.py` | `session_tools_2026.11.19/` |

**Paths are no longer hard-coded.** `hfm_config.py` (project root) gives every script `PROJ` (the folder it lives in), `DL` (`HFM_DOWNLOADS`, default `~/Downloads`), `DD` (`HFM_DATA_DONE`, default `<DL>/data.done`) and `SCRATCH` (`HFM_SCRATCH`, default `<system temp>/hfm_scratch`). Override per run: `HFM_DATA_DONE=/Volumes/x/data.done python3 -I session_tools_.../script.py …` (checked: a wrong value fails fast with `FileNotFoundError`; the default works under `-I` from any working directory). The `.sh` batch scripts `cd "$(dirname "$0")/.."`. New scripts: `sys.path.insert(0, <project>)` then `from hfm_config import PROJ, DD, DL, SCRATCH`. What still needs adjusting per run is **data names, not locations**: set names (`gochina`, `141`), batch folders (`mc_2026.11.19`, `GoChina.consolidated`), and scratch inputs an old session left behind (`contained_dirs.pkl`, `compare_*.tsv`, `plan.json`), which must be regenerated by re-running the analysis step. `route_topics.py` is cut by line number by `route_plan.py` / `route_tiers.py` (`src[25:64]`): **do not add or remove lines above line 66 of it.**

## 10. Verification checklist (after every step, report counts)

1. **Page coverage:** per root, html + txt + unsupported rows == number of `.htm/.html` files in the extracted zip; unsupported pages outside `_files/` = 0 (found 54 missed pages once, H§46-7).
2. Reports: every local `<img src>` resolves (unescape, NFC, skip `http:`/`data:`); 0 remote; well-formed (`</html>`, balanced `<section>`); 0 orphan images; 0 fake images; extension = header; 0 empty folders (`.DS_Store` ignored).
3. CSVs: all `output` exist; each html/image listed once; `images_copied` correct; 0 missing over **all** CSVs.
4. Noise scan over txt and html (visible text only): no watermark / `买春堂版权所有` / `www.maichun.org` garbage, spam, stamps, notices, `INCLUDEPICTURE`/`HYPERLINK`, NBSP, U+2028/9, U+FFFD, private-use, control, zero-width, `&#N;`, `[image missing]` (in txt), footers, garbage-token runs. Review hits by hand; false positives (`KJ ML`, ratings) stay.
5. Duplicates: 0 exact; flagged near pairs listed; held groups listed.
6. txt: manifest rules (§6.2-7); `sources = kept + duplicates + empty`; CJK subset test.
7. Images: SHA-256 of every file matches manifest; 0 name clashes; count equals manifest rows.
8. Count the files in a folder with `ls | grep -c html` (not `wc -l`, `.DS_Store`).

## 11. Known gaps / open items (carry forward)

- **PDF text** cannot be extracted here (no `pdftotext`/`antiword`/`catdoc`/LibreOffice): PDFs are compared by hash only. Decide on a tool before a case-III zip with many PDFs.
- **Embedded pictures of `.docx`/`.doc`** (other than `INCLUDEPICTURE`-carved) are not routed to images-only automatically.
- Resized/re-saved images: `img_near.py` is advisory (`review` rows need a look; video frames seconds apart can pass). Crops and rotated copies are not detected.
- Near-duplicate report pairs stay flagged (48 groups / 99 pages in 141; 165 pairs in gochina) - hand review.
- `141` txt not yet compared with `gochina txt_merged.txt` and the `mc` txt library; `141_images_manifest.csv` rows for moved images keep blank `output`.
- ~594 reports in `mcjt-total` and 546 stories in `待定义` need reading or a user decision per region.
- Source mojibake / `买春堂` in titles left as is unless asked.
- Quarantines and scratchpad backups are lost on reboot: save scripts in a `session_tools_<date>/` folder, not the scratchpad.

## 12. Working habits that held

Dry run → verify → `--go`; byte/hash check before every delete; one question at a time when the user must decide; stop and show evidence when a verification fails; commit the docs/scripts only on request; update this file (not the history backup) with anything new.
