#!/usr/bin/env python3
"""
amazon.photos.viewer — Browse your local Amazon Photos mirror.

Virtual-scroll grid: only the visible rows have widgets in memory,
so 50K+ photo libraries open without OOM.

Usage:
    python viewer.py --mirror-root /path/to/mirror
"""

import argparse
import json
import queue
import threading
from collections import OrderedDict
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

try:
    from PIL import Image, ImageTk
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    PIL_OK = True
except ImportError:
    PIL_OK = False

THUMB_W    = 160
THUMB_H    = 130
CELL_PAD   = 6
GRID_COLS  = 5
LABEL_H    = 20
ROW_H      = THUMB_H + LABEL_H + CELL_PAD * 3   # px per grid row
COL_W      = THUMB_W + CELL_PAD * 2             # px per grid column
BUFFER_ROWS = 3     # rows rendered above/below visible area
MAX_CACHE   = 400   # max thumbnails held in memory at once

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif",
                  ".tiff", ".webp", ".heic", ".raw"}

BG_DARK  = "#1e1e1e"
BG_PANEL = "#252526"
BG_CELL  = "#2d2d2d"
FG_WHITE = "#ffffff"
FG_DIM   = "#888888"
ACCENT   = "#094771"


class _LRUCache:
    """Thread-safe LRU cache for ImageTk.PhotoImage objects."""
    def __init__(self, maxsize: int):
        self._d: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._d:
                return None
            self._d.move_to_end(key)
            return self._d[key]

    def put(self, key, value) -> None:
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
            else:
                if len(self._d) >= self._maxsize:
                    self._d.popitem(last=False)
            self._d[key] = value


class PhotoViewer:
    def __init__(self, root: tk.Tk, mirror_root: Path):
        self.root = root
        self.mirror_root  = mirror_root
        self.pics_dir     = mirror_root / "pics"
        self.albums_dir   = mirror_root / "albums"

        self._all_photos: list[Path] = []
        self._albums:     dict[str, list[Path]] = {}
        self._current_photos: list[Path] = []
        self._total_rows: int = 0

        self._thumb_cache    = _LRUCache(MAX_CACHE)
        self._rendered_rows: dict[int, list[tk.Widget]] = {}
        self._stop_event     = threading.Event()
        self._thumb_queue: queue.Queue = queue.Queue()
        self._scroll_after   = None
        self._sort_var       = tk.StringVar(value="name")
        self._placeholder    = None

        self._load_data()
        self._build_ui()
        self._start_thumb_worker()

        self._album_list.selection_set(0)
        # Defer initial render until the window is fully sized
        self.root.after(120, lambda: self._show_album("All Photos"))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self.pics_dir.exists():
            self._all_photos = sorted(
                p for p in self.pics_dir.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            )
        if self.albums_dir.exists():
            for jf in sorted(self.albums_dir.glob("*.json")):
                try:
                    data  = json.loads(jf.read_text(encoding="utf-8"))
                    name  = data.get("name", jf.stem)
                    paths = []
                    for entry in data.get("photos", []):
                        lp = entry.get("local_path")
                        if lp:
                            p = Path(lp)
                            if p.exists():
                                paths.append(p)
                    self._albums[name] = paths
                except Exception:
                    pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.title("Amazon Photos Viewer")
        self.root.geometry("1100x760")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(700, 500)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=BG_PANEL,
                        troughcolor=BG_DARK, arrowcolor=FG_DIM)
        style.configure("TRadiobutton", background="#2d2d2d",
                        foreground=FG_WHITE, font=("Segoe UI", 10))

        # Toolbar
        toolbar = tk.Frame(self.root, bg="#2d2d2d", pady=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(toolbar, text="  Sort by:", bg="#2d2d2d",
                 fg=FG_DIM, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        for val, label in [("name", "Name"), ("date", "Date (oldest first)")]:
            ttk.Radiobutton(toolbar, text=label, variable=self._sort_var,
                            value=val, command=self._refresh).pack(side=tk.LEFT, padx=6)
        self._status_lbl = tk.Label(toolbar, text="", bg="#2d2d2d",
                                    fg=FG_DIM, font=("Segoe UI", 10))
        self._status_lbl.pack(side=tk.RIGHT, padx=12)

        main = tk.Frame(self.root, bg=BG_DARK)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Album sidebar
        left = tk.Frame(main, bg=BG_PANEL, width=210)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        tk.Label(left, text="Albums", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 11, "bold"), pady=10).pack(fill=tk.X, padx=8)
        self._album_list = tk.Listbox(
            left, bg=BG_PANEL, fg="#cccccc",
            selectbackground=ACCENT, selectforeground=FG_WHITE,
            borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), activestyle="none", relief="flat",
        )
        self._album_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._album_list.bind("<<ListboxSelect>>", self._on_album_select)
        self._album_list.insert(tk.END, "All Photos")
        for name in sorted(self._albums):
            self._album_list.insert(tk.END, name)
        n = len(self._albums)
        tk.Label(left, text=f"{n} album{'s' if n != 1 else ''}",
                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 9)).pack(pady=(0, 8))

        # Photo canvas (thumbnails drawn directly here — no child frame)
        right = tk.Frame(main, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(right, bg=BG_DARK, highlightthickness=0, bd=0)

        def _yview_and_render(*args):
            self._canvas.yview(*args)
            self._schedule_render()

        vscroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=_yview_and_render)
        self._canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas.bind("<Configure>",  lambda e: self._schedule_render())
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)

        if PIL_OK:
            self._placeholder = ImageTk.PhotoImage(
                Image.new("RGB", (THUMB_W, THUMB_H), BG_CELL)
            )

    # ── Scroll handling ───────────────────────────────────────────────────────

    def _on_mousewheel(self, event) -> None:
        if event.delta:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        self._schedule_render()

    def _schedule_render(self) -> None:
        """Debounce: fire _render_visible 80 ms after the last scroll/resize."""
        if self._scroll_after:
            self.root.after_cancel(self._scroll_after)
        self._scroll_after = self.root.after(80, self._render_visible)

    # ── Album selection ───────────────────────────────────────────────────────

    def _on_album_select(self, event) -> None:
        sel = self._album_list.curselection()
        if sel:
            self._show_album(self._album_list.get(sel[0]))

    def _refresh(self) -> None:
        sel = self._album_list.curselection()
        self._show_album(self._album_list.get(sel[0]) if sel else "All Photos")

    def _sorted(self, photos: list[Path]) -> list[Path]:
        if self._sort_var.get() == "date":
            return sorted(photos, key=lambda p: p.stat().st_mtime)
        return sorted(photos, key=lambda p: p.name.lower())

    # ── Virtual-scroll display ────────────────────────────────────────────────

    def _show_album(self, album_name: str) -> None:
        # Cancel in-flight thumbnail loads from previous view
        self._stop_event.set()
        self._stop_event = threading.Event()
        try:
            while True:
                self._thumb_queue.get_nowait()
        except queue.Empty:
            pass

        photos = (self._all_photos if album_name == "All Photos"
                  else list(self._albums.get(album_name, [])))
        self._current_photos = self._sorted(photos)
        self._total_rows = (len(self._current_photos) + GRID_COLS - 1) // GRID_COLS

        self._status_lbl.config(
            text=f"{len(self._current_photos):,} photo{'s' if len(self._current_photos) != 1 else ''}"
        )

        self._destroy_rows(list(self._rendered_rows.keys()))
        self._canvas.delete("all")

        total_h = max(self._total_rows * ROW_H, 1)
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width() or 900, total_h))
        self._canvas.yview_moveto(0)

        if not PIL_OK:
            self._canvas.create_text(450, 60, text="Install Pillow: pip install pillow",
                                     fill=FG_WHITE, font=("Segoe UI", 12))
            return
        if not self._current_photos:
            msg = ("No photos yet — run cloner.py first." if album_name == "All Photos"
                   else f"Album '{album_name}' is empty.")
            self._canvas.create_text(450, 60, text=msg, fill=FG_DIM, font=("Segoe UI", 11))
            return

        self._render_visible()

    def _render_visible(self) -> None:
        """Create rows entering the viewport; destroy rows that scrolled away."""
        if not self._current_photos or self._total_rows == 0:
            return

        # Guard: canvas not yet sized
        if self._canvas.winfo_height() <= 1:
            self.root.after(100, self._render_visible)
            return

        total_h   = self._total_rows * ROW_H
        ylo, yhi  = self._canvas.yview()
        top_px    = ylo * total_h
        bottom_px = yhi * total_h

        first_row = max(0, int(top_px  / ROW_H) - BUFFER_ROWS)
        last_row  = min(self._total_rows - 1, int(bottom_px / ROW_H) + BUFFER_ROWS)

        # Destroy rows that left the viewport buffer
        stale = [r for r in list(self._rendered_rows) if r < first_row or r > last_row]
        self._destroy_rows(stale)

        # Create newly visible rows
        for row_idx in range(first_row, last_row + 1):
            if row_idx not in self._rendered_rows:
                self._create_row(row_idx)

    def _create_row(self, row_idx: int) -> None:
        """Place one row of cells as canvas window items."""
        widgets = []
        y = row_idx * ROW_H

        for col_idx in range(GRID_COLS):
            photo_idx = row_idx * GRID_COLS + col_idx
            if photo_idx >= len(self._current_photos):
                break
            photo_path = self._current_photos[photo_idx]
            x = col_idx * COL_W + CELL_PAD

            cell = tk.Label(self._canvas, image=self._placeholder,
                            bg=BG_CELL, cursor="hand2")
            self._canvas.create_window(x, y + CELL_PAD, window=cell, anchor="nw")

            fname = photo_path.name
            short = fname if len(fname) <= 22 else fname[:19] + "..."
            lbl = tk.Label(self._canvas, text=short,
                           bg=BG_DARK, fg=FG_DIM, font=("Segoe UI", 8))
            self._canvas.create_window(x, y + CELL_PAD + THUMB_H + 4,
                                       window=lbl, anchor="nw")

            cell.bind("<Button-1>", lambda e, p=photo_path: self._open_full(p))
            widgets.extend([cell, lbl])

            self._thumb_queue.put((photo_path, cell, self._stop_event))

        self._rendered_rows[row_idx] = widgets

    def _destroy_rows(self, row_indices: list[int]) -> None:
        for row_idx in row_indices:
            for w in self._rendered_rows.pop(row_idx, []):
                try:
                    w.destroy()
                except tk.TclError:
                    pass

    # ── Thumbnail background worker ───────────────────────────────────────────

    def _start_thumb_worker(self) -> None:
        threading.Thread(target=self._thumb_worker, daemon=True).start()

    def _thumb_worker(self) -> None:
        while True:
            try:
                path, cell, stop = self._thumb_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if stop.is_set():
                continue  # stale item from a previous album view

            key   = str(path)
            photo = self._thumb_cache.get(key)
            if photo is None:
                try:
                    img = Image.open(path)
                    img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._thumb_cache.put(key, photo)
                except Exception:
                    continue

            self.root.after(0, self._apply_thumb, cell, photo)

    def _apply_thumb(self, cell: tk.Label, photo) -> None:
        try:
            if cell.winfo_exists():
                cell.configure(image=photo)
                cell._photo = photo  # prevent GC while cell is alive
        except tk.TclError:
            pass

    # ── Full-size viewer ──────────────────────────────────────────────────────

    def _open_full(self, path: Path) -> None:
        win = tk.Toplevel(self.root)
        win.title(path.name)
        win.configure(bg="#000000")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        try:
            img = Image.open(path)
            img.thumbnail((sw - 80, sh - 80), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            messagebox.showerror("Cannot open photo", f"{path.name}:\n{e}", parent=win)
            win.destroy()
            return
        lbl = tk.Label(win, image=photo, bg="#000000")
        lbl.image = photo
        lbl.pack()
        tk.Label(win, text="Click image or press Esc to close",
                 bg="#000000", fg="#444444", font=("Segoe UI", 9)).pack(pady=4)
        win.geometry(f"{img.width}x{img.height + 28}")
        lbl.bind("<Button-1>", lambda e: win.destroy())
        win.bind("<Escape>",   lambda e: win.destroy())
        win.focus_set()


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse local Amazon Photos mirror")
    parser.add_argument("--mirror-root", required=True,
                        help="Path to the local mirror root folder")
    args = parser.parse_args()
    mirror_root = Path(args.mirror_root)
    if not mirror_root.exists():
        print(f"Error: mirror root not found: {mirror_root}")
        raise SystemExit(1)
    root = tk.Tk()
    PhotoViewer(root, mirror_root)
    root.mainloop()


if __name__ == "__main__":
    main()
