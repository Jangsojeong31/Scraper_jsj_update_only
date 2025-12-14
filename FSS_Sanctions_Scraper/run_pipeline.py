import argparse
import json
import subprocess
import sys
import os
import io
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


def run_step(script_name: str, description: str, extra_args: list = None) -> None:
    script_path = ROOT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"{script_name} 파일을 찾을 수 없습니다.")

    log(f"\n[단계] {description} 실행 중...")
    cmd = [sys.executable, '-u', str(script_path)]  # -u: unbuffered output
    if extra_args:
        cmd.extend(extra_args)
    
    # 실시간 출력을 위해 Popen 사용 (인코딩 오류 방지)
    # Windows에서 인코딩 오류를 방지하기 위해 환경 변수 설정
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'  # Python 3.7+ UTF-8 모드
    
    # subprocess를 실행할 때 인코딩 오류를 방지하기 위해
    # stdout을 직접 읽지 않고 communicate() 사용하거나
    # 더 안전한 방법으로 처리
    try:
        process = subprocess.Popen(
            cmd,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,  # bytes로 받기
            bufsize=0,  # unbuffered
            env=env,
        )
        
        # 실시간으로 출력 읽기 (bytes를 직접 읽어서 안전하게 디코딩)
        # _readerthread 오류를 방지하기 위해 직접 읽기
        buffer = b''
        while True:
            chunk = process.stdout.read(8192)  # 8KB씩 읽기
            if not chunk:
                break
            
            buffer += chunk
            
            # 줄 단위로 분리하여 처리
            while b'\n' in buffer:
                line_bytes, buffer = buffer.split(b'\n', 1)
                try:
                    # UTF-8로 디코딩 시도
                    line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                except Exception:
                    # 실패 시 cp949로 시도
                    try:
                        line = line_bytes.decode('cp949', errors='replace').rstrip('\r')
                    except Exception:
                        # 둘 다 실패하면 replace로 처리
                        line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                
                if line:  # 빈 줄은 제외
                    log(f"  {line}")
        
        # 남은 버퍼 처리
        if buffer:
            try:
                line = buffer.decode('utf-8', errors='replace').rstrip('\r')
                if line:
                    log(f"  {line}")
            except:
                pass
                
    except Exception as e:
        # subprocess 실행 오류
        log(f"  [subprocess 실행 오류: {e}]")
        raise
    
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"{script_name} 실행이 실패했습니다 (exit code: {process.returncode}).")


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

    # fss_scraper_v2.py 구조에 맞게 필드명 확인
    # 제재내용 필드 확인
    sanction_ok = sum(1 for item in data if has_value(item.get('제재내용', '')))

    def to_pct(count: int) -> str:
        return f"{count} / {total} ({count / total * 100:.1f}%)"

    log("\n[통계] 제재내용 추출 현황")
    log(f" - 제재내용 추출 성공: {to_pct(sanction_ok)}")


def main() -> None:
    # 기본 검색 종료일: 오늘 날짜
    today = datetime.now()
    default_edate = today.strftime('%Y-%m-%d')
    
    parser = argparse.ArgumentParser(description="금감원 제재조치 현황 스크래핑 전체 파이프라인")
    parser.add_argument('--skip-scrape', action='store_true', help='기존 스크래핑 결과를 유지하고 분석 단계만 실행')
    parser.add_argument('--skip-ocr-retry', action='store_true', help='ocr_failed_items.py 실행 생략')
    parser.add_argument('--stats-only', action='store_true', help='통계만 출력 (스크래핑/추출 미실행)')
    parser.add_argument('--log-file', type=str, help='실행 로그를 저장할 파일 경로 (기록은 append 모드)')
    parser.add_argument('--limit', type=int, default=None, help='수집할 최대 항목 수 (기본: 전체)')
    parser.add_argument('--sdate', type=str, default=None, help='검색 시작일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD)')
    parser.add_argument('--edate', type=str, default=default_edate, help=f'검색 종료일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_edate})')
    parser.add_argument('--after', type=str, default=None, help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD)')
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
            scraper_args = []
            if args.limit:
                scraper_args.extend(['--limit', str(args.limit)])
            if args.sdate:
                scraper_args.extend(['--sdate', args.sdate])
            if args.edate:
                scraper_args.extend(['--edate', args.edate])
            if args.after:
                scraper_args.extend(['--after', args.after])
            run_step('fss_scraper_v2.py', '1. 목록 및 PDF 스크래핑', scraper_args if scraper_args else None)
        else:
            log("\n[건너뜀] 스크래핑 단계는 --skip-scrape 옵션으로 생략했습니다.")

        # OCR 후처리 실행 (extract_metadata_ocr.py에서 추출된 제재내용 후처리)
        run_step('post_process_ocr.py', '2. OCR 후처리')

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



