# Processing rules for personal text/image archives

Reusable playbook, written after processing the data set `inputs/2008_10_17_sss.Report/`. Follow it for similar data sets. Sections 1–6 are the rules. Section 7 lists what the scripts do and do not automate yet.

## 1. Principles

1. **Originals are read-only.** Never modify, move or delete anything under `inputs/`.
2. **Look before deleting or overwriting outputs.** List the folder first. Overwrite only files that a script generated in the same run. Never `rm -rf` an output folder. If a superseded output remains (for example a txt whose page became an HTML report), list it and ask.
3. **Environment.** Activate `venv` before running Python. Scripts use only the standard library (no network, no BeautifulSoup/lxml). `.doc` reading uses macOS `textutil`.
4. **Do not print document bodies** when checking results (the content is explicit). Report counts and short context only.
5. **Report honestly:** counts before/after, what was skipped, what could not be resolved.

## 2. Outputs layout

```
outputs/
├── txt/                         cleaned text without images (single files and/or the merged file)
│   └── <merged>.txt             e.g. 2008-09-misc.txt (see section 5)
├── reports/<folder>/<rel>.html  reports: cleaned text + images (images linked, not embedded)
├── images/<folder>/             ONLY images referenced by a report (flat)
├── images.only/                 images NOT referenced by any report
│   ├── <folder>/                (e.g. crazy/, RussianChicken/, wet/)
│   └── <folder>/manifest.csv    (image-folder manifests, section 3.C)
├── <folder>_summary.csv         one row per source page
└── <folder>_images_manifest.csv one row per source file
```

Rules:
- **Reports link to `images/`** with relative paths (`../../images/<folder>/p001_x.jpg`). Keep `reports/` and `images/` side by side. Embedding as base64 is an option only when a single-file report is needed.
- **Routing test:** an image belongs in `images/` if and only if some report links to it. Everything else goes to `images.only/`.
- **Flat naming** (no per-page sub-folders): post images are `p<NNN>_<original name>` (NNN = page index in sorted order), unreferenced images are `x_<first 30 chars of own folder name>_<file name>`. Names must never collide.

## 3. Pipelines by input type

### A. Word `.doc`
1. **Check for images first.** A file has images if `textutil -convert html` has `<img>` **or** the text contains `INCLUDEPICTURE` (Word field for a picture linked by URL, not embedded; textutil gives 0 `<img>` for these, so the html test alone misses them). Count both.
2. **Text-only files** -> `outputs/txt/<stem>.txt` (`doc_to_txt.py`). It skips files with images and never overwrites unless `--overwrite`.
3. **Files with images** -> `outputs/reports/<stem>.html` (`doc_to_html.py`). Word keeps the picture data **inside** the `.doc` as the cached result of each `INCLUDEPICTURE` field, but textutil does not expose it. `carve_doc_images.py` carves JPEG/PNG/GIF from the binary (walks JPEG segments, skips nested EXIF thumbnails) in file order, which matches field order. If carved count == field count, images go to `outputs/images/<stem>/NNN.<ext>` (+ `manifest.csv` with the original URL) and the report links `../images/<stem>/NNN.<ext>`. If the counts differ, the report falls back to the remote URL (dead 2007-08 hosts, so images will not show). Never rely on the remote URLs.
4. Extract text: `textutil -convert txt -encoding UTF-8 -stdout`. Remove noise (section 4.1) and normalise (4.3).
5. Skip Word lock files (`~$*.doc`) in `inputs/`.

### B. Saved web pages (`<page>.htm` + `<page>_files/`)
Tool: `process_html_posts.py <source folder> -o outputs`.

- **Decoding:** use the charset declared in the page (`big5` → `big5hkscs`, `gbk`/`gb2312` → `gb18030`). Decoding everything as GBK produced mojibake on big5 pages.
- **Posts:** Discuz threads have one `<table id="pidNNN">` per post. The first is the primary post and the rest are replies. Body = element with class `postmessage`. Author = first `<cite>`.
- **Other layouts** (found by listing pages with no `pid` tables): Xici-style threads use one `<td class="doc_txt">` per post. Older Discuz: one `<div class="t_msgfont">` per post. bt-download pages: body is the first `<td bgcolor=#ffffee colspan=2>`. phpBB: `<span class="postbody">` per post, author = last `span.name`, date = last `發表於:` cell. PHPWind: `<div id="read_tpc|read_NNN" class="tpc_content">` per post. A photo-album page keeps its photos in `<div class="phototable212">` blocks. vBulletin: `<table id="postNNN">`, author = `a.bigusername`, body = first `td.alt1`. Plain pages: `<div id="content">` (author = first `p.author`). Qzone blog: `<div id="blogDetailDiv">`. crazys.net model pages: first `<td>` containing `<b>author</b> 於 … 發表`. **Not posts:** pages saved inside a `*_files` folder that are image-host error pages (DivShare, xs.to) stay `unsupported` on purpose; say so in the report. Add a small adapter in `get_posts` for each new layout. Do not silently skip pages.
- **Decision per page:**

| Page content | Output |
|---|---|
| Any image in the primary post or in a reply | HTML report with the primary post plus every reply that has images. The primary post is always included, even if only a reply has images. |
| No images anywhere | txt with title, author and primary-post text only |

- **What counts as an image:** `jpg/jpeg/png/bmp` whose file exists locally. Forum smilies are never saved and are ignored.
- **Finding the image file** (try in order): path as written → `<page stem>_files/<name>` → ASCII-only name match inside the page's own folder (for names whose non-ASCII part was decoded differently) → file-name match in sibling `*_files` folders (the saved folder may have been renamed or shortened). If several folders hold the name, accept it when all candidates are **byte-identical** (the same picture saved under a renamed folder); otherwise the image is unresolved and the page falls back to txt, so check `unresolved_img_refs` on txt pages.
- **Broken file names** (`L&amp`, no real extension): the `<img src>` is accepted when the file is found and its header sniffs as jpg/png/bmp. It is copied with the sniffed extension (`p035_L&amp.jpg`).
- **Avatars** (`class=avatar` ancestor) are never post images. An avatar file that no post uses goes to `images.only/`.
- **Images are copied, not moved**, into `images/<folder>/` with the `p<NNN>_` prefix. Only images of saved posts are copied.
- **Whitespace** is collapsed in text nodes (HTML semantics) before any regex is applied, because the watermark often has a newline inside it in the source.

### C. Folders of loose images (already extracted from zips, or folders without a page)
- Source: `<folder>/<page>_files/*.jpg` for saved pages that are not turned into reports (e.g. `crazy`, `RussianChicken`).
- Copy all `jpg/jpeg/png/gif/bmp` into `images.only/<folder>/` as `p<NN>_<original name>`. `NN` is the page index in sorted order. Different pages reuse names like `01.jpg`.
- Write `images.only/<folder>/manifest.csv` (`image,source`). Skip `Thumbs.db`.
- Tool: `collect_images.py`. If such a folder is later turned into reports, its images move to `images/<folder>/` (referenced) and the rest stay in `images.only/`.

## 4. Noise removal

### 4.1 Watermark and garbage in `.doc` text
- Watermark: `本帖来源\s*https?://www.maichun.org\s*买春堂版权所有`.
- Followed by a run of 1–2 character printable-ASCII tokens (`# h6 T4 u+ J6 S% c/ E7 U`), separated by space or NBSP. Each token must be followed by a separator, line break or end of text. The run stops at the first line break or non-ASCII character.
- Implementation: `clean_doc_noise.py` (regex `NOISE`). The separator must be a **single-character class**. An earlier version used `[  ]+` followed by `?`, which became a lazy quantifier and silently removed nothing.

- **Noise varies per file; do not assume the maichun watermark.** The 2008-09 `.doc` set had files with no watermark at all, only garbage. Scan each file before choosing rules. Variants found:
  1. Spaced garbage at line end (or whole line): `0 s5 j" r* \` y- E2`. Rule (`doc_to_txt.strip_tail`): tail of >=3 space/U+3000-separated 1-2 char ASCII tokens, with >=1 mixed alnum+punct token and >=3 garbage-like tokens (len 1, or not purely letters / purely digits). The first token may be glued to the preceding CJK char. `KJ BJ DL ML`, `16 -- 28`, `2008 08 13` stay.
  2. Spam phrase + garbage: `军团,招财进宝,华人性息网站第一`, also truncated or split by line breaks, and `ＭＣ军团（招財進寶）[关闭注册]`. Delete the phrase and the ASCII run after it (`[!-~ NBSP]*`, stops at line break or non-ASCII).
  3. `bbs.maichun.org` / maichun watermark + garbage run (same run rule).
  4. Compact garbage with no spaces at line end or as a whole line: `6r0M#p:|%]:r9U` (`doc_to_html.strip_compact`). Delete when preceded by non-ASCII / line start (optional space), length >=8, >=3 special chars, has a lowercase letter and an uppercase letter or digit, and no `[a-z]{3,}` word and not a URL. A leading 1-3 digit number before a letter (`100V2z...`) is kept; this may leave or lose one real digit, which cannot be decided. If the run is followed by a visible link text, keep the link.
  5. Field codes: `HYPERLINK "url" \t "_blank"` removed; the visible link text after it stays.
- Known leftover: a garbage token glued to ASCII text (`24H8 U6 j7...`) can leave one stray character.

### 4.2 Garbage in HTML pages
- In saved forum pages the garbage is plain text **hidden by CSS**. Drop elements with `font-size:0`, `display:none`, `visibility:hidden`, or a white font (`color:#fff`/`white`) whose text has no CJK characters. This removes the garbage reliably, with no pattern guessing.
- **Exception:** `font-size:0` does not hide an `<img>`. If a `font-size:0` wrapper contains pictures, keep the pictures and drop only the hidden text (`display:none` / `visibility:hidden` stay dropped completely). Without this a real post image was lost (`上海發廊雙飛燕`).
- Drop ads (`id` starting `ad_` or containing `overture`).
- Then run the watermark regex of 4.1 on each post's text as a second pass.
- Do not "clean" short ASCII sequences by pattern in HTML text. After step 1 the remaining hits (`KJ + ML 300`, `To do or not this is a question`, `2 , 5, 8`) are real content.

### 4.3 Character clean-up (text from `textutil`)
- U+2028 / U+2029 → newline. `\r\n` and `\r` → `\n`.
- NBSP → space. Collapse runs of spaces. Strip trailing spaces. Collapse 3+ blank lines to 1.
- Decode leftover numeric entities `&#NNNN;` into the real character.

### 4.4 Forum boilerplate (removed on request)
- Edit stamp: `\[\s*本帖最[后後]由[^\]\n]*?[于於][^\]\n]*?[编編][辑輯]\s*\]`.
- Reply-to-see notice: `本帖[隐隱]藏的[内內]容需要[回]?[复復]才可以[浏瀏][览覽]`. Only the notice is removed. Text before it on the same line stays.
- In HTML reports also remove the stray `<br>` runs left behind (3+ → 2, and any before `</section>`).

## 5. Merging text

- After cleaning, individual txt files can be appended into one file (done for this set: all `wet` txt files into `outputs/txt/2008-09-misc.txt`).
- Order = sorted file names. Each file keeps its own title line. Separate files with a blank line. If the target exists, **append** to it. Never overwrite.
- Do the merge only once per source set. A second run would duplicate content.
- After merging, the per-page summary must say where each txt page now lives (`txt/<merged>.txt (merged)`).

### 5.1 Merge by folder (done for `outputs/txt/maichun/<folder>/`, 2026-11-16)
- Each folder gets `<folder>/<folder>.txt` + `<folder>.manifest.csv` (`no, file, start_line, end_line, chars`) in the same folder.
- Order: the folder's own `*.txt` sorted by name, then each sub-folder recursively (sorted). Each file keeps its title line; blank line between files.
- The originals stay in place (delete only on the user's request). The script skips a folder whose target already exists, so a re-run cannot append twice.
- Check: every source file's text is found in the merged file, in order.

### 5.2 Loose `.txt` inputs
- Source `.txt` files may be GBK. Decode strictly with `gb18030` and write UTF-8; a byte copy shows as mojibake. Also normalise line endings (`\r\n`→`\n`), NBSP/U+3000 to spaces, trailing spaces, 3+ blank lines. Check for U+FFFD = 0.

## 6. Verification checklist (run before calling a data set done)

1. Every source page appears once in `<folder>_summary.csv`, and exactly one output exists for it. HTML pages have a report. Txt pages have their txt, or their title appears in the merged file.
2. No stray reports or txt files without a source page.
3. Every `<img>` link in every report resolves, and the report is well-formed (`<section>` tags balanced, ends with `</html>`).
4. **Referenced images:** the set of files in `images/` equals the set linked from reports. `images.only/` contains no linked file. No file is in both.
5. `<folder>_images_manifest.csv` lists every non-page source file once, every output path exists, and output size equals source size.
6. Image-folder manifests (`crazy`, `RussianChicken`): rows == files.
7. Noise scan over all txt and html: no `maichun` / `买春堂` / `本帖来源`, no U+2028/2029, NBSP, U+FFFD, private-use or control characters, no `&#NNN;`, no edit stamps or reply notices, no `INCLUDEPICTURE` / `HYPERLINK` / `招财进宝` / `关闭注册`. Review any "garbage-like" hits by hand.
8. Counts before and after are reported to the user.

## 7. Script status and known gaps

| Script | Does | Not yet |
|---|---|---|
| `clean_doc_noise.py` | `.doc` → cleaned txt/doc (4.1) | Writes a flat `.txt` + `.doc` in the output folder. Does not apply 4.3 or 4.4, extract images, or check for images. |
| `doc_to_txt.py` | Text-only `.doc` -> `outputs/txt` with 4.1 (variants 1), 4.3; detects images incl. `INCLUDEPICTURE`; no overwrite without `--overwrite` | Spam phrases and compact garbage are not applied (not needed for the 2 files it handled; use `doc_to_html.py` rules if they appear). |
| `doc_to_html.py` | `.doc` with linked pictures -> `outputs/reports/<stem>.html`, 4.1 variants 1-5, `INCLUDEPICTURE` -> `<img>` | Embedded pictures are carved from the binary; no separate `images.only` routing (every carved image is referenced). |
| `htmltree.py` | Lenient stdlib HTML tree and charset decoding | – |
| `process_html_posts.py` | Section 3.B, 4.2, 4.3 (partly), 4.4, `p<NNN>_` images, summary and images manifest, layouts: pid tables, `doc_txt`, `t_msgfont`, bt-download `td#ffffee`, phpBB `postbody`, PHPWind `read_*`, photo album; control chars (`\x1c` etc.) cleaned; `[image missing]` marker where an image file was not saved; unreferenced images go to `images.only/<folder>/x_…` | Does not merge txt (section 5). Writes `txt/<folder>/…` per page. `本帖最近评分记录` (rating logs) is kept. |
| `collect_images.py` | Section 3.C, writes to `images.only/<folder>/` (`--sub images` to change) | – |

Manual steps used for this data set, to be scripted later: 4.3 and 4.4 on the output txt, the txt merge, moving unreferenced images to `images.only/`, and adding the `output` column to the summary.

Usage:
```bash
cd history-files-merge
source venv/bin/activate
python clean_doc_noise.py "inputs/<folder>/<file>.doc" -o outputs/txt
python process_html_posts.py "inputs/<folder>/<source folder>" -o outputs
python collect_images.py "inputs/<folder>/<image folder>" -o outputs     # then move result under images.only/
```

## 8. Gotchas learned

- `Thumbs.db` (149 files) is a cache. Skip it.
- Some image files were saved with broken names (`&amp`, `&amp(1).1]`). Sniff the file header (`FF D8` jpg, `89 50 4E 47` png, `GIF`, `BM` bmp), then copy with the right extension.
- The saved `_files` folder name often differs from the page name (title truncated, `～` vs `∼`, mojibake). Never rely on the exact folder name.
- The same image can be linked from two saved copies of one thread, so `images/` may hold more files than the manifest has "used" rows.
- `textutil` is the only `.doc` reader available. LibreOffice, antiword and catdoc are not installed.
- Checking `file` on a `.doc` shows a garbled title (code page 936). Ignore it.

## 9. Reference run: `inputs/2008_10_17_sss.Report/`

| Item | Result |
|---|---|
| `2008-09-10.doc` | 38 watermark blocks removed, 9,422 → 7,219 chars, no images. Now in `outputs/txt/2008-09-misc.txt` (renamed by the user) |
| `彭城寻春系列.doc` | 400 blocks removed, 59,492 → 36,012 chars, no images, `outputs/txt/彭城寻春系列.txt` |
| `wet/` (181 pages) | 143 reports, 38 txt (merged into `2008-09-misc.txt`); 893 images in `images/wet/`; 57 in `images.only/wet/` |
| `crazy/`, `RussianChicken/` | 193 and 49 images in `images.only/`, with manifests |
| Boilerplate removed | 84 edit stamps, 59 reply notices |

## 10. Reference run: `inputs/{hk9394,mcjt,Peep,russian}` (2026-11-16)

| Folder | Type | Result |
|---|---|---|
| `hk9394/` | Report (first mistaken for image-only, then user decided it needs reports to keep title/author/date): phpBB threads, 35 pages | 35 html; 110 images in `images/hk9394/`; 76 in `images.only/hk9394/` (loose folders with no saved page: `史提芬周之2008常平跨年*`, `最近主板版面好冷…`) |
| `Peep/` | Report (first mistaken for image-only; the page has ~2,500 chars of post text, PHPWind layout) | 1 html, 49 images in `images/Peep/`, 1 unreferenced bmp in `images.only/Peep/` |
| `mcjt/` | Reports | 14 html + 10 txt; 136 images in `images/mcjt/`; 4 unreferenced in `images.only/mcjt/` |
| `russian/` | Reports | 15 html, 144 images in `images/russian/` |

Notes from this run:
- **Check the layout before calling a folder image-only.** "No `pid` tables" means unsupported layout, not "no text". `Peep` and `hk9394` were misclassified this way. Image-only is the exception: a folder is image-only only if the text truly has no title/author/post content. Inspect the page text and the post containers first.
- Each report shows `[image missing]` where the source page references an image that was not saved. A missing image inside a dropped reply (no saved images) gets no marker; it is only counted in `unresolved_img_refs` (`沈阳金谛的撩骚松骨法`, 1; the 亞洲-有碼 bt page, 4 markers; in `hk9394` 3 markers, other unresolved refs are in dropped replies).
- Checks run and passed: image order in each report equals source order (sizes compared), file sizes equal source, header sniff valid, `images/` == linked set, no noise or control characters.
- `本帖最近评分记录` (rating log blocks) are kept in 21 files; not defined as noise. A `maichun.org` URL in one post and `买春堂` in titles are real content.
- Superseded image-only outputs (old `p<NN>_` copies and `manifest.csv` in `images.only/hk9394` and `images.only/Peep`) were hash-checked against `images/` and the `x_` files, then deleted with the user's OK. `images.only/` now holds only unreferenced images (`hk9394` 76, `Peep` 1; `Peep_images_manifest.csv` and `hk9394_images_manifest.csv` are the manifests).
- Txt merge (section 5) was not done for this set (not requested).

## 11. Reference run: 19 loose `.doc` files in `inputs/` (2026-11-16)

| Item | Result |
|---|---|
| Text-only (2) | `宁德汽车站附近再战霞浦女` 28,973 -> 24,738 chars (169 garbage lines); `苏狼成都玩砂` 69,568 -> 68,184. In `outputs/txt/` |
| With linked pictures (17) | All have `INCLUDEPICTURE` (136 images total); the html `<img>` check had said 0, so they were first treated as text-only. Converted to `outputs/reports/*.html`; 136 embedded pictures carved to `outputs/images/<stem>/` (all decode, all 136 links resolve) |
| Noise | No maichun watermark block in any file. Spam phrases removed: 22/8/15/6/18 in the five files that had them; compact and spaced tail garbage in the rest |

Notes from this run:
- **Check the layout before calling a folder image-only.** "No `pid` tables" means unsupported layout, not "no text". `Peep` and `hk9394` were misclassified this way. Image-only is the exception: a folder is image-only only if the text truly has no title/author/post content. Inspect the page text and the post containers first.
- Each report shows `[image missing]` where the source page references an image that was not saved. A missing image inside a dropped reply (no saved images) gets no marker; it is only counted in `unresolved_img_refs` (`沈阳金谛的撩骚松骨法`, 1; the 亞洲-有碼 bt page, 4 markers; in `hk9394` 3 markers, other unresolved refs are in dropped replies).
- Checks run and passed: image order in each report equals source order (sizes compared), file sizes equal source, header sniff valid, `images/` == linked set, no noise or control characters.
- `本帖最近评分记录` (rating log blocks) are kept in 21 files; not defined as noise. A `maichun.org` URL in one post and `买春堂` in titles are real content.
- Superseded image-only outputs (old `p<NN>_` copies and `manifest.csv` in `images.only/hk9394` and `images.only/Peep`) were hash-checked against `images/` and the `x_` files, then deleted with the user's OK. `images.only/` now holds only unreferenced images (`hk9394` 76, `Peep` 1; `Peep_images_manifest.csv` and `hk9394_images_manifest.csv` are the manifests).
- Txt merge (section 5) was not done for this set (not requested).

## 11. Reference run: 19 loose `.doc` files in `inputs/` (2026-11-16)

| Item | Result |
|---|---|
| Text-only (2) | `宁德汽车站附近再战霞浦女` 28,973 -> 24,738 chars (169 garbage lines); `苏狼成都玩砂` 69,568 -> 68,184. In `outputs/txt/` |
| With linked pictures (17) | All have `INCLUDEPICTURE` (136 images total); the html `<img>` check had said 0, so they were first treated as text-only. Converted to `outputs/reports/*.html`; 136 embedded pictures carved to `outputs/images/<stem>/` (all decode, all 136 links resolve) |
| Noise | No maichun watermark block in any file. Spam phrases removed: 22/8/15/6/18 in the five files that had them; compact and spaced tail garbage in the rest |

Notes from this run:
- The user's instruction was "write txt if no image contained"; for files with images they chose HTML (or doc) with all noise removed. Chosen: HTML, because linked pictures do not survive a `.doc` round trip.
- First attempt wrote txt for all files and then moved the 17 image files out of `outputs/txt/` to a scratch folder; those were generated in the same run and not user results.
- First version linked the remote URLs and no image showed (hosts dead, and not reachable from here). The pictures were embedded in the `.doc` all along; always check the raw file for image signatures (`FFD8FF`, `89PNG`, `GIF8`) before concluding that images are links only.

## 12. Reference run: `inputs/{FZForum,maichun,Wet168}` (2026-11-16)

| Folder | Pages | Reports | Txt | Images in `images/` | `images.only/` |
|---|---|---|---|---|---|
| FZForum | 73 | 41 | 0 | 279 | 3 |
| maichun | 456 | 127 | 329 (+3 loose `.txt`) | 1,051 | 24 |
| Wet168 | 126 | 125 | 1 | 602 | 19 |

Notes from this run:
- 32 FZForum pages stay `unsupported`: image-host error pages (31 DivShare in `近期驗證十余位…_files/`, 1 xs.to `33333.htm`). Not content.
- New layout adapters (section 3.B): vBulletin, `div#content`, Qzone, crazys.net. First run without them left 6 maichun and 1 FZForum real pages unsupported.
- **Audit of `images.only/`** (user asked): per file check header is an image, no report links it, no hash duplicate in `images/`, and no source page references it outside `class=avatar`. The first audit found 4 files that were body images: identical copies in renamed folders (2), a broken-name file (1), a picture inside `font-size:0` (1). Fixes are in 3.B and 4.2; two pages changed txt → report, their superseded txt files were checked against the report and deleted, stale `images.only` copies were hash-checked and deleted (all were files from the same session).
- Stale-output rule applies after every re-run: script does not delete. Compare the file list before/after (`comm`), then clean only files the run itself produced and only after a hash/text check.
- Image-manifest paths are relative to `outputs/`. When auditing, HTML-unescape `src` (`&amp;`) before resolving.
- The user later reorganised `outputs/txt/maichun` into folders named in Chinese and asked for the merge in 5.1.
- Left as is: one corrupted private-use character `\ue302` already present in the source of `【天意阅】『☆№§巴蜀回春§№☆』我在砂舞的日子里之情洒樱花`. `买春堂` / `maichun` mentions in text and URLs are real content.
- Not done: rating-log blocks (`本帖最近评分记录`) were not checked in this set.


## 13. Reference run: `inputs/{fdz,macau,MCJT}` (2026-11-16)

| Folder | Pages | Reports | Txt | Images in `images/` | `images.only/` (before clean-up) |
|---|---|---|---|---|---|
| fdz | 203 | 203 | 0 | 1,072 | 60 (10 are now duplicates of linked images) |
| macau | 62 | 62 | 0 | 247 | 243 (162 now duplicates of linked images) |
| MCJT | 250 | 105 | 145 | 1,173 | 33 (21 duplicate by hash) |

New layout adapters / fixes (all in `process_html_posts.py`):
- Discuz poll threads: no `pid` id, body = `div.postmessage` (3 MCJT pages).
- tiexue (铁血) threads: one `td.txt4` per post (3 MCJT pages).
- Older Discuz `t_msgfont`: attachment pictures live in `div.t_attachlist` beside the message div, so they were missed (all macau pages looked text-only).
- Image folder saved without the `_files` suffix and with a shortened name (`Sun王朝食件大眼妹26號`): same-prefix sibling folder fallback.

Notes: the first run had 6 unsupported MCJT pages and 38+1 pages wrongly written as txt; the re-run turned them into reports. Superseded txt and `images.only` copies are NOT deleted by the script; list them and ask. Source-corrupted mojibake (private-use characters) in `魅力写手作品…泡良还在路上…` and one stray `本帖来源` fragment in `晋总阅…狂干家庭旅社…` left as is.

## 14. Decision log, 2026-11-16/17 (maichun merge, fdz/macau/MCJT, clean-ups)

| # | Decision | Reason |
|---|---|---|
| 1 | `inputs/maichun` merged per folder into `outputs/txt/maichun/<folder>.txt` + `<folder>.manifest.csv` (15 folders, 297 files), not written into `inputs/` | `inputs/` is read-only (section 1). The user said "root folder"; outputs root was chosen. All files were valid UTF-8, no GBK conversion needed. Later the user moved/cleaned `inputs/maichun` and `outputs/txt/maichun`; the merge is not repeated. |
| 2 | `fdz`, `macau`, `MCJT` processed with `process_html_posts.py` (section 3.B) | Same pipeline as earlier saved-page sets. |
| 3 | Six MCJT pages first came out `unsupported`; adapters added (Discuz poll threads `div.postmessage`, tiexue `td.txt4`) instead of leaving them | Rule: never silently skip pages; "no pid tables" means unsupported layout, not no text. |
| 4 | Macau attachment pictures (`div.t_attachlist`, beside the message div) are now rendered | All 62 macau pages looked text-only; the pictures were in the attachment list. 38 pages turned txt -> report. |
| 5 | Sibling image folder without `_files` suffix and with a shortened name is matched by a 6-char prefix | `Sun王朝食件大眼妹26號` images were saved in such a folder; 10 refs were unresolved. |
| 6 | gif is still not a post image; 1 body gif in `常平花街介紹` stays in `images.only` | Section 3.B counts only jpg/jpeg/png/bmp (gifs are mostly smilies). User can change this rule. |
| 7 | Avatars, tiexue user-info thumbnails (`area2_hy_2`), related-thread thumbnails (`bbs_huliantd`), ads and signatures stay in `images.only` | They are not post content. Audit traced each image to its source page. |
| 8 | 193 stale `images.only` files and 39 stale txt files deleted, plus `images.only/.DS_Store` (user approved) | The re-run does not delete. Images: hash-identical to images now linked from reports. Txt: post body (header and `[image missing]` markers excluded) found in the report text. First check said 0/39 because it counted the `作者:` header and CSS text; fixed before deleting. |
| 9 | Left as is: source mojibake in `魅力写手作品…泡良还在路上…` (35 images never saved, still txt), one stray `本帖来源` in `狂干家庭旅社…`, `买春堂`/`maichun` mentions | Source defects or real content, not noise by the rules. |
| 10 | `/Users/hany/Downloads/images-only.done/crazy`: 3 exact duplicates deleted from 81 jpeg (78 left) | Matched by SHA-256 (byte-identical); first name kept per group. Only identical files are caught, not resized copies. |

Final counts: fdz 203 reports / 1,072 images; macau 62 / 247; MCJT 105 reports + 145 txt / 1,173 images; `images.only` 143 (fdz 50, macau 81, MCJT 12), all unreferenced.

## 15. Reference run: `inputs/{come2meAsia,RedArmyCollectionComplete,Report3,Report5,ReportKaixin,Reports,ReportsHK9394}` (2026-11-18)

| Folder | Pages | Reports | Txt | Unsupported |
|---|---|---|---|---|
| come2meAsia | 53 | 53 | 0 | 0 |
| RedArmyCollectionComplete | 36 | 32 | 4 | 0 |
| Report3 | 100 | 32 | 67 | 1 (empty stub) |
| Report5 | 176 | 29 | 144 | 3 (empty stubs) |
| ReportKaixin | 101 | 58 | 43 | 0 |
| Reports | 137 | 34 | 102 | 1 (frameset only) |
| ReportsHK9394 | 121 | 114 | 7 | 0 |
| `Reports/*.doc` (4) | | 2 (`2007_nO3_LIST`, `KoreaMap`) | 2 (`Japan_YJStory`, `koreaSummary`) | |

Totals: 354 reports, 369 txt, 3,381 images in `images/` (all linked, 0 broken, 0 orphans), 306 in `images.only/` (none linked).

- New adapters in `get_posts`: DCForum (myredbook), PHPWind `div.tpc_content` without id (yhsn.net), Dvbbs `div#textstyle_N`, mop.com `div.show_txt`, dtiblog `div.body`, crazys.net long form (`<i>於 … 發表|回應</i>`). `x-gbk` charset mapped to gb18030.
- `tidy()` now removes the forum spam phrase (`军团,招财进宝,华人信息网站第一` + garbage run) and the page title is cleaned the same way.
- `KoreaMap.doc` has 7 PNGs but no INCLUDEPICTURE field: `doc_to_txt` and the `<img>` test both miss it; `carve()` finds it. Pictures were placed after paragraph k (position is a guess).
- The first run happened before the adapters existed; 535 `images.only` files it wrote became linked images. They were hash-checked and moved (not deleted) out of `outputs/`. Always run into a scratch folder and compare the file lists before cleaning (section 12 stale rule).
- Left as is: private-use characters in the source of `【元鼎+】德阳！200块钱…`, one stray `本帖来源` in `【麦田+】…如意里发廊…`, nicknames in the QQ blacklist page, `maichun`/`买春堂` in URLs and text.
