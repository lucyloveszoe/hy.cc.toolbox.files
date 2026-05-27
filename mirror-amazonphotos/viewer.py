#!/usr/bin/env python3
"""
amazon.photos.viewer — Browse your local Amazon Photos mirror.

Reads from the local mirror created by cloner.py — no internet connection needed.
Displays a scrollable thumbnail grid with an album sidebar.

Usage:
    python viewer.py --mirror-root C:\\tmp\\mirror
"""

import argparse
import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # HEIC support optional; non-HEIC photos still work
    PIL_OK = True
except ImportError:
    PIL_OK = False

THUMB_W = 160
THUMB_H = 130
CELL_PAD = 6
GRID_COLS = 5
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".heic", ".raw"}

BG_DARK = "#1e1e1e"
BG_PANEL = "#252526"
BG_CELL = "#2d2d2d"
BG_CELL_HOVER = "#3a3a3a"
FG_WHITE = "#ffffff"
FG_DIM = "#888888"
ACCENT = "#094771"


class PhotoViewer:
    def __init__(self, root: tk.Tk, mirror_root: Path):
        self.root = root
        self.mirror_root = mirror_root
        self.pics_dir = mirror_root / "pics"
        self.albums_dir = mirror_root / "albums"

        self._all_photos: list[Path] = []
        self._albums: dict[str, list[Path]] = {}   # album_name → photo paths
        self._current_photos: list[Path] = []
        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._thumb_refs: list = []    # prevent garbage collection of PhotoImage objects
        self._cell_widgets: list[tk.Label] = []
        self._placeholder: ImageTk.PhotoImage | None = None
        self._stop_event = threading.Event()
        self._sort_var = tk.StringVar(value="name")

        self._load_data()
        self._build_ui()

        # Show all photos on launch
        self._album_list.selection_set(0)
        self._show_album("All Photos")

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        """Scan pics/ and albums/ directories to build in-memory photo and album lists."""
        if self.pics_dir.exists():
            self._all_photos = sorted(
                p for p in self.pics_dir.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            )

        if self.albums_dir.exists():
            for jf in sorted(self.albums_dir.glob("*.json")):
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    name = data.get("name", jf.stem)
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
        style.configure("TRadiobutton", background="#2d2d2d", foreground=FG_WHITE,
                        font=("Segoe UI", 10))

        # ── Toolbar ──
        toolbar = tk.Frame(self.root, bg="#2d2d2d", pady=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Label(toolbar, text="  Sort by:", bg="#2d2d2d",
                 fg=FG_DIM, font=("Segoe UI", 10)).pack(side=tk.LEFT)

        for val, label in [("name", "Name"), ("date", "Date (oldest first)")]:
            ttk.Radiobutton(
                toolbar, text=label, variable=self._sort_var,
                value=val, command=self._refresh,
            ).pack(side=tk.LEFT, padx=6)

        self._status_lbl = tk.Label(toolbar, text="", bg="#2d2d2d",
                                    fg=FG_DIM, font=("Segoe UI", 10))
        self._status_lbl.pack(side=tk.RIGHT, padx=12)

        # ── Main area (left panel + right canvas) ──
        main = tk.Frame(self.root, bg=BG_DARK)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: album list
        left = tk.Frame(main, bg=BG_PANEL, width=210)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        tk.Label(left, text="Albums", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 11, "bold"), pady=10).pack(fill=tk.X, padx=8)

        self._album_list = tk.Listbox(
            left,
            bg=BG_PANEL, fg="#cccccc",
            selectbackground=ACCENT, selectforeground=FG_WHITE,
            borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), activestyle="none",
            relief="flat",
        )
        self._album_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._album_list.bind("<<ListboxSelect>>", self._on_album_select)

        self._album_list.insert(tk.END, "All Photos")
        for name in sorted(self._albums):
            self._album_list.insert(tk.END, name)

        album_count = len(self._albums)
        tk.Label(left, text=f"{album_count} album{'s' if album_count != 1 else ''}",
                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 9)).pack(pady=(0, 8))

        # Right: scrollable photo grid
        right = tk.Frame(main, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(right, bg=BG_DARK, highlightthickness=0, bd=0)
        vscroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vscroll.set)

        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._grid_frame = tk.Frame(self._canvas, bg=BG_DARK)
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._grid_frame, anchor="nw"
        )

        self._grid_frame.bind("<Configure>", self._on_frame_resize)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", self._on_mousewheel)   # Linux scroll up
        self._canvas.bind("<Button-5>", self._on_mousewheel)   # Linux scroll down

        # Create placeholder once (reused for all empty cells)
        if PIL_OK:
            self._placeholder = ImageTk.PhotoImage(
                Image.new("RGB", (THUMB_W, THUMB_H), BG_CELL)
            )

    # ── Canvas sizing ─────────────────────────────────────────────────────────

    def _on_frame_resize(self, event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, event) -> None:
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.delta:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")

    # ── Album selection ───────────────────────────────────────────────────────

    def _on_album_select(self, event) -> None:
        sel = self._album_list.curselection()
        if not sel:
            return
        self._show_album(self._album_list.get(sel[0]))

    def _refresh(self) -> None:
        sel = self._album_list.curselection()
        album = self._album_list.get(sel[0]) if sel else "All Photos"
        self._show_album(album)

    # ── Photo display ─────────────────────────────────────────────────────────

    def _sorted(self, photos: list[Path]) -> list[Path]:
        if self._sort_var.get() == "date":
            return sorted(photos, key=lambda p: p.stat().st_mtime)
        return sorted(photos, key=lambda p: p.name.lower())

    def _show_album(self, album_name: str) -> None:
        # Cancel any in-flight thumbnail loader
        self._stop_event.set()
        self._stop_event = threading.Event()

        photos = self._all_photos if album_name == "All Photos" \
            else list(self._albums.get(album_name, []))
        self._current_photos = self._sorted(photos)

        self._status_lbl.config(
            text=f"Showing {len(self._current_photos):,} photo{'s' if len(self._current_photos) != 1 else ''}"
        )

        # Rebuild grid
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._cell_widgets.clear()
        self._thumb_refs.clear()

        if not PIL_OK:
            tk.Label(
                self._grid_frame,
                text="Install Pillow to view thumbnails:\n  pip install pillow",
                bg=BG_DARK, fg=FG_WHITE, pady=40, font=("Segoe UI", 12),
            ).grid(row=0, column=0, columnspan=GRID_COLS)
            return

        if not self._current_photos:
            msg = ("No photos in the mirror yet.\n"
                   "Run cloner.py to download your Amazon Photos library."
                   if album_name == "All Photos"
                   else f"No photos found in album '{album_name}'.")
            tk.Label(self._grid_frame, text=msg, bg=BG_DARK,
                     fg=FG_DIM, pady=40, font=("Segoe UI", 11)).grid(
                row=0, column=0, columnspan=GRID_COLS)
            return

        # Place placeholder cells
        for i, photo_path in enumerate(self._current_photos):
            row, col = divmod(i, GRID_COLS)

            cell_frame = tk.Frame(self._grid_frame, bg=BG_CELL,
                                  padx=2, pady=2)
            cell_frame.grid(row=row * 2, column=col,
                            padx=CELL_PAD, pady=(CELL_PAD, 0), sticky="n")

            cell = tk.Label(cell_frame, image=self._placeholder,
                            bg=BG_CELL, cursor="hand2",
                            width=THUMB_W, height=THUMB_H)
            cell.pack()

            # Filename label below thumbnail
            fname = photo_path.name
            short = fname if len(fname) <= 22 else fname[:19] + "..."
            tk.Label(self._grid_frame, text=short, bg=BG_DARK,
                     fg=FG_DIM, font=("Segoe UI", 8), wraplength=THUMB_W).grid(
                row=row * 2 + 1, column=col, pady=(0, CELL_PAD))

            p = photo_path
            cell.bind("<Button-1>", lambda e, path=p: self._open_full(path))
            cell_frame.bind("<Button-1>", lambda e, path=p: self._open_full(path))

            self._cell_widgets.append(cell)

        # Scroll to top
        self._canvas.yview_moveto(0)

        # Load thumbnails in background
        t = threading.Thread(
            target=self._load_thumbs_bg,
            args=(list(self._current_photos), list(self._cell_widgets), self._stop_event),
            daemon=True,
        )
        t.start()

    def _load_thumbs_bg(
        self,
        photos: list[Path],
        cells: list[tk.Label],
        stop: threading.Event,
    ) -> None:
        """Background thread: open each image, create thumbnail, queue UI update."""
        for path, cell in zip(photos, cells):
            if stop.is_set():
                return
            key = str(path)
            if key in self._thumb_cache:
                photo = self._thumb_cache[key]
            else:
                try:
                    img = Image.open(path)
                    img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._thumb_cache[key] = photo
                except Exception:
                    continue
            self.root.after(0, self._apply_thumb, cell, photo)

    def _apply_thumb(self, cell: tk.Label, photo: ImageTk.PhotoImage) -> None:
        try:
            cell.configure(image=photo)
            self._thumb_refs.append(photo)  # keep alive
        except tk.TclError:
            pass  # widget was destroyed during album switch

    # ── Full-size viewer ──────────────────────────────────────────────────────

    def _open_full(self, path: Path) -> None:
        win = tk.Toplevel(self.root)
        win.title(path.name)
        win.configure(bg="#000000")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        try:
            img = Image.open(path)
            img.thumbnail((screen_w - 80, screen_h - 80), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            messagebox.showerror("Cannot open photo",
                                 f"{path.name}:\n{e}", parent=win)
            win.destroy()
            return

        lbl = tk.Label(win, image=photo, bg="#000000")
        lbl.image = photo
        lbl.pack()

        hint = tk.Label(win, text="Click image or press Esc to close",
                        bg="#000000", fg="#444444", font=("Segoe UI", 9))
        hint.pack(pady=4)

        win.geometry(f"{img.width}x{img.height + 28}")
        lbl.bind("<Button-1>", lambda e: win.destroy())
        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_set()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browse local Amazon Photos mirror",
        epilog="Example: python viewer.py --mirror-root C:\\tmp\\mirror",
    )
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
