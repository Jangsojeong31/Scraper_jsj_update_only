try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import argparse
import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime


ROOT_DIR = Path(__file__).resolve().parent

_log_file_handle = None


def log(message: str = "") -> None:
    if message:
        try:
            print(message)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or 'utf-8'
            safe_message = message.encode(encoding, errors='replace').decode(encoding, errors='replace')
            print(safe_message)
    else:
        print()
    if _log_file_handle:
        _log_file_handle.write(message + "\n")
        _log_file_handle.flush()


def run_step(script_name: str, description: str) -> None:
    script_path = ROOT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"{script_name} 파일을 찾을 수 없습니다.")

    log(f"\n[단계] {description} 실행 중...")
    env = os.environ.copy()
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    env.setdefault('PYTHONUTF8', '1')

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        env=env,
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            log(f"  {line}")
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} 실행이 실패했습니다 (exit code: {result.returncode}).")


def print_stats(json_path: Path) -> None:
    if not json_path.exists():
        log(f"통계 생성을 위한 파일이 존재하지 않습니다: {json_path}")
        return

    with json_path.open('r', encoding='utf-8') as f:
        data = json.load(f)

    total = len(data)
    if total == 0:
        log("데이터가 비어 있어 통계를 생성할 수 없습니다.")
        return

    def has_value(value: str) -> bool:
        return bool(value and value.strip() and value.strip() != '-')

    target_ok = sum(1 for item in data if has_value(item.get('제재대상', '')))
    sanction_ok = sum(1 for item in data if has_value(item.get('제재내용', '')))
    both_ok = sum(1 for item in data if has_value(item.get('제재대상', '')) and has_value(item.get('제재내용', '')))

    def to_pct(count: int) -> str:
        return f"{count} / {total} ({count / total * 100:.1f}%)"

    log("\n[통계] 제재대상/제재내용 추출 현황")
    log(f" - 제재대상 추출 성공: {to_pct(target_ok)}")
    log(f" - 제재내용 추출 성공: {to_pct(sanction_ok)}")
    log(f" - 둘 다 추출 성공: {to_pct(both_ok)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="금감원 경영유의사항 공시 스크래핑 전체 파이프라인")
    parser.add_argument('--skip-scrape', action='store_true', help='기존 스크래핑 결과를 유지하고 분석 단계만 실행')
    parser.add_argument('--skip-ocr-retry', action='store_true', help='ocr_failed_items.py 실행 생략')
    parser.add_argument('--stats-only', action='store_true', help='통계만 출력 (스크래핑/추출 미실행)')
    parser.add_argument('--log-file', type=str, help='실행 로그를 저장할 파일 경로 (append 모드)')
    args = parser.parse_args()

    json_path = ROOT_DIR / 'fss_results.json'

    log_file_handle = None

    try:
        if args.log_file:
            log_path = Path(args.log_file).expanduser()
            if not log_path.parent.exists():
                log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file_handle = log_path.open('a', encoding='utf-8')
            global _log_file_handle
            _log_file_handle = log_file_handle
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log(f"[로그 시작] {timestamp} | 파일: {log_path.resolve()}")

        if args.stats_only:
            print_stats(json_path)
            return

        if not args.skip_scrape:
            run_step('fss_scraper.py', '1. 목록 및 PDF 스크래핑')
        else:
            log("\n[건너뜀] 스크래핑 단계는 --skip-scrape 옵션으로 생략했습니다.")

        run_step('extract_sanctions.py', '2. 제재대상/제재내용 추출 (OCR 후처리 포함)')

        ocr_retry_script = ROOT_DIR / 'ocr_failed_items.py'
        if not args.skip_ocr_retry and ocr_retry_script.exists():
            run_step('ocr_failed_items.py', '3. OCR 실패 항목 재처리')
        elif not ocr_retry_script.exists():
            log("\n[정보] ocr_failed_items.py 파일이 없어 재처리 단계를 건너뜁니다.")
        else:
            log("\n[건너뜀] --skip-ocr-retry 옵션으로 OCR 재처리 단계를 생략했습니다.")

        print_stats(json_path)
    finally:
        if log_file_handle:
            log(" ")
            log("[로그 종료]")
            log_file_handle.close()
            _log_file_handle = None


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f"\n[오류] {exc}")
        sys.exit(1)

