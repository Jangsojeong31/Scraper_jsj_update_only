"""
금융감독원 보도자료 목록에서 첨부파일(HWP, PDF 등)을 모두 추출하고,
보도일을 HWP에서만 추출하는 스크립트 (CSV/Excel/JSON 저장)
"""
import requests
from bs4 import BeautifulSoup
import re
import io
import time
import olefile
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import pandas as pd
import json
from openpyxl.utils import get_column_letter


# -----------------------------------------------------------
# HWP 파일에서 텍스트 추출
# -----------------------------------------------------------
def extract_text_from_hwp_bytes(hwp_bytes):
    """HWP 파일 바이트 데이터를 메모리에서 읽어 텍스트 추출"""
    try:
        with olefile.OleFileIO(io.BytesIO(hwp_bytes)) as ole:
            text_content = ""
            possible_paths = ['PrvText', 'BodyText/Section0', 'Section0', 'DocInfo', 'BodyText']
            for path in possible_paths:
                if ole.exists(path):
                    data = ole.openstream(path).read()
                    try:
                        text = data.decode('utf-16-le', errors='ignore')
                        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
                        text = re.sub(r'\s+', ' ', text)

                        if len(text.strip()) > 10:
                            text_content = text
                            break
                    except Exception:
                        pass
            return text_content

    except Exception as e:
        print(f"    ⚠️ HWP 파일 파싱 오류: {e}")
        return ""


# -----------------------------------------------------------
# 텍스트에서 날짜 추출
# -----------------------------------------------------------
def extract_first_date(text):
    """텍스트에서 가장 처음 나타나는 날짜 추출 (보도일)"""
    if not text:
        return None

    date_patterns = [
        r'(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)',
        r'(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s*\(?[가-힣]*\)?)',
        r'(\d{4}-\d{1,2}-\d{1,2})',
        r'(\d{4}/\d{1,2}/\d{1,2})',
        r'(\d{8})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return None


# -----------------------------------------------------------
# 다음 페이지가 있는지 확인
# -----------------------------------------------------------
def has_next_page(soup, current_page):
    """현재 페이지에서 다음 페이지가 있는지 확인"""
    try:
        # 다음 페이지 버튼 찾기 (텍스트로 찾기)
        next_texts = ['다음', '>', '▶', 'next', 'Next']
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            text = link.get_text(strip=True)
            if any(next_text in text for next_text in next_texts):
                href = link.get("href", "").strip()
                if href and "pageIndex=" in href:
                    return True
        
        # .next 클래스 찾기
        next_links = soup.select(".next, .paging .next, .pagination .next")
        if next_links:
            return True
        
        # 페이지 번호 링크에서 현재 페이지보다 큰 번호 찾기
        pagination_selectors = [
            "div.paging",
            "div.pagination",
            "div.pageArea",
            ".paging",
            ".pagination",
            ".pageArea",
        ]
        
        for selector in pagination_selectors:
            pagination = soup.select_one(selector)
            if pagination:
                page_links = pagination.select("a[href]")
                for link in page_links:
                    text = link.get_text(strip=True)
                    if text.isdigit() and int(text) > current_page:
                        return True
                    
                    href = link.get("href", "").strip()
                    if href and "pageIndex=" in href:
                        match = re.search(r'pageIndex=(\d+)', href)
                        if match:
                            page_num = int(match.group(1))
                            if page_num > current_page:
                                return True
        
        # 전체 링크에서 다음 페이지 찾기
        for link in all_links:
            href = link.get("href", "").strip()
            if href and "pageIndex=" in href:
                match = re.search(r'pageIndex=(\d+)', href)
                if match:
                    page_num = int(match.group(1))
                    if page_num > current_page:
                        return True
        
        return False
        
    except Exception as e:
        print(f"    ⚠️ 다음 페이지 확인 실패: {e}")
        return False


# -----------------------------------------------------------
# 단일 페이지에서 보도자료 추출
# -----------------------------------------------------------
def scrape_single_page(session, page_url, page_num, total_pages, start_idx=1):
    """단일 페이지에서 보도자료 데이터를 추출합니다"""
    results = []
    
    try:
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', class_='board_list') or soup.find('table')

        if not table:
            print(f"    ⚠️ 페이지 {page_num}: 테이블을 찾을 수 없습니다.")
            return results

        rows = table.find_all('tr')[1:]
        if not rows:
            print(f"    ⚠️ 페이지 {page_num}: 데이터가 없습니다.")
            return results

        if total_pages > 0:
            print(f"\n📄 페이지 {page_num}/{total_pages} 처리 중... ({len(rows)}개 항목)")
        else:
            print(f"\n📄 페이지 {page_num} 처리 중... ({len(rows)}개 항목)")

        # 각 보도자료 행 반복 처리
        for row_idx, row in enumerate(rows, start=start_idx):
            title_link = row.find('a', href=re.compile(r'view\.do'))
            if not title_link:
                continue

            # 제목, 상세 URL
            title = title_link.get_text(strip=True)
            detail_url = urljoin(page_url, title_link['href'])

            # 담당부서
            tds = row.find_all('td')
            department = tds[2].get_text(strip=True) if len(tds) >= 3 else None

            # 첨부파일 (.hwp, .pdf, 등)
            file_links = []
            attach_links = row.find_all('a', href=re.compile(r'fileDown\.do'))

            for link in attach_links:
                href = urljoin(page_url, link['href'])
                file_name = link.get_text(strip=True)

                file_links.append({
                    '첨부파일명': file_name,
                    '첨부파일 url': href
                })

            print(f"  [{row_idx}] {title}")
            if not file_links:
                print("      ⚠️ 첨부파일 없음")

            # 상세 본문 가져오기
            try:
                detail_response = session.get(detail_url, timeout=30)
                detail_response.raise_for_status()
                detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                content_div = detail_soup.find('div', class_='dbdata')
                content = content_div.get_text(separator='\n', strip=True) if content_div else ''
                content = re.sub(r'\n+', '\n', content.strip())
            except Exception as e:
                print(f"      ⚠️ 상세페이지 크롤링 실패: {e}")
                content = ''

            # HWP 파일을 통한 보도일 추출
            date = None
            text_preview = None

            hwp_files = [f for f in file_links if f['첨부파일명'].lower().endswith('.hwp')]

            for f in hwp_files:
                try:
                    print(f"      📂 HWP 다운로드 중: {f['첨부파일명']}")
                    file_response = session.get(f['첨부파일 url'], timeout=30)
                    file_response.raise_for_status()

                    text = extract_text_from_hwp_bytes(file_response.content)
                    if text:
                        date = extract_first_date(text)
                        text_preview = text[:200]
                        print(f"      📅 보도일: {date or '추출 실패'}")
                        break

                except Exception as e:
                    print(f"      ⚠️ HWP 처리 실패 ({f['첨부파일명']}): {e}")

            # 결과 저장
            results.append({
                '번호': row_idx,
                '제목': title,
                '담당부서': department,
                '보도일': date,
                '첨부파일': file_links,
                '첨부파일내용 미리보기': text_preview,
                '상세페이지URL': detail_url,
                '내용': content
            })

            time.sleep(0.5)

    except Exception as e:
        print(f"    ❌ 페이지 {page_num} 처리 오류: {e}")

    return results


# -----------------------------------------------------------
# 기존 데이터 로드
# -----------------------------------------------------------
def load_existing_data(json_file="results.json"):
    """기존에 저장된 데이터를 로드합니다"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"📂 기존 데이터 로드: {len(data)}건 발견")
            return data
    except FileNotFoundError:
        print("📂 기존 데이터 없음 (처음부터 시작)")
        return []
    except Exception as e:
        print(f"⚠️ 기존 데이터 로드 실패: {e} (처음부터 시작)")
        return []


# -----------------------------------------------------------
# 보도자료 목록 스크래핑 (모든 페이지)
# -----------------------------------------------------------
def scrape_press_releases(base_url, total_pages=2010, resume=True):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    results = []
    print("📢 보도자료 목록 처리 중...\n")
    print(f"📊 총 예상 페이지 수: {total_pages}페이지\n")

    try:
        # 기존 데이터 로드
        all_results = []
        item_counter = 1
        start_page = 1
        
        if resume:
            existing_data = load_existing_data("results.json")
            if existing_data:
                all_results = existing_data
                item_counter = len(existing_data) + 1
                # 페이지당 약 10건 가정하여 시작 페이지 계산
                # 정확한 계산을 위해 마지막 항목의 상세페이지URL에서 pageIndex 추출 시도
                last_item = existing_data[-1]
                last_url = last_item.get('상세페이지URL', '')
                if 'pageIndex=' in last_url:
                    match = re.search(r'pageIndex=(\d+)', last_url)
                    if match:
                        start_page = int(match.group(1)) + 1  # 다음 페이지부터 시작
                else:
                    # URL에서 추출 실패 시 항목 수로 계산 (페이지당 10건 가정)
                    start_page = (len(existing_data) // 10) + 1
                
                print(f"🔄 이어서 진행: {len(existing_data)}건 저장됨, 페이지 {start_page}부터 시작\n")
                import sys
                sys.stdout.flush()
        
        # URL에서 기본 파라미터 추출
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query)
        
        page_num = start_page
        save_interval = 50  # 50페이지마다 중간 저장
        
        start_time = time.time()
        
        while page_num <= total_pages:
            # 페이지 URL 생성
            params['pageIndex'] = [str(page_num)]
            new_query = urlencode(params, doseq=True)
            page_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
            
            # 페이지 가져오기
            try:
                response = session.get(page_url, timeout=30)
                response.raise_for_status()
                response.encoding = 'utf-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 테이블 확인
                table = soup.find('table', class_='board_list') or soup.find('table')
                if not table:
                    print(f"  ⚠️ 페이지 {page_num}: 테이블을 찾을 수 없습니다. 종료합니다.")
                    break
                
                rows = table.find_all('tr')[1:]
                if not rows:
                    print(f"  ⚠️ 페이지 {page_num}: 데이터가 없습니다. 종료합니다.")
                    break
                
                # 단일 페이지 스크래핑
                page_results = scrape_single_page(session, page_url, page_num, total_pages, start_idx=item_counter)
                
                if not page_results:
                    print(f"  ⚠️ 페이지 {page_num}: 추출된 데이터가 없습니다. 종료합니다.")
                    break
                
                # 번호 업데이트
                for result in page_results:
                    result['번호'] = item_counter
                    item_counter += 1
                
                all_results.extend(page_results)
                
                # 진행률 계산
                progress = (page_num / total_pages) * 100
                elapsed_time = time.time() - start_time
                avg_time_per_page = elapsed_time / page_num if page_num > 0 else 0
                remaining_pages = total_pages - page_num
                estimated_remaining_time = avg_time_per_page * remaining_pages
                
                # 시간 포맷팅
                def format_time(seconds):
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    if hours > 0:
                        return f"{hours}시간 {minutes}분 {secs}초"
                    elif minutes > 0:
                        return f"{minutes}분 {secs}초"
                    else:
                        return f"{secs}초"
                
                print(f"  ✅ 페이지 {page_num}/{total_pages} 완료 ({progress:.1f}%) | "
                      f"추출: {len(page_results)}개 | 누적: {len(all_results)}개 | "
                      f"경과: {format_time(elapsed_time)} | 예상 남은 시간: {format_time(estimated_remaining_time)}")
                import sys
                sys.stdout.flush()  # 실시간 출력을 위해 버퍼 플러시
                
                # 중간 저장 (주기적으로)
                if page_num % save_interval == 0:
                    print(f"\n  💾 중간 저장 중... (페이지 {page_num})")
                    save_results(all_results, 
                               csv_file="results.csv", 
                               excel_file="results.xlsx", 
                               json_file="results.json")
                    print(f"  ✅ 중간 저장 완료\n")
                
                # 다음 페이지 확인 (안전장치)
                if page_num < total_pages and not has_next_page(soup, page_num):
                    print(f"\n  ⚠️ 다음 페이지를 찾을 수 없지만, 아직 {total_pages - page_num}페이지가 남았습니다.")
                    print(f"  계속 진행합니다...\n")
                
                page_num += 1
                
                # 페이지 간 대기
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ 페이지 {page_num} 처리 오류: {e}")
                # 오류 발생 시 중간 저장
                if all_results:
                    print(f"\n  💾 오류 발생으로 중간 저장 중...")
                    save_results(all_results, 
                               csv_file="results.csv", 
                               excel_file="results.xlsx", 
                               json_file="results.json")
                # 연속 오류가 발생하면 종료
                break
        
        results = all_results
        total_time = time.time() - start_time
        print(f"\n📊 총 {page_num}페이지 처리 완료 (소요 시간: {format_time(total_time)})")

    except Exception as e:
        print(f"❌ 처리 오류: {e}")
        # 오류 발생 시에도 중간 저장
        if 'all_results' in locals() and all_results:
            print(f"\n  💾 오류 발생으로 중간 저장 중...")
            save_results(all_results, 
                       csv_file="results.csv", 
                       excel_file="results.xlsx", 
                       json_file="results.json")

    return results


# -----------------------------------------------------------
# CSV / Excel / JSON 저장 함수
# -----------------------------------------------------------
def save_results(results, csv_file="results.csv", excel_file="results.xlsx", json_file="results.json"):
    if not results:
        print("❌ 저장할 결과가 없습니다.")
        return

    df = pd.DataFrame(results)

    # 첨부파일 리스트 → 문자열 변환
    df['첨부파일'] = df['첨부파일'].apply(
        lambda lst: ', '.join([f"{f['첨부파일명']} ({f['첨부파일 url']})" for f in lst]) if lst else ''
    )

    df.fillna('', inplace=True)

    # 컬럼 순서 정렬
    df = df[['번호', '제목', '보도일', '상세페이지URL', '첨부파일', '담당부서', '내용']]

    # CSV 저장
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"📄 CSV 저장 완료: {csv_file}")

    # Excel 저장
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='보도자료')
        ws = writer.sheets['보도자료']

        # 열 너비 자동 조정
        for i, col in enumerate(df.columns, start=1):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(max_len, 50)

    print(f"📘 Excel 저장 완료: {excel_file}")

    # JSON 저장
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"🧾 JSON 저장 완료: {json_file}")


# -----------------------------------------------------------
# 실행 메인
# -----------------------------------------------------------
def main():
    import sys
    # 출력 버퍼링 비활성화 (실시간 출력을 위해)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    
    base_url = "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218&pageIndex=1"
    total_pages = 2010  # 총 페이지 수
    print("금융감독원 보도자료 스크래핑 시작")
    print("=" * 70)
    sys.stdout.flush()

    results = scrape_press_releases(base_url, total_pages=total_pages)

    print("=" * 70)
    print(f"총 {len(results)}개 보도자료 처리 완료")

    success = sum(1 for r in results if r['보도일'])
    if results:
        print(f"보도일 추출 성공률: {success}/{len(results)} ({success/len(results)*100:.1f}%)")

    save_results(results)


if __name__ == "__main__":
    main()
