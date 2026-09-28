"""Recursively convert all PNG/BMP images under a folder to JPEG (quality=90).

Usage:
    python convert_to_jpeg.py <target_folder>

Behavior:
    - Recurses into all sub-folders of <target_folder>.
    - Converts every .png / .bmp file to .jpg at JPEG quality=90.
    - Deletes the original PNG/BMP file only after the JPEG has been
      written and verified to load successfully.
    - If a .jpg with the same base name already exists, the file is
      skipped (not overwritten) and reported.
"""

import sys
from pathlib import Path

from PIL import Image

JPEG_QUALITY = 90
SOURCE_EXTENSIONS = {".png", ".bmp"}


def is_source_image(path: Path) -> bool:
    return path.suffix.strip().lower() in SOURCE_EXTENSIONS


def convert_image(src_path: Path) -> tuple[bool, str]:
    dst_path = src_path.with_suffix(".jpg")

    if dst_path.exists():
        return False, f"SKIPPED (target already exists): {dst_path}"

    try:
        with Image.open(src_path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(dst_path, "JPEG", quality=JPEG_QUALITY)

        # Verify the newly written JPEG is valid before deleting the source.
        with Image.open(dst_path) as check_img:
            check_img.verify()

    except Exception as exc:
        if dst_path.exists():
            dst_path.unlink()
        return False, f"FAILED: {src_path} ({exc})"

    src_size_kb = round(src_path.stat().st_size / 1024, 2)
    dst_size_kb = round(dst_path.stat().st_size / 1024, 2)
    src_path.unlink()
    return True, f"OK: {src_path} -> {dst_path} ({src_size_kb} KB -> {dst_size_kb} KB)"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python convert_to_jpeg.py <target_folder>")
        sys.exit(1)

    target_folder = Path(sys.argv[1])
    if not target_folder.is_dir():
        print(f"Error: not a folder: {target_folder}")
        sys.exit(1)

    converted = 0
    skipped = 0
    failed = 0

    for path in sorted(target_folder.rglob("*")):
        if not path.is_file() or not is_source_image(path):
            continue

        success, message = convert_image(path)
        print(message)

        if success:
            converted += 1
        elif message.startswith("SKIPPED"):
            skipped += 1
        else:
            failed += 1

    print("\n--- Summary ---")
    print(f"Converted: {converted}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")


if __name__ == "__main__":
    main()
