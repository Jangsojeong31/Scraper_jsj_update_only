import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_scraper(output_dir: Path, limit: Optional[int], skip_attachments: bool) -> int:
    script_path = Path(__file__).resolve().parent / "fss_scraper.py"
    cmd = [sys.executable, str(script_path), "--output-dir", str(output_dir)]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    if skip_attachments:
        cmd.append("--skip-attachments")
    process = subprocess.run(cmd, text=True)
    return process.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검사업무 메뉴얼 스크랩핑 전체 파이프라인")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent),
        help="결과 파일을 저장할 경로 (기본값: 스크립트 디렉터리)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="수집할 게시글 수 제한 (기본값: 제한 없음)",
    )
    parser.add_argument(
        "--skip-attachments",
        action="store_true",
        help="첨부파일 다운로드 및 점검표 추출을 건너뜁니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[정보] 스크레이퍼 실행...")
    exit_code = run_scraper(output_dir, args.limit, args.skip_attachments)
    if exit_code != 0:
        print(f"[오류] 스크레이퍼 실행 실패 (exit code={exit_code})")
        sys.exit(exit_code)

    print("[완료] 파이프라인 실행이 완료되었습니다.")


if __name__ == "__main__":
    main()
