import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime


ROOT_DIR = Path(__file__).resolve().parent

_log_file_handle = None


def log(message: str = "") -> None:
    if message:
        print(message)
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
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            log(f"  {line}")
    if result.returncode != 0:
        raise RuntimeError(
            f"{script_name} 실행이 실패했습니다 "
            f"(exit code: {result.returncode})."
        )


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

    # v2는 이미 사건별로 분리되어 저장되므로, 제목 필드가 있는 항목을 카운트
    items_with_incidents = sum(
        1 for item in data if item.get('제목', '').strip()
    )

    def to_pct(count: int) -> str:
        return f"{count} / {total} ({count / total * 100:.1f}%)"

    log("\n[통계] 사건제목/사건내용 추출 현황")
    log(f" - 총 사건 수: {total} "
        f"(이미 사건별로 분리되어 저장됨)")
    pct = items_with_incidents / total * 100 if total > 0 else 0
    log(f" - 제목이 있는 사건: {items_with_incidents} ({pct:.1f}%)")

    # 업종별 통계
    industry_counts = {}
    for item in data:
        industry = item.get('업종', '기타')
        industry_counts[industry] = industry_counts.get(industry, 0) + 1

    if industry_counts:
        log("\n[통계] 업종별 분포")
        sorted_industries = sorted(
            industry_counts.items(), key=lambda x: x[1], reverse=True
        )
        for industry, count in sorted_industries:
            pct = count / total * 100 if total > 0 else 0
            log(f" - {industry}: {count}건 ({pct:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="금융정보분석원 제재공시 스크래핑 전체 파이프라인"
    )
    parser.add_argument(
        '--skip-scrape',
        action='store_true',
        help='기존 스크래핑 결과를 유지하고 분석 단계만 실행'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='통계만 출력 (스크래핑/추출 미실행)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        help='실행 로그를 저장할 파일 경로 (기록은 append 모드)'
    )
    args = parser.parse_args()

    json_path = ROOT_DIR / 'kofiu_results.json'

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
            run_step(
                'kofiu_scraper_v2.py',
                '1. 목록 및 PDF 스크래핑 (사건 추출 포함)'
            )
        else:
            log("\n[건너뜀] 스크래핑 단계는 "
                "--skip-scrape 옵션으로 생략했습니다.")

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
