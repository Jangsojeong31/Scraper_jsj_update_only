import os
import runpy
from pathlib import Path
import sys


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    current_dir = Path(__file__).resolve().parent
    target_script = current_dir.parent / "FSS_Sanctions_Scraper" / "ocr_failed_items.py"
    if not target_script.exists():
        raise FileNotFoundError(f"원본 스크립트를 찾을 수 없습니다: {target_script}")

    previous_cwd = Path.cwd()
    try:
        os.chdir(current_dir)
        runpy.run_path(str(target_script), run_name="__main__")
    finally:
        os.chdir(previous_cwd)


if __name__ == "__main__":
    main()

