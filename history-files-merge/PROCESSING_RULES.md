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
- **Other layouts** (found by listing pages with no `pid` tables): Xici-style threads use one `<td class="doc_txt">` per post. Older Discuz: one `<div class="t_msgfont">` per post. bt-download pages: body is the first `<td bgcolor=#ffffee colspan=2>`. phpBB: `<span class="postbody">` per post, author = last `span.name`, date = last `發表於:` cell. PHPWind: `<div id="read_tpc|read_NNN" class="tpc_content">` per post. A photo-album page keeps its photos in `<div class="phototable212">` blocks. vBulletin: `<table id="postNNN">`, author = `a.bigusername`, body = first `td.alt1`. Plain pages: `<div id="content">` (author = first `p.author`). Qzone blog: `<div id="blogDetailDiv">`. crazys.net model pages: first `<td>` containing `<b>author</b> 於 … 發表`. **Not posts:** pages saved inside a `*_files` folder that are image-host error pages (DivShare, xs.to) stay `unsupported` on purpose; say so in the report. Later additions (2026-11-18, all last-resort adapters placed before the photo-album fallback, so pages that already worked are unaffected): tiexue variant `div.main_body` per post (the `div.reply` wrapper is a copy, skipped); Blogger `div.post-body`; WordPress `div.content` inside `div#post-N` (东莞桑拿网); vBulletin without ids `table.posttable` → first `td.alt1` (红豆社区); `div.divBody` blogs (厚街桑拿坐台小姐内部照片). Empty pages (`<BODY></BODY>`, ~300 bytes), SEO ad pages (百度音乐掌门人 `div.info.zminfo`), search-result or navigation stubs, and a `stat.htm` inside a `_files` folder are not posts: leave them `unsupported` and list them. Add a small adapter in `get_posts` for each new layout. Do not silently skip pages.
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
| `clean_loose_txt.py` | Loose `.txt` (GBK or UTF-16) → UTF-8 with the noise rules of section 17; never overwrites | Rules are tuned to the maichun garbage forms seen so far; review the counts it prints. |

Run these scripts from the project folder **without** `python -I`: `process_html_posts.py` imports `clean_doc_noise`, `doc_to_txt` and `htmltree` from its own folder, and `-I` blocks that (`ModuleNotFoundError`). Keep `-I` for throw-away scripts that read untrusted input.

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

## 16. Reference runs, 2026-11-18: 2010_04 and 2010_07 sets

Output roots under `~/Downloads/data.done/` (one root per source batch, so folders with the same name, e.g. `mc` and `学生妹`, never collide):

```
2010_04.Reports/  and  2010_07.Reports/
  <folder>/<rel path>.html        reports; images linked as images/<folder>/p<NNN>_… (../ per sub-folder level)
  <folder>/images/<folder>/       images used by a report
  <folder>_summary.csv            one row per source page (+ output column, relative to the CSV folder)
  <folder>_images_manifest.csv    one row per image
  txt/<folder>/                   txt pages (2010_07 only; 2010_04 txt went to Reports.series-…/txt/tmp)
  images.only/<folder>/           unreferenced images
Reports.series-2026.11.17/
  html/<folder>/…                 same layout as above (for 老红军_2010_04, 沧桑的情人)
  txt/locations/  txt/series/     the txt library (sections 18-19)
  txt/tmp/<folder>/               staging for txt pages; if the name exists, use <folder>_2010_04, never merge into it
```

| Set | Folders | Pages → reports / txt / unsupported |
|---|---|---|
| 2010_04 (8 folders) | 胜地, 学生妹, —夜游, come2meAsia, hk9394, mc, mc2, society | 593 reports, 747 txt, 16 unsupported |
| 老红军, 沧桑的情人 | | 58 + 16 reports, 5 txt |
| 2010_07 | mc, mc-topvids, mc3, Society, yktm, 学生妹 | 133 reports, 86 txt, 0 unsupported |
| Places (2010_07) | 264 pages | 227 txt-type, 31 html, 6 unsupported |

Notes:
- **Folder named in the request vs. what exists:** `inputs/` changes between turns (the user moves folders). List it first, process what is there, and say which requested folders were missing. Folders not named (e.g. `Places` in one turn) are not processed.
- **Byte-identical folders:** `mc` and `mc 2` had 52 of 52 identical pages; process one and say so. Check with md5 of the page files before running.
- **Zips with Windows names:** `unzip` mangles GBK file names and creates `a\b` literal names. Extract with Python `zipfile`: decode names `cp437 → gbk` (fallback `big5hkscs`) when bit 0x800 is not set, replace `\` with `/`, and treat names ending in `/` as directories (they are not flagged `is_dir`). Extract each zip into its own scratch folder.
- **Pages whose images were never saved** (no `_files` folder, or one file) correctly fall back to txt. Check `unresolved_img_refs` on txt pages before calling it a bug.
- **Empty stubs:** ~300-byte pages with an empty `<BODY>` stay `unsupported`. 12 of 16 unsupported pages in the 2010_04 set were stubs.
- **`.doc` with pictures:** `doc_to_html` falls back to remote URLs when the carved count differs from the `INCLUDEPICTURE` count (洗浴.doc: 7 of 19). Do not store such a report; ask. `KoreaMap.doc` carves 7 PNGs byte-identical to the earlier run, so the earlier html can be reused with its image folder depth adjusted (`../images/…` when the report is one level down).
- **Duplicate html reports across sets:** compare normalized text (strip head, h1, tags, whitespace) plus the image-name sequence (without `p<NNN>_`). Exact → do not store. 23 of 31 Places html pages were exact copies.

## 17. Loose txt files and doc text: encoding and noise (`clean_loose_txt.py`)

- **Encoding:** BOM `FF FE` → UTF-16; else UTF-8; else GBK (`gb18030`). Of 7 loose files in `Places`/`胜地`: 4 GBK, 3 UTF-16. Normalize U+2028/2029, `\r\n`, NBSP and U+3000 to space; no U+FFFD allowed.
- **Noise forms found (all removed, then recount):**
  1. spam `ＭＣ军团（招財進寶）[关闭注册]` / `军团,招财进宝,华人[信性]息网站第一` + ASCII run;
  2. bare `www.maichun.org` followed by an ASCII garbage run (to line end or first non-ASCII);
  3. a garbage run of 1-2 char tokens glued **in front of** the URL;
  4. spaced tail garbage (`strip_tail` from `doc_to_txt.py`);
  5. garbage at the start of a line glued to the following Chinese text or followed by 2+ spaces (needs ≥3 tokens with a mixed alnum+punct token, or ≥6 tokens that all look like garbage);
  6. a 2-token tail like `。! j.` (needs a punct-only token and a mixed token);
  7. a ≥5-token tail where every token is garbage-like;
  8. a garbage run glued to list numbering (`{2.米兰…`: strip the run and one glued character, keep the number).
- **Do not remove** plain runs such as `ML KJ`, `16 -- 28`, table rows (`E 400元 90分钟 A  +B`). After cleaning, a scan for lines with ≥4 short ASCII tokens should show only real content.
- Garbage can also survive in txt written by `process_html_posts.py` (tail runs after Chinese text). After every run, scan txt and html lines with the same detectors and fix in place (26 txt lines and 4 html lines in the 2010_04 set; for html unescape the line first, re-escape `& < >`, skip lines that contain tags).
- Result for the three big `Places` files: `南京.txt` 30,311 → 22,365 chars, `杭州/简介.txt` 60,042 → 46,028, `南京/总结.txt` 9,877 → 8,008.
- Unrecoverable source mojibake (private-use characters, e.g. in `魅力写手作品…泡良还在路上…`) is left as is; report the count.

## 18. Merging txt into the library (`locations/`, `series/`), 2026-11-18

Order of work for any "merge X into Y" request:
1. **Dry run first, read-only.** Candidates, exact duplicates, near duplicates, new count. Report counts, not text. Wait for the user's choice when there is a real choice (dups, compilations, naming).
2. **Duplicate tests** (against all of `locations` + `series`, and against the other candidates):
   - exact: md5 of the text with all whitespace removed;
   - near: share of 8-grams found in one other story > 0.6 (both ≥ 300 chars). For near-identical text use all 8-grams on both sides; sampling at different offsets gave false "0.43" for identical files;
   - title-only pre-filters (first 12 chars) miss renamed copies; always run the body test too.
   - Skip duplicates; keep the longer version inside a batch. A near duplicate that is a **superset** of a library story (徐州 `总结`, +15% text, reordered) → replace that story in place and rebuild the manifest, not a second copy.
3. **Back up** the target txt and manifest to the scratchpad (`bak_*/`) before touching them.
4. **Append** (section 4 algorithm of this file): `old = rstrip('\n')`, new story starts at `old.count('\n') + 3`; story text = `strip('\n')` of the source; `file` = source file name with `/`→`／`; numbering continues. Empty target (user-created empty `广西.txt`): first story at line 1, create the manifest. New region → new `<region>.txt` + manifest.
5. **Verify** with the strict checklist of section 19. Report counts, backups and what was skipped.
6. **Delete sources only after the user says so**, and only after each source's whitespace-normalized text is found in the target (trimmed-garbage copies: compare after applying the same trimming). Save the deleted list to the scratchpad. Remove folders that become empty (remove subfolders first; `.DS_Store` does not count). Originals also remain in the zips.

Location routing (`mc-merged` → `locations/`):
- Folder names are the location when the source is organised by region (`Places/上海` → `上海.txt`; 杭州, 徐州, 苏州, 南京 → `江浙.txt`; 山东 sub-folders → `山东.txt`). Follow the user's folder decision even when the text hints otherwise (重庆江北…→ stays in 上海 if the user says so).
- For mixed sources score each story: keyword hits in the title (×6), `【…地址/地点/位置/店名…】` field (×6) and body (×1) against a region keyword table. Confident = best ≥ 8 and ≥ 2× second, or the board tag agrees with the best (`[桂总阅]`→广西, `[云总阅]`→云南, `[川参]`→川渝, `[湘总阅]`→湖南 …; the tag only breaks ties, rule 2.5 still holds). Everything else stays pending.
- Remove ambiguous words from the table: 长安, 南海, 沙田, 白云, 南山, 天河 (广东); 朝阳区, 大兴, 通州, 昌平, 房山 (京津). Known false positives: 延安西路 = 上海 (not 陕西), 南京路/高雄路 = 武汉 (not 江浙/台湾), 韩庄 = 山东 (微山), 江宁 = 南京, 东城/长安 hotel ads = 东莞.
- **Contested stories:** use the place named in the title (河口, 德宏→云南; 成都→川渝; 北京→京津; 武汉→湖北; 济南→山东; 西安→陕西; 澳门→港澳). Titles that only give the girl's origin (`广东妹`, `广西姊妹花`) say nothing about where it happened: hold or ask.
- **Venue/series evidence:** a story with no clue can be routed when its venue or series name appears almost only in one region file of the library (心雨舞厅 42× 川渝, 白天鹅 154× 川渝, `疯狂嫖娼记` earlier parts in 云南, 樟木头 in 广东).
- Non-China or unknown country → `其他海外.txt` (renamed from `非美海外.txt`; the rename touched `series/福建狼古巴行.manifest.csv`, `series/援交系列小T感受.manifest.csv`, `locations/错位报告.csv` source/column text, and this file). Country files that exist (`日本`, `韩国`, `美国`, `俄罗斯`) are used when the title names that country.
- New files created this session: `江西`, `港澳`, `甘肃`, and `待定义` (not a region: holds stories whose location could not be decided; the user chose the name `待定义`).
- Keep a `routing_report.csv` (no, file, region, scores, second region, board tag, basis, status, current number) next to the source, update it after every pass, and remove routed stories from the source only after verifying their text is in `locations` (section 5 rebuild: trim, reflow, renumber).
- Pass log for `mc-merged` (555 stories): 385 confident, 96 "probably right", 24 contested by title, 7 non-China/doubtful, 7 by venue/series evidence, 8 by reading, 4 by the user → 531 routed in total (385+96+24+7+7+8+4), 9 skipped duplicates deleted, 15 → `待定义` (531+9+15 = 555).

## 19. Strict check for `locations/` and `series/` manifests (run before calling the library done)

Per txt/manifest pair, all of these must hold:
- both files exist; manifest has a BOM, LF line endings and the columns `no,file,start_line,end_line,chars` (locations; one series file uses the same) or `part,title,source_file,source_start_line,source_end_line,start_line,end_line,chars` (series). A single-article series file gets a 1-row manifest with empty source columns.
- txt is UTF-8, LF only, ends with exactly one `\n`.
- `no/part` is 1..N; first story starts at line 1; each `end_line ≥ start_line`; the last story ends on the last line; consecutive stories are exactly one blank line apart.
- `chars == len('\n'.join(lines[start-1:end]))`.
- **No story starts or ends on a blank line.** A story's own trailing blank line plus the separator gives two blank lines and an off-by-one range. Fix by the section 5 rebuild: trim each story, reflow with one blank line, recompute `start/end/chars`, and assert that the whitespace-normalized text is unchanged. (93 stories in 9 files had this; they were pre-existing.)
- When normalizing a file's trailing newlines, re-check the last manifest row: if its `end_line` counted the removed blank line it now points past the end of the file.
- Every non-empty line is covered by some story; no U+FFFD, control characters, NBSP, `&#NNN;`, `INCLUDEPICTURE`, `HYPERLINK`, `本帖来源`, `买春堂版权所有`, spam phrase; garbage-tail scan finds nothing.
- No duplicate story across all files (md5 of whitespace-free text).
- Titles vs. first line: differences are listed for a manual look only (the compilations `总结`, `简介`, `睢宁` have non-title first lines on purpose).
- Final state of this session: 47 pairs (30 locations, 17 series), 1,350 stories, 0 issues, 0 duplicate groups.

HTML side of the final check: for each output root count html and images; resolve every local `<img src>` and other local links (unescape, ignore `#`/`?`, treat NFC/NFD names as equal); no remote links; every image under `images/` is linked by a report (0 orphans). `images.only` files are unreferenced on purpose and are reported separately. Results: `2010_04.Reports` 595 html / 4,619 images, `2010_07.Reports` 141 / 1,467, `Reports.series-2026.11.17/html` 148 / 2,712, all with 0 broken and 0 orphans.

## 20. CSV upkeep: blank and tag rows whose file is gone

When the user moves or deletes outputs by hand (or after a merge removes txt pages), every `output` must still point to a real file (relative to the CSV folder):
- re-point if the content lives elsewhere (txt pages merged into `locations` → `../Reports.series-…/txt/locations/<region>.txt`; use the routing report to find the region; blank rows whose duplicate was deleted);
- otherwise blank `output`; in `*_images_manifest.csv` append `[output file no longer in data.done]` to `status`; in `*_summary.csv`, which has no status column, add a trailing `note` column (empty elsewhere) with the same tag. Never delete rows, keep the BOM, the line endings and the existing column order;
- back up all CSVs first; re-scan afterwards (`missing = 0`). "Listed more than once" is fine for txt rows that point at one region file.
- After this session: `2010_04.Reports` 1,112 and `Reports.series-2026.11.17/html` 6 rows tagged; `2010_07.Reports` 24 rows tagged.

## 21. Habits that worked this session

- Report counts only; never print story text (section 1.4). Titles and short context are fine.
- One question at a time when the user must decide (duplicates, compilations, where a story belongs, file names). Do not guess locations: hold them and list them with the evidence.
- Every destructive step: list → verify content is elsewhere → save the list → delete → re-verify.
- After the user edits the tree between turns, re-list before acting (folders and files disappeared several times without being deleted by the assistant).
- Quote the user's typo'd names once, then rename when told (`带定义` → `待定义`) and fix every CSV that mentions the old name (`grep` over all CSVs).

## 22. Reference run: `inputs/mcu` (2026-11-18)

| Item | Result |
|---|---|
| Pages | 27 saved pages → 4 html reports, 23 txt, 22 images, 0 unsupported (`process_html_posts.py inputs/mcu -o outputs`) |
| Txt merge | 23 txt → `outputs/txt/mcu/mcu.txt` + `mcu.manifest.csv` (5.1 layout; sources deleted on request after a whitespace-normalized "found in merged file" check) |
| Move to the series library | `html/mcu/*.html`, `html/mcu/images/mcu/`, `html/mcu_summary.csv` (+ `output` column), `html/mcu_images_manifest.csv`; the merged txt lives in `txt/tmp/category/` |

- Reports written by the script link `../../images/<folder>/…`; in the library layout (`html/<folder>/x.html`, images in `html/<folder>/images/<folder>/`) the link is `images/<folder>/…`. Rewrite the links when moving, then re-run the link check.
- Summary `output` for txt pages that were merged: `../txt/tmp/category/<folder>.txt (merged)` (path relative to `html/`). Always re-list the target first: the user moved the merged txt between turns.

## 23. Merging one report folder into another (html + images + CSVs)

Used for `mc3`, `mc2`, `mc` → `mc`; `society` → `Society`; `Places` → `胜地`; `学生妹` → `学生妹`; `come2meAsia`, `hk9394`, `开心`, `mc` (HPLaptopBack). Steps:

1. **Dry run, read-only.** For every source report compute the normalized text (strip `<head>`, `<h1>`, tags, whitespace) and the image-name sequence without `p<NNN>_`:
   - exact = same text and same image sequence → skip;
   - near = 8-gram share > 0.6 → decide (below);
   - new → copy.
   Also count image-name clashes (same name, different bytes) and html-name clashes.
2. **Compare against the target only, plus the files already chosen for the target.** A first run printed "near" for pairs inside the *source* (the pool included just-added source files); matching against the target alone gave 1–11 %. When in doubt, print the best match's title.
3. **Near copies:** replace the target copy only when the incoming one has more images, and only after backing the old one up (images moved with it). Equal or fewer images → skip. Several versions of one thread inside the source: keep the one with the most images.
4. **Check sibling folders and the series folders before copying.** A merge into `mc` re-added `七十三` and `七十四`, which had been moved earlier into `上海狼在俄罗斯`; it was noticed only after the run and undone. Rule: a report that already lives in another folder of the library is a duplicate, not new.
5. **Copy, never move.** Reports are written with links rewritten (`images/<src>/` → `images/<target>/`); images are copied only when a kept report uses them; an existing image name must be byte-identical (assert). Trim forum footers from file name, `<title>` and `<h1>`: regex `\s+-\s+([☆╉]|[^\s-]*春色).*$`.
6. **CSVs:** add source rows whose `page` is not in the target (txt and unsupported rows too, keep their notes); html rows of skipped duplicates get a blank `output` and a note; add a trailing `note` column when the target has none; manifest rows only for copied images. `images_copied` counts unique files, so it can be lower than the number of `<img>` tags.
7. **Verify:** links, orphans, every `output` exists, every html in the summary once, every image in the manifest once.
8. **Delete the source only on request**, and only after: every report's text is in the target (overlap ≥ 0.9 when versions differ) and every image has a byte-identical copy. Save the CSVs and the file list to the scratchpad first; then remove folders, CSVs and the empty parent (`.DS_Store` does not count).
9. **When the source is a plain older copy** (`come2meAsia`, `hk9394` of HPLaptopBack: 100 % identical), say so and change nothing; it can still be offered for deletion.
10. **Naming clash with an existing folder** (`html/学生妹` already holds the merged content): do not create a second copy; ask or follow section 16's `<folder>_2010_xx` rule.
11. Whole-folder moves (`2010_04.Reports/*` → `2010_07.Reports`): check name clashes first. Relative paths in the CSVs stay valid because folder and CSVs move together.

## 24. Merging txt into `locations/` (more cases, 2026-11-18)

- **Target without a manifest and without story headers** (`category/学生妹.txt`): do not guess boundaries (only 2 of 51 titles occurred in it). With the user's choice: one **legacy row** covering the old lines, then one row per appended story.
- **Which candidates to append:** exact duplicates and near duplicates are skipped. State the metric: 8-gram share of the source found in the target (used to choose) and character coverage (a different, higher number). Showing both caused confusion; pick one for deletion decisions.
- **Side-by-side requests:** do not print bodies. Show source chars, matched target lines, chars missing from the target and 10–14 character hints. In every case the missing text was reply tails, rating lines or author notes, not different stories.
- **Delete in stages** when asked (the >95 %, then >90 %, then all). Before each stage list the files and save the list. The deleted tail text is gone afterwards; say so.
- **Routing a folder (`tmp/tmp`, 36 files):** 9 duplicates skipped, 1 compilation held, 26 routed (江浙 9, 山东 4, 陕西 3, 湖北 2, 河南, 川渝, 新疆 (new file), 河北, 待定义 4). Strip the board footer (` - 江苏春色 - -华东春色- - 皇家帝国花园【暂时关闭注册】`) from titles.
- **Compilation (`发廊.txt`):** a title line that follows a blank line and precedes `【验证时间】`/`【买春地址】` fields starts a story. Split into files, trim spam residue (`华人信息网站第一 发信到 …@… 索取最新地址`), check each against the library, route, delete the pieces only after text check.
- **Phone numbers in titles:** delete files whose title holds a complete mainland mobile number (`1[3-9]\d{9}`, also written with spaces). A truncated `13` is not a number.
- After routing run the strict checks of section 19 on the touched files only and compare spam-phrase counts before/after (old stories may legitimately still contain `关闭注册`).

## 25. Auditing and de-duplicating a report root (`2010_07.Reports`, 2026-11-18)

Checks per folder: `<img>` links resolve, orphans, well-formed html, non-image files, stray `.DS_Store`; per CSV: BOM, column count, `output` exists, no repeated `output` except txt rows pointing at one `locations` file, html in summary once, images in manifest once, summary `images_copied` vs unique images, manifest `status` of rows without `output` carries `[output file no longer in data.done]`.

De-duplication of exact duplicate reports across the root:
1. Group by normalized text + image sequence (section 23). Result: 82 groups / 83 extra copies, 56 of them between `—夜游` and `开心`.
2. Keep one per group: folder priority `mc > —夜游 > hk9394 > come2meAsia > mc-topvids > yktm > Society > 开心`; inside one folder keep the longest file name (the most complete title).
3. **Quarantine first** (outside `data.done`, same relative paths, plus a `removed → kept` TSV and a CSV backup), repoint the CSV rows to the kept copy, move images only when every report using them is removed, re-run the audit (0 groups, 0 broken, 0 orphans). Delete the quarantine only on the user's word, after a byte check of every image against its kept copy.
4. Images with the same bytes under different `p<NNN>_` names (216 groups left) are legitimate: each is linked by a different report. Do not remove them.
5. A folder whose reports were all duplicates (`开心`) ends up empty but its CSVs still have rows pointing elsewhere; ask before removing folder and CSVs.

## 26. Working habits added this session

- When the next step is determined by the rules and the data (exact duplicates, nothing new, a plain older copy), state the finding and the default and continue. The user twice rejected a multiple-choice question and answered with the next instruction instead; ask only when there is a real choice, and then once, briefly.
- A "move" that finds the target name already taken, or a "merge" with nothing new, is reported as such with counts; do not invent work.
- Always give the backup and deleted-list paths (scratchpad) after a destructive step.
- Scripts used this session were throw-away scratchpad scripts (`merge_*.py`, `dedupe_2010_07.py`). Candidate for a project script: one `merge_report_folders.py` implementing section 23 (dry run + `go`).

## 27. Auditing the finished report roots (2026-11-18)

Roots audited with the section 25 checks: `2008_10_17_sss.Report`, `2008_10_30_sss.Report`, `2008_10_30_sss.Report.Single`, `2009_02_03_Report`, `2009_04_23_ss+2009_05_15_Report`, `2010_07.Reports`, `Reports.series-2026.11.17/html`. Three layouts exist; use the matching checker:

| Layout | Used by | Reports | Images | CSVs |
|---|---|---|---|---|
| `reports/<folder>/…`, `images/<folder>/…` | the `20xx_xx_xx_*.Report` roots | link `../../images/<folder>/…` | flat per folder | `<folder>_summary.csv`, `<folder>_images_manifest.csv` at the root, `output` relative to the root |
| `<folder>/*.html`, `<folder>/images/<folder>/…` | `2010_07.Reports`, series `html/` | link `images/<folder>/…` | | CSVs next to the folders |
| `reports/<report>.html`, `images/<report>/NNN.ext` + `manifest.csv` (`image,original_url`) | `….Report.Single` | link `../images/<report>/NNN.ext` | one folder per report | per-report manifest only; no summary |

Findings worth remembering:
- A report can live in another folder than the CSV that lists it (`russian` report stored in `reports/mcjt`, listed in `russian_summary.csv`). Check "listed exactly once" over **all** CSVs of the root, not per folder.
- `images_copied` is the number of unique files, not of `<img>` tags (a repeated image gives a lower number).
- Manifest rows `copied` with an empty `output` must carry the tag `[output file no longer in data.done]`.
- `maichun` inside a forum URL in the post text is content, not noise.
- Rows of txt pages merged into `locations` share one `output`; that is not a duplicate. Do not write a remark such as ` (merged)` into `output`: use a `note` column and a plain path (`mcu_summary.csv` was fixed this way). The user moves `txt/` folders between turns (`txt/tmp/category` → `txt/category`): re-resolve the path before writing it.
- Report counts after every step: html, images, broken, orphans, CSV rows, missing outputs, exact-duplicate groups.

## 28. Near-duplicate test and de-duplication rules (corrections, 2026-11-18)

- **Near-duplicate test:** "8-gram share of the smaller page > 0.8" gives false hits when pages carry boilerplate (186 hits in `fdz`, mostly different posts that share ~1,200 characters of forum chrome; short pages match everything). Use pages with ≥ 300 characters and require **Jaccard > 0.7 and containment > 0.8**. Print titles, text lengths and image counts for each pair and review by hand. Never remove near-duplicates automatically.
- **A story can be a section of a compilation** (`平生第一次肛交成功记`, 1,725 chars, vs a 31,892-character report: 99 % of its text and one identical image). Remove only after the user agrees.
- **Keep rule for exact duplicates** (same normalized text and same image-name sequence): more unique images first, then the longest file name, then folder priority, then path order. Exact duplicates have equal image counts, so in practice the longest name wins.
- **Same text and same image names does not mean same bytes.** In the series `html` root 9 images of removed reports were larger JPEGs (same pixel size, about twice the file size; a lower-quality copy had been kept). Before deleting a quarantine, hash every quarantined image against its kept copy; for each difference compare dimensions and sizes, report them, and on the user's word copy the larger file over the kept one under the **kept** name (back the replaced file up first). The label of a differing pair must be the **kept** side's folder (a pair I called "学生妹" lived in `胜地`).
- **Quarantine procedure:** move duplicate reports plus the images used only by them to a scratchpad folder with the same relative paths; write a `removed → kept` TSV; back up all CSVs; repoint CSV rows (summary `output` → kept report, manifest `output` → kept image by position in the image sequence); also move a per-report image folder that is left with only `manifest.csv`; re-run the audit; delete the quarantine only on request after the byte/text check above.
- **Merging a source into an existing target** can re-add what was moved out earlier (section 23, step 4) and can find **nothing new** (a plain older copy): say so, change nothing, offer to delete the source.
- **Empty folders:** list first (`.DS_Store` does not count), remove with `rmdir`/`rm -r` only when no file is inside; an "empty `redarmy_II`" requested for merging was reported as empty, then removed on request.

## 29. Working habits (continued)

- Re-resolve every path the user gives: folders were created, moved or emptied between turns (`txt/tmp/…`, five `夜游` files, `redarmy_II`).
- After each destructive step print the backup path and the removed→kept log path.
- When a verification fails (9 differing images), stop, show the evidence and ask; do not delete anyway.
- Commit the rules doc only on request; push only on request.

## 30. Fake images and cross-root CSV rows (2026-11-18)

- **Fake image files.** A saved web page can leave an "image" that is really an error page (an HTML stub of 169–1,233 bytes, an XML stub of 345 bytes, or a 0-byte file). The report then shows a broken picture although the link resolves. Check every image file's header (`FF D8 FF` jpg, `89 50 4E 47` png, `GIF8`, `BM`), not only that the file exists. Six were found across `data.done` (1 in `2010_07.Reports/mc`, 1 in `2008_10_17_sss.Report/wet`, 2 in `老红军`/`老红军_2010_04`, 2 in `胜地`), each linked by one report.
- **Fix for a fake image** (on the user's word): replace the `<img …>` tag in the report with the marker `[image missing]` (the tag is followed by `<br>`, as in other reports); move the file to the scratchpad; in the manifest blank `output` and append ` [image file was not a picture]` to `status`; lower `images_copied` of the owning summary row(s) by 1 (rows that were repointed to the same report must be lowered too). Back up the report and CSVs first.
- **Cross-root CSV rows.** CSVs of older roots (`wet`, `russian`, `maichun`, `MCJT`) contain `output` paths like `../Reports.series-2026.11.17/html/<folder>/…` because reports were moved into the series library earlier. A de-duplication or move inside the series library therefore breaks rows in **other** roots (73 rows were left pointing at removed files: 7 + 53 in `wet`, 1 + 4 in `maichun`, 1 + 7 in `MCJT`). Rule: after any move, rename or de-duplication, scan **all** CSVs in `data.done` (`*/*.csv` and `*/html/*.csv`), not only the touched folder, and require 0 missing outputs. Repair with the removed → kept log (normalize the path relative to the CSV's folder, then `os.path.relpath` back).
- **Final check script idea** (for the future `merge_report_folders.py`): per root, links, orphans, header sniff of every image, CSV outputs, exact duplicates; then a root-independent pass over all CSVs for missing outputs.
