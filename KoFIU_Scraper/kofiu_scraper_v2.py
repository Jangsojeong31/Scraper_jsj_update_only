"""
금융정보분석원(KoFIU) 제재공시 스크래퍼 v2
- common/file_extractor.py의 FileExtractor를 사용하여 PDF 추출
"""
import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
import argparse
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from pathlib import Path
import sys

# common 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.file_extractor import FileExtractor
from extract_metadata import extract_metadata_from_content, extract_sanction_details, extract_incidents

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

sys.stdout.reconfigure(encoding='utf-8')


class KoFIUScraperV2:
    """금융정보분석원 제재공시 스크래퍼 (FileExtractor 사용)"""
    
    def __init__(self):
        self.base_url = "https://www.kofiu.go.kr"
        self.list_url = "https://www.kofiu.go.kr/kor/notification/sanctions.do"
        
        # requests 세션 설정
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        
        # FileExtractor 초기화
        self.temp_dir = Path("temp_downloads")
        self.temp_dir.mkdir(exist_ok=True)
        self.file_extractor = FileExtractor(
            download_dir=str(self.temp_dir),
            session=self.session
        )
        
        self.results = []
        self.driver = None
        
        if SELENIUM_AVAILABLE:
            self._init_selenium()
    
    def _init_selenium(self):
        """Selenium 드라이버 초기화"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ko-KR')
            self.driver = webdriver.Chrome(options=chrome_options)
            print("  ✓ Selenium 드라이버 초기화 완료")
        except Exception as e:
            print(f"  ※ Selenium 초기화 실패: {e}")
            self.driver = None
    
    def close(self):
        """리소스 정리"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except:
                pass
        
        # 임시 파일 정리
        try:
            for file in self.temp_dir.iterdir():
                file.unlink()
            self.temp_dir.rmdir()
            print("\n임시 파일 정리 완료")
        except Exception:
            pass
    
    def __del__(self):
        """소멸자에서 드라이버 종료"""
        self.close()

    def get_page(self, url, retry=3):
        """HTTP GET 요청 (재시도 로직 포함)"""
        for i in range(retry):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
                return response
            except Exception as e:
                print(f"페이지 로드 실패 (시도 {i+1}/{retry}): {e}")
                if i < retry - 1:
                    time.sleep(2)
                else:
                    raise
        return None

    def is_pdf_url(self, url: str) -> bool:
        """URL이 PDF 파일인지 확인"""
        if not url:
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()
        return path.endswith('.pdf') or '.pdf' in query

    def derive_filename(self, url: str, link_text: str = "") -> str:
        """URL과 링크 텍스트에서 파일명 추출"""
        candidates = []
        if link_text and len(link_text.strip()) > 3:
            candidates.append(link_text.strip())

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if 'file' in query and query['file']:
            candidates.append(query['file'][0])

        path_name = parsed.path.split('/')[-1]
        if path_name:
            candidates.append(path_name)

        for candidate in candidates:
            name = unquote(candidate).strip()
            if not name:
                continue
            name = name.replace('/', '_').replace('\\', '_').replace(':', '_')
            if not name.lower().endswith('.pdf'):
                name += '.pdf'
            return name

        return f"attachment_{int(time.time()*1000)}.pdf"

    def extract_attachment_content(self, detail_url, link_text=''):
        """
        첨부파일 내용 추출 (FileExtractor 사용)
        
        Returns:
            tuple: (추출된 내용, 문서유형)
        """
        try:
            # PDF URL인 경우 직접 다운로드
            if self.is_pdf_url(detail_url):
                filename = self.derive_filename(detail_url, link_text)
                print(f"  PDF 다운로드 시도: {filename}")
                
                # FileExtractor로 파일 다운로드
                file_path, actual_filename = self.file_extractor.download_file(
                    url=detail_url,
                    filename=filename,
                    referer=self.list_url
                )
                
                if file_path and os.path.exists(file_path):
                    # FileExtractor로 PDF 내용 추출
                    content = self.file_extractor.extract_pdf_content(file_path)
                    
                    # 임시 파일 삭제
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    
                    if content and content.strip():
                        print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                        return content, 'PDF-텍스트'
                    else:
                        return "[PDF 파일이지만 텍스트 추출 실패]", 'PDF-OCR필요'
                else:
                    return "[파일 다운로드 실패]", '오류'
            
            # 일반 페이지에서 첨부파일 링크 찾기
            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)

            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                link_text_inner = link.get_text(strip=True)

                if '/download' in href.lower() or 'download' in href.lower() or '.pdf' in href.lower():
                    if href.startswith('/'):
                        file_url = urljoin(self.base_url, href)
                    elif href.startswith('http'):
                        file_url = href
                    else:
                        file_url = urljoin(detail_url, href)

                    filename = link_text_inner.strip()
                    if not filename or len(filename) < 3:
                        if 'file=' in href:
                            filename = unquote(href.split('file=')[-1].split('&')[0])
                        else:
                            filename = href.split('/')[-1].split('?')[0]

                    if not filename.lower().endswith('.pdf'):
                        continue

                    print(f"  첨부파일 발견: {filename}")

                    # FileExtractor로 파일 다운로드
                    file_path, actual_filename = self.file_extractor.download_file(
                        url=file_url,
                        filename=filename,
                        referer=detail_url
                    )
                    
                    if file_path and os.path.exists(file_path):
                        if file_path.lower().endswith('.pdf'):
                            content = self.file_extractor.extract_pdf_content(file_path)
                            
                            # 임시 파일 삭제
                            try:
                                os.remove(file_path)
                            except:
                                pass
                            
                            if content and content.strip():
                                print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                                return content, 'PDF-텍스트'
                            else:
                                return f"[PDF 파일이지만 텍스트 추출 실패: {filename}]", 'PDF-OCR필요'
                        else:
                            # 임시 파일 삭제
                            try:
                                os.remove(file_path)
                            except:
                                pass
                            return f"[{os.path.splitext(file_path)[1]} 파일은 현재 지원되지 않습니다: {filename}]", '기타첨부파일'
                    break

            return "[첨부파일을 찾을 수 없습니다]", '첨부없음'

        except Exception as e:
            print(f"  첨부파일 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return f"[오류: {str(e)}]", '오류'

    def scrape_list_page(self, page_index):
        """목록 페이지 스크래핑 (Selenium 사용)"""
        print(f"\n페이지 {page_index} 스크래핑 중...")
        
        if not SELENIUM_AVAILABLE or not self.driver:
            print("  ※ Selenium을 사용할 수 없어 스크래핑을 건너뜁니다.")
            return []
        
        try:
            # 첫 페이지는 URL로 이동, 이후는 JavaScript 함수 사용
            if page_index == 1:
                url = self.list_url
                self.driver.get(url)
                time.sleep(3)
            else:
                self.driver.execute_script(f"goPaging_PagingView('{page_index}');")
                time.sleep(3)
            
            # bo_list 요소 찾기
            try:
                bo_list = self.driver.find_element(By.CLASS_NAME, 'bo_list')
            except:
                print(f"  페이지 {page_index}: bo_list를 찾을 수 없습니다")
                return []
            
            # BeautifulSoup으로 파싱
            soup = BeautifulSoup(self.driver.page_source, 'lxml')
            bo_list_div = soup.find('div', class_='bo_list')
            
            if not bo_list_div:
                print(f"  페이지 {page_index}: bo_list div를 찾을 수 없습니다")
                return []
            
            # ul > li.bo_li 구조 파싱
            items = []
            li_items = bo_list_div.find_all('li', class_='bo_li')
            
            for li in li_items:
                try:
                    # 제목 (로그용)
                    subject_p = li.find('p', class_='li_subject')
                    title_link = subject_p.find('a') if subject_p else None
                    title = title_link.get_text(strip=True) if title_link else ""
                    
                    # 날짜 추출 (첫 번째 li_date가 게시일)
                    date_spans = li.find_all('span', class_='li_date')
                    post_date = ""
                    if date_spans:
                        post_date = date_spans[0].get_text(strip=True)
                    
                    # 첨부파일 링크 찾기
                    hidden_file_div = li.find('div', class_='hidden_file_g')
                    pdf_url = None
                    pdf_filename = None
                    if hidden_file_div:
                        file_list = hidden_file_div.find('ul', class_='file_list')
                        if file_list:
                            pdf_link = file_list.find('a', class_='pdf')
                            if pdf_link:
                                href = pdf_link.get('href', '')
                                if href.startswith('/'):
                                    pdf_url = urljoin(self.base_url, href)
                                elif href.startswith('http'):
                                    pdf_url = href
                                else:
                                    pdf_url = urljoin(self.base_url, '/' + href.lstrip('/'))
                                pdf_filename = pdf_link.get_text(strip=True)
                    
                    items.append({
                        '상세페이지URL': pdf_url,
                        '_pdf_filename': pdf_filename,
                        '_link_text': title,
                        '_post_date': post_date
                    })
                    
                except Exception as e:
                    print(f"  항목 처리 중 오류: {e}")
                    continue
            
            print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
            return items
            
        except Exception as e:
            print(f"  페이지 {page_index} 스크래핑 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def parse_date(self, date_str):
        """
        날짜 문자열을 datetime 객체로 변환
        지원 형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
        """
        if not date_str:
            return None
        
        # 다양한 날짜 형식 지원
        date_formats = ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d']
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def scrape_all(self, limit=None, after_date=None):
        """
        전체 페이지 스크래핑
        
        Args:
            limit: 수집할 최대 항목 수 (None이면 전체 수집)
            after_date: 이 날짜 이후 항목만 수집 (YYYY-MM-DD 또는 YYYY.MM.DD 형식)
        """
        print("=" * 60)
        print("금융정보분석원 제재공시 스크래핑 시작 (v2 - FileExtractor 사용)")
        if limit:
            print(f"  수집 제한: {limit}개")
        if after_date:
            print(f"  날짜 필터: {after_date} 이후")
        print("=" * 60)
        
        # after_date 문자열을 datetime으로 변환
        after_datetime = self.parse_date(after_date) if after_date else None
        
        if not SELENIUM_AVAILABLE:
            print("  ※ Selenium이 설치되어 있지 않아 스크래핑을 수행할 수 없습니다.")
            print("     pip install selenium 을 실행하여 설치해주세요.")
            return []

        all_items = []
        seen_urls = set()
        page = 1
        empty_pages = 0
        stop_by_date = False  # 날짜 기준 종료 플래그

        while True:
            # limit에 도달하면 목록 수집 중단
            if limit and len(all_items) >= limit:
                print(f"\n목록 수집 제한({limit}개)에 도달하여 수집을 종료합니다.")
                break
            
            # 날짜 기준 종료
            if stop_by_date:
                print(f"\n날짜 기준({after_date} 이후)에 해당하는 항목이 더 이상 없어 수집을 종료합니다.")
                break
            
            items = self.scrape_list_page(page)
            if not items:
                empty_pages += 1
                if empty_pages >= 2:
                    print(f"\n페이지 {page}에서 더 이상 항목이 없어 수집을 종료합니다.")
                    break
            else:
                empty_pages = 0

            new_items = []
            for item in items:
                # limit 체크
                if limit and len(all_items) + len(new_items) >= limit:
                    break
                
                # 날짜 필터링
                if after_datetime:
                    post_date_str = item.get('_post_date', '')
                    post_datetime = self.parse_date(post_date_str)
                    
                    if post_datetime:
                        if post_datetime < after_datetime:
                            # 날짜순 정렬이므로, 이 날짜보다 이전이면 더 이상 수집 불필요
                            print(f"  날짜 {post_date_str}가 기준일({after_date}) 이전이므로 건너뜀")
                            stop_by_date = True
                            break
                    
                pdf_url = item.get('상세페이지URL')
                if pdf_url and pdf_url in seen_urls:
                    continue
                if pdf_url:
                    seen_urls.add(pdf_url)
                new_items.append(item)

            if new_items:
                all_items.extend(new_items)
            
            if not items:
                break
            
            # 페이지네이션 확인
            try:
                total_pages = 10
                try:
                    page_info = self.driver.find_element(By.XPATH, "//div[@class='paging']//div[contains(text(), '/')]")
                    page_text = page_info.text.strip()
                    match = re.search(r'/\s*(\d+)', page_text)
                    if match:
                        total_pages = int(match.group(1))
                        print(f"  총 페이지 수: {total_pages}")
                except:
                    pass
                
                if page >= total_pages:
                    print(f"\n모든 페이지 수집 완료 (총 {total_pages}페이지)")
                    break
                    
            except Exception as e:
                print(f"  페이지네이션 확인 중 오류: {e}")
                if page > 1:
                    break
            
            time.sleep(1)
            page += 1
            
            if page > 100:
                print(f"\n최대 페이지 수(100)에 도달하여 수집을 종료합니다.")
                break

        print(f"\n총 {len(all_items)}개 항목 수집 완료")

        print("\n상세 정보 및 첨부파일 추출 시작...")
        
        for idx, item in enumerate(all_items, 1):
            link_text = item.pop('_link_text', '')
            pdf_filename = item.pop('_pdf_filename', '')
            
            print(f"\n[{idx}/{len(all_items)}] {pdf_filename or link_text or 'N/A'} 처리 중...")
            
            if item.get('상세페이지URL'):
                attachment_content, doc_type = self.extract_attachment_content(
                    item['상세페이지URL'], 
                    pdf_filename or link_text
                )
                item['제재조치내용'] = attachment_content
                
                # PDF 내용에서 제재대상기관, 제재조치요구일, 제재내용 추출
                if attachment_content and not attachment_content.startswith('['):
                    institution, sanction_date = extract_metadata_from_content(attachment_content)
                    if institution:
                        item['제재대상기관'] = institution
                        print(f"  제재대상기관 추출: {institution}")
                    if sanction_date:
                        item['제재조치요구일'] = sanction_date
                        print(f"  제재조치요구일 추출: {sanction_date}")
                    
                    # 제재내용 (표 데이터) 추출
                    sanction_details = extract_sanction_details(attachment_content)
                    if sanction_details:
                        item['제재내용'] = sanction_details
                        print(f"  제재내용 추출: {len(sanction_details)}자")
                    
                    # 사건 제목/내용 추출 (4번 항목)
                    incidents = extract_incidents(attachment_content)
                    if incidents:
                        item.update(incidents)
                        incident_count = len([k for k in incidents.keys() if k.startswith('사건제목')])
                        print(f"  사건 추출: {incident_count}건")
            else:
                item['제재조치내용'] = "[첨부파일 URL이 없습니다]"

            self.results.append(item)
            time.sleep(1)

        # 리소스 정리
        self.close()

        return self.results

    def save_results(self, filename='kofiu_results_v2.json'):
        """결과 저장 (JSON, CSV) - output 폴더에 저장"""
        # output 폴더 생성
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # 파일명만 추출 (경로가 포함된 경우)
        base_filename = os.path.basename(filename)
        json_filepath = os.path.join(output_dir, base_filename)
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {json_filepath}에 저장되었습니다. (총 {len(self.results)}개)")

        try:
            import csv
            csv_filename = base_filename.replace('.json', '.csv')
            csv_filepath = os.path.join(output_dir, csv_filename)
            
            if self.results:
                # 기본 필드
                base_fieldnames = ['제재대상기관', '제재조치요구일', '제재내용']
                
                # 사건 관련 필드 동적 추가 (최대 사건 수 찾기)
                max_incidents = 0
                for item in self.results:
                    incident_count = len([k for k in item.keys() if k.startswith('사건제목')])
                    if incident_count > max_incidents:
                        max_incidents = incident_count
                
                # 사건제목1, 사건내용1, 사건제목2, 사건내용2... 순서로 추가
                incident_fieldnames = []
                for i in range(1, max_incidents + 1):
                    incident_fieldnames.append(f'사건제목{i}')
                    incident_fieldnames.append(f'사건내용{i}')
                
                # 마지막에 URL과 전체 내용 추가
                fieldnames = base_fieldnames + incident_fieldnames + ['상세페이지URL', '제재조치내용']

                with open(csv_filepath, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()

                    for item in self.results:
                        row = {}
                        for field in fieldnames:
                            value = item.get(field, '')
                            if value is None:
                                value = ''
                            row[field] = str(value)
                        writer.writerow(row)

                print(f"CSV 파일도 {csv_filepath}에 저장되었습니다.")
                if max_incidents > 0:
                    print(f"  (사건 컬럼: 최대 {max_incidents}건)")
        except Exception as e:
            print(f"CSV 저장 중 오류 (무시): {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='금융정보분석원(KoFIU) 제재공시 스크래퍼')
    parser.add_argument('--limit', type=int, default=None,
                        help='수집할 최대 항목 수 (기본값: 전체 수집)')
    parser.add_argument('--after', type=str, default='2024.03.30',
                        help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD 또는 YYYY.MM.DD, 기본값: 2024.03.30)')
    parser.add_argument('--output', type=str, default='kofiu_results_v2.json',
                        help='출력 파일명 (기본값: kofiu_results_v2.json)')
    
    args = parser.parse_args()
    
    scraper = KoFIUScraperV2()
    results = scraper.scrape_all(limit=args.limit, after_date=args.after)
    scraper.save_results(filename=args.output)

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

