# Default processing rule for Word `.doc` files

The noise-cleaning rule below applies to the text of every `.doc` file. Each file produces up to three kinds of output (see Outputs layout). A text-only file (no images) produces only the `txt` output and a report without images.

## Goal

Remove forum watermarks and the human-unreadable garbage characters that follow them, and keep the readable text.

Example of the noise:

```
本帖来源 http://www.maichun.org 买春堂版权所有# h6 T4 u+ J6 S% c/ E7 U
```

## Rule

1. **Never modify the original.** Read from `inputs/`, write results to `outputs/` using the layout below.
2. **Extract text.** Use macOS `textutil -convert txt -encoding UTF-8`.
3. **Remove the noise block.** Delete the watermark and the garbage run that follows it:
   - Watermark: `本帖来源\s*https?://www.maichun.org\s*买春堂版权所有`
   - Garbage run: any number of tokens of 1–2 printable ASCII characters (`!`–`~`), separated by a space or NBSP (` `). Each token must be followed by a space, NBSP, line break (` `, ` `, `\r`, `\n`), ideographic space (`　`) or end of text.
   - The run stops at the first line break or non-ASCII character (e.g. Chinese text or `【`), so the body text is not touched.
4. **Write the outputs.** Save the three outputs described in Outputs layout. Original Word formatting is not preserved in the pure txt.
5. **Verify** (see below).

## Outputs layout

Every source file `<stem>.doc` produces three outputs, grouped by type under `outputs/`:

```
outputs/
├── txt/
│   └── <stem>.txt              # (1) pure text: cleaned, UTF-8, no images
├── images/
│   └── <source folder name>/   # (2) pure images, one sub-folder per source folder
│       ├── p01_<orig name>.jpg
│       └── manifest.csv        #     new name -> source path
└── reports/
    └── <stem>.html  or  <stem>.doc   # (3) report: cleaned text + the images
```

1. **Pure txt** (`outputs/txt/`): only text, noise removed, no image placeholders.
2. **Pure images** (`outputs/images/<source folder name>/`): the sub-folder is named after the original folder, e.g. `inputs/2008_10_17_sss.Report/crazy` -> `outputs/images/crazy/`, `.../RussianChicken` -> `outputs/images/RussianChicken/`.
   - Source: saved web pages (`<page>.htm` + `<page>_files/`). All `jpg/jpeg/png/gif/bmp` under the page `_files` folders are **copied** (originals untouched) into the one flat sub-folder. `Thumbs.db` and non-image files are skipped.
   - Naming: `p<NN>_<original name>`, where `NN` is the page index in sorted order. Different pages reuse names such as `01.jpg`, so the prefix prevents overwriting.
   - `manifest.csv` in each sub-folder maps every new name to its source path.
   - Tool: `collect_images.py`. Check the output count equals the number of source images.
3. **Report** (`outputs/reports/`): the cleaned text with the images in their original positions. Use one of:
   - `.html`: images are referenced from `../images/<source folder name>/` (or embedded as base64 if the report must be a single file).
   - `.doc`: images are embedded in the document.

   Pick one format per run and apply it to every file in that run. For a file with no images the report contains text only.

The noise-cleaning in step 3 of the Rule must be applied to the text in the txt and the report, never only to one of them.

## Saved forum pages (`.htm` + `_files`)

Tool: `process_html_posts.py <source folder> -o outputs` (stdlib only; `htmltree.py` is its small HTML parser). Handles Discuz-style threads, where each post is a `<table id="pidNNN">`; the first one is the primary post, the others are replies. The page's declared charset (big5 / gbk) is used for decoding.

Decision per page:

| Page content | Output |
|---|---|
| Primary post or any reply has images | **HTML report** with the primary post plus every reply that has images. Only those posts' images are copied. |
| No images anywhere | **TXT** with the primary post text only (title, author, text). |
| No `pid` tables (other forum layout) | Not processed, listed as `unsupported` in the summary for manual review. |

If only a reply has images, the primary post is still included in the report, as context.

Outputs are grouped by source folder name, mirroring the relative path inside it:

```
outputs/txt/<folder>/<rel path>.txt
outputs/reports/<folder>/<rel path>.html     images linked as ../../images/<folder>/...
outputs/images/<folder>/p<NNN>_<name>        NNN = page index, avoids name clashes
outputs/<folder>_summary.csv                 per page: mode, posts, images, unresolved image refs
```

Noise removal, in this order:
1. **Hidden garbage elements are dropped**: `font-size:0`, `display:none`, `visibility:hidden`, and white-font text (`color:#fff`) with no Chinese characters. This is where the random-character garbage lives in these pages.
2. **Ads** (`id` starting `ad_` or containing `overture`) are dropped.
3. **Watermark regex** (the `.doc` rule above) is applied to the text of each post.
4. Whitespace is normalised and blank-line runs are collapsed.

Image rules: only `jpg/jpeg/png/bmp` whose file exists locally count as images. Forum smilies are not saved in these folders, so they are ignored. If the saved `_files` folder was renamed, an image is accepted when its file name matches exactly one file in the sibling `_files` folders. `unresolved_img_refs` in the summary counts image references whose file could not be found.

Check after a run: watermark leftovers must be 0, every `<img>` in the reports must exist, and images copied must match the summary.

## Verification

- The script reports `leftovers` (any remaining `本帖来源`, `买春堂版权所有` or `www.maichun.org`). It must be `0`.
- Scan the output for runs of 3 or more short ASCII tokens, or short ASCII tokens at the end of a line. Review each hit by hand. Real text such as `KJ  ML` or an English sentence is a false positive and should stay.
- Do not print or dump the document body when checking. Report counts and short context only.

## Known limits

- Only the `maichun.org` / `买春堂` watermark is handled. A different watermark needs its own `WATERMARK` pattern.
- Short ASCII words right after a watermark on the same line (for example `FL`) could be removed as garbage. In the first two files this did not happen, but review the hits when processing new files.
- `clean_doc_noise.py` does not yet follow the txt/reports layout. It writes a flat `.txt` and `.doc` into `outputs/`, so the `txt/` and `reports/` outputs still need to be implemented. Images are done (`collect_images.py`) for the saved-web-page folders `crazy` and `RussianChicken`.
- The `wet` folder has 2 pages with another layout (`unsupported`) and a few pages whose image files are saved under broken names, so they fall back to txt. Both are listed in `wet_summary.csv`.
- Images embedded inside a `.doc` are not extracted yet; `collect_images.py` only handles saved-web-page folders.

## Usage

```bash
cd history-files-merge
source venv/bin/activate        # always activate the venv first
python clean_doc_noise.py "inputs/<folder>/<file>.doc" [more.doc ...] -o outputs
```

Images from a saved-web-page folder:

```bash
python collect_images.py "inputs/<folder>/crazy" "inputs/<folder>/RussianChicken" -o outputs
```

Implementation: `clean_doc_noise.py` (standard library only; needs macOS `textutil`).

## Reference run (first 2 files)

| File | Watermark blocks removed | Characters before → after |
|---|---|---|
| `2008-09-10.doc` | 38 | 9,422 → 7,219 |
| `彭城寻春系列.doc` | 400 | 59,492 → 36,012 |
