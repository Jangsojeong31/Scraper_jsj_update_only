import argparse
import json
import subprocess
import sys
import os
import io
import re
from pathlib import Path
from datetime import datetime, timedelta


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


def normalize_date_format(date_str: str) -> str:
    """
    날짜 문자열을 YYYY-MM-DD 형식으로 정규화
    
    Args:
        date_str: 다양한 형식의 날짜 문자열 (YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD)
        
    Returns:
        str: YYYY-MM-DD 형식의 날짜 문자열
    """
    if not date_str:
        return date_str
    
    # 숫자만 추출
    numbers = re.findall(r'\d+', date_str)
    if len(numbers) >= 3:
        year = numbers[0]
        month = numbers[1].zfill(2)
        day = numbers[2].zfill(2)
        return f"{year}-{month}-{day}"
    
    return date_str


def parse_date(date_str: str) -> datetime:
    """
    날짜 문자열을 datetime 객체로 변환
    
    Args:
        date_str: YYYY-MM-DD 형식의 날짜 문자열
        
    Returns:
        datetime: 변환된 datetime 객체
    """
    if not date_str:
        return None
    
    normalized = normalize_date_format(date_str)
    try:
        return datetime.strptime(normalized, '%Y-%m-%d')
    except:
        return None


def get_latest_sanction_date(archive_path: Path) -> datetime:
    """
    archive 데이터에서 가장 최근 제재조치일 찾기
    
    Args:
        archive_path: archive JSON 파일 경로
        
    Returns:
        datetime: 가장 최근 제재조치일 (없으면 None)
    """
    if not archive_path.exists():
        return None
    
    try:
        with archive_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            return None
        
        latest_date = None
        for item in data:
            sanction_date_str = item.get('제재조치일', '')
            if sanction_date_str:
                date_obj = parse_date(sanction_date_str)
                if date_obj:
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
        
        return latest_date
    except Exception as e:
        log(f"  ※ archive 데이터 읽기 오류: {e}")
        return None


def is_duplicate(new_item: dict, archive_data: list) -> bool:
    """
    새 항목이 archive 데이터와 중복되는지 확인 (제재조치일 + 금융회사명 기준)
    
    Args:
        new_item: 새로 크롤링한 항목
        archive_data: 기존 archive 데이터
        
    Returns:
        bool: 중복이면 True
    """
    new_sanction_date = new_item.get('제재조치일', '').strip()
    new_company = new_item.get('금융회사명', '').strip()
    
    if not new_sanction_date or not new_company:
        return False
    
    for archive_item in archive_data:
        archive_sanction_date = archive_item.get('제재조치일', '').strip()
        archive_company = archive_item.get('금융회사명', '').strip()
        
        # 제재조치일과 금융회사명이 모두 일치하면 중복
        if new_sanction_date == archive_sanction_date and new_company == archive_company:
            return True
    
    return False


def merge_with_archive(new_data: list, archive_path: Path) -> list:
    """
    새 데이터를 archive 데이터와 병합 (중복 제거)
    
    Args:
        new_data: 새로 크롤링한 데이터
        archive_path: archive JSON 파일 경로
        
    Returns:
        list: 병합된 데이터
    """
    # archive 데이터 로드
    archive_data = []
    if archive_path.exists():
        try:
            with archive_path.open('r', encoding='utf-8') as f:
                archive_data = json.load(f)
        except Exception as e:
            log(f"  ※ archive 데이터 로드 오류: {e}")
            archive_data = []
    
    # 중복 제거하면서 새 데이터 추가
    merged_data = archive_data.copy()
    added_count = 0
    duplicate_count = 0
    
    for new_item in new_data:
        if is_duplicate(new_item, archive_data):
            duplicate_count += 1
        else:
            merged_data.append(new_item)
            added_count += 1
    
    log(f"\n[병합 결과]")
    log(f" - archive 기존 데이터: {len(archive_data)}건")
    log(f" - 새로 크롤링한 데이터: {len(new_data)}건")
    log(f" - 중복 제외: {duplicate_count}건")
    log(f" - 새로 추가: {added_count}건")
    log(f" - 최종 데이터: {len(merged_data)}건")
    
    return merged_data


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
    
    # archive 경로
    archive_path = ROOT_DIR / 'archive' / 'fss_results.json'
    
    parser = argparse.ArgumentParser(description="금감원 제재조치 현황 스크래핑 전체 파이프라인")
    parser.add_argument('--skip-scrape', action='store_true', help='기존 스크래핑 결과를 유지하고 분석 단계만 실행')
    parser.add_argument('--run-ocr-retry', action='store_true', help='ocr_failed_items.py 실행 (기본값: 실행 안 함)')
    parser.add_argument('--skip-ocr-retry', action='store_true', help='ocr_failed_items.py 실행 생략 (deprecated: 기본값이 실행 안 함)')
    parser.add_argument('--stats-only', action='store_true', help='통계만 출력 (스크래핑/추출 미실행)')
    parser.add_argument('--log-file', type=str, help='실행 로그를 저장할 파일 경로 (기록은 append 모드)')
    parser.add_argument('--limit', type=int, default=None, help='수집할 최대 항목 수 (기본: 전체)')
    parser.add_argument('--sdate', type=str, default=None, help='검색 시작일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: archive 기준 자동 계산)')
    parser.add_argument('--edate', type=str, default=None, help=f'검색 종료일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_edate})')
    parser.add_argument('--after', type=str, default=None, help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD)')
    parser.add_argument('--no-merge', action='store_true', help='archive와 병합하지 않고 새 데이터만 저장')
    args = parser.parse_args()

    json_path = ROOT_DIR / 'output' / 'fss_results.json'

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
            # archive에서 가장 최근 제재조치일 찾기
            latest_sanction_date = get_latest_sanction_date(archive_path)
            
            # 크롤링 기간 계산
            if args.sdate:
                # 사용자가 직접 지정한 경우
                sdate = args.sdate
            elif latest_sanction_date:
                # archive 기준: 최근 제재조치일 -3일부터
                start_date = latest_sanction_date - timedelta(days=3)
                sdate = start_date.strftime('%Y-%m-%d')
                log(f"\n[크롤링 기간 설정]")
                log(f" - archive 최근 제재조치일: {latest_sanction_date.strftime('%Y-%m-%d')}")
                log(f" - 크롤링 시작일: {sdate} (최근 제재조치일 -3일)")
            else:
                # archive가 없으면 기본값 사용 (일주일 전)
                sdate = (today - timedelta(days=7)).strftime('%Y-%m-%d')
                log(f"\n[크롤링 기간 설정]")
                log(f" - archive 데이터 없음, 기본값 사용")
                log(f" - 크롤링 시작일: {sdate} (일주일 전)")
            
            edate = args.edate if args.edate else default_edate
            
            scraper_args = []
            if args.limit:
                scraper_args.extend(['--limit', str(args.limit)])
            scraper_args.extend(['--sdate', sdate])
            scraper_args.extend(['--edate', edate])
            if args.after:
                scraper_args.extend(['--after', args.after])
            run_step('fss_scraper_v2.py', '1. 목록 및 PDF 스크래핑', scraper_args if scraper_args else None)
            
            # 새로 크롤링한 데이터와 archive 병합
            if not args.no_merge and json_path.exists():
                log(f"\n[단계] archive 데이터와 병합 중...")
                try:
                    with json_path.open('r', encoding='utf-8') as f:
                        new_data = json.load(f)
                    
                    # archive와 병합
                    merged_data = merge_with_archive(new_data, archive_path)
                    
                    # 병합된 데이터를 archive에 저장
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive_path.open('w', encoding='utf-8') as f:
                        json.dump(merged_data, f, ensure_ascii=False, indent=2)
                    
                    log(f"  ✓ archive 데이터 업데이트 완료: {archive_path}")
                    
                    # output은 새로 크롤링한 데이터만 유지 (스크래퍼가 이미 저장함)
                    log(f"  ✓ output 폴더는 새로 크롤링한 데이터만 유지됩니다")
                    
                    # archive CSV 생성 (병합된 전체 데이터)
                    archive_csv_path = archive_path.parent / archive_path.name.replace('.json', '.csv')
                    
                    try:
                        import csv
                        # 사건별로 분리된 결과 생성 (스크래퍼와 동일한 로직)
                        split_results = []
                        for item in merged_data:
                            # 사건이 여러 개인 경우 각 사건마다 별도의 행으로 확장
                            titles = []
                            contents = []
                            
                            # 제목1, 제목2, ... 찾기
                            for key in sorted(item.keys()):
                                if key.startswith('제목'):
                                    idx = key.replace('제목', '')
                                    title = item.get(key, '').strip()
                                    content = item.get(f'내용{idx}', '').strip()
                                    if title:
                                        titles.append(title)
                                        contents.append(content)
                            
                            if titles:
                                # 사건이 여러 개인 경우
                                for title, content in zip(titles, contents):
                                    split_results.append({
                                        '구분': item.get('구분', '제재사례'),
                                        '출처': item.get('출처', '금융감독원'),
                                        '업종': item.get('업종', '기타'),
                                        '금융회사명': item.get('금융회사명', ''),
                                        '제목': title,
                                        '내용': content,
                                        '제재내용': item.get('제재내용', ''),
                                        '제재조치일': item.get('제재조치일', ''),
                                        '파일다운로드URL': item.get('파일다운로드URL', ''),
                                        'OCR추출여부': item.get('OCR추출여부', '아니오')
                                    })
                            else:
                                # 사건이 없는 경우
                                split_results.append({
                                    '구분': item.get('구분', '제재사례'),
                                    '출처': item.get('출처', '금융감독원'),
                                    '업종': item.get('업종', '기타'),
                                    '금융회사명': item.get('금융회사명', ''),
                                    '제목': '',
                                    '내용': '',
                                    '제재내용': item.get('제재내용', ''),
                                    '제재조치일': item.get('제재조치일', ''),
                                    '파일다운로드URL': item.get('파일다운로드URL', ''),
                                    'OCR추출여부': item.get('OCR추출여부', '아니오')
                                })
                        
                        # archive CSV 저장 (병합된 전체 데이터)
                        fieldnames = ['구분', '출처', '업종', '금융회사명', '제목', '내용', '제재내용', '제재조치일', '파일다운로드URL', 'OCR추출여부']
                        with archive_csv_path.open('w', encoding='utf-8-sig', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                            writer.writeheader()
                            for item in split_results:
                                row = {}
                                for field in fieldnames:
                                    value = item.get(field, '')
                                    if value is None:
                                        value = ''
                                    row[field] = str(value)
                                writer.writerow(row)
                        
                        log(f"  ✓ archive CSV 파일 업데이트 완료: {archive_csv_path}")
                    except Exception as csv_error:
                        log(f"  ※ CSV 생성 중 오류: {csv_error}")
                    
                except Exception as e:
                    log(f"  ※ 병합 중 오류: {e}")
        else:
            log("\n[건너뜀] 스크래핑 단계는 --skip-scrape 옵션으로 생략했습니다.")

        # OCR 후처리 실행 (V3 OCR로 추출된 제재내용 후처리)
        run_step('post_process_ocr.py', '2. OCR 후처리')

        # OCR 실패 항목 재처리 (기본값: 실행 안 함, --run-ocr-retry 옵션으로 실행)
        ocr_retry_script = ROOT_DIR / 'ocr_failed_items.py'
        if args.run_ocr_retry:
            if ocr_retry_script.exists():
                run_step('ocr_failed_items.py', '3. OCR 실패 항목 재처리')
            else:
                log("\n[정보] ocr_failed_items.py 파일이 없어 재처리 단계를 건너뜁니다.")
        elif args.skip_ocr_retry:
            # --skip-ocr-retry 옵션은 하위 호환성을 위해 유지
            log("\n[건너뜀] --skip-ocr-retry 옵션으로 OCR 재처리 단계를 생략했습니다.")
        else:
            # 기본값: 실행 안 함
            log("\n[건너뜀] OCR 재처리 단계는 기본적으로 실행하지 않습니다. (실행하려면 --run-ocr-retry 옵션 사용)")

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



