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
import csv
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
        
        # 업종 분류 매핑 로드
        self.industry_map = self._load_industry_classification()
        
        if SELENIUM_AVAILABLE:
            self._init_selenium()
    
    def _load_industry_classification(self):
        """금융회사별 업종분류 CSV 파일 로드"""
        industry_map = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, '금융회사별_업종분류.csv')
        
        try:
            # utf-8-sig 인코딩 사용하여 BOM 자동 처리
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    company_name = row.get('금융회사명', '').strip()
                    industry = row.get('업종', '').strip()
                    if company_name and industry:
                        industry_map[company_name] = industry
            print(f"  ✓ 업종분류 데이터 로드 완료: {len(industry_map)}개 회사")
        except FileNotFoundError:
            print(f"  ※ 업종분류 파일을 찾을 수 없습니다: {csv_path}")
        except Exception as e:
            print(f"  ※ 업종분류 파일 로드 중 오류: {e}")
        
        return industry_map
    
    def get_industry(self, institution_name):
        """
        금융회사명으로 업종 조회
        - 정확한 매칭 우선
        - 부분 매칭 시도 (회사명에 포함되어 있는 경우)
        - 매칭되지 않으면 '기타' 반환
        """
        if not institution_name:
            return '기타'
        
        # 정확한 매칭
        clean_name = institution_name.strip()
        if clean_name in self.industry_map:
            return self.industry_map[clean_name]
        
        # 특수문자 제거 후 매칭 (예: * 제거)
        clean_name_no_special = re.sub(r'[*\s]', '', clean_name)
        for company, industry in self.industry_map.items():
            company_clean = re.sub(r'[*\s]', '', company)
            if clean_name_no_special == company_clean:
                return industry
        
        # 부분 매칭 시도 (금융회사명이 매핑 테이블의 회사명에 포함되거나 그 반대)
        for company, industry in self.industry_map.items():
            # 금융회사명이 회사명을 포함하는 경우
            if company in clean_name:
                return industry
            # 회사명이 금융회사명을 포함하는 경우
            if clean_name in company:
                return industry
        
        return '기타'
    
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
            item.pop('_post_date', None)  # 임시 필드 제거
            
            print(f"\n[{idx}/{len(all_items)}] {pdf_filename or link_text or 'N/A'} 처리 중...")
            
            if item.get('상세페이지URL'):
                attachment_content, doc_type = self.extract_attachment_content(
                    item['상세페이지URL'], 
                    pdf_filename or link_text
                )
                item['제재조치내용'] = attachment_content
                
                # PDF 내용에서 금융회사명, 제재조치일, 제재내용 추출
                if attachment_content and not attachment_content.startswith('['):
                    institution, sanction_date = extract_metadata_from_content(attachment_content)
                    if institution:
                        item['금융회사명'] = institution
                        # 업종 매핑
                        industry = self.get_industry(institution)
                        item['업종'] = industry
                        print(f"  금융회사명 추출: {institution} (업종: {industry})")
                    else:
                        item['업종'] = '기타'
                    if sanction_date:
                        item['제재조치일'] = sanction_date
                        print(f"  제재조치일 추출: {sanction_date}")
                    
                    # 제재내용 (표 데이터) 추출
                    sanction_details = extract_sanction_details(attachment_content)
                    if sanction_details:
                        item['제재내용'] = sanction_details
                        print(f"  제재내용 추출: {len(sanction_details)}자")
                    
                    # 사건 제목/내용 추출 (4번 항목)
                    incidents = extract_incidents(attachment_content)
                    if incidents:
                        item.update(incidents)
                        incident_count = len([k for k in incidents.keys() if k.startswith('제목')])
                        print(f"  사건 추출: {incident_count}건")
            else:
                item['제재조치내용'] = "[첨부파일 URL이 없습니다]"
                item['업종'] = '기타'
            
            # 업종 필드가 없는 경우 기타로 설정
            if '업종' not in item:
                item['업종'] = '기타'

            self.results.append(item)
            time.sleep(1)

        # 리소스 정리
        self.close()

        return self.results

    def _extract_related_laws(self, text):
        """
        텍스트에서 관련법규 추출
        - ｢ ｣ 및 「 」 괄호 안의 법률명 + 조항 추출
        - 각 법률별로 줄바꿈으로 구분
        """
        if not text:
            return ""
        
        # 전처리: 괄호 통일 (「」 -> ｢｣, 혼합 괄호 처리)
        normalized_text = text
        normalized_text = normalized_text.replace('「', '｢').replace('」', '｣')
        
        # 줄바꿈을 공백으로 대체하여 법률명이 분리되지 않도록 처리
        normalized_text = re.sub(r'\s*\n\s*', ' ', normalized_text)
        
        # 연속 공백 정리
        normalized_text = re.sub(r'\s+', ' ', normalized_text)
        
        laws = []
        
        # ｢법률명｣ 제X조... 패턴 추출
        # 법률명과 조항을 함께 추출
        pattern = r'｢([^｣]+)｣\s*(제[\d조의\s,제항호]+(?:등)?)'
        matches = re.findall(pattern, normalized_text)
        
        for law_name, articles in matches:
            # 법률명 정리 (앞뒤 공백 제거, 연속 공백 정리)
            law_name = re.sub(r'\s+', ' ', law_name.strip())
            articles = articles.strip()
            
            # 조항 정리 (연속 공백 제거)
            articles = re.sub(r'\s+', '', articles)
            
            law_entry = f"｢{law_name}｣ {articles}"
            if law_entry not in laws:
                laws.append(law_entry)
        
        # 동법 시행령 패턴도 추출
        sihaengryung_pattern = r'동법\s*시행령\s*(제[\d조의\s,제항호]+(?:등)?)'
        sihaengryung_matches = re.findall(sihaengryung_pattern, normalized_text)
        
        for articles in sihaengryung_matches:
            articles = re.sub(r'\s+', '', articles.strip())
            law_entry = f"동법 시행령 {articles}"
            if law_entry not in laws:
                laws.append(law_entry)
        
        # 각 법률을 줄바꿈으로 구분
        return '\n'.join(laws)

    def _remove_law_section(self, text):
        """
        텍스트에서 <관련법규> 또는 <관련규정> 섹션 이후 내용 제거
        """
        if not text:
            return text
        
        # <관련법규> 또는 <관련규정> 패턴 찾기
        pattern = r'\s*<\s*관련(?:법규|규정)\s*>.*$'
        result = re.sub(pattern, '', text, flags=re.DOTALL)
        
        return result.strip()

    def _clean_content(self, text):
        """
        텍스트에서 불필요한 줄바꿈 제거
        - 특수 마커(ㅇ, □, -, (1) 등) 앞의 줄바꿈은 유지
        - 그 외 줄바꿈은 공백으로 대체
        - <관련법규>/<관련규정> 이후 내용 제거
        """
        if not text:
            return text
        
        # 먼저 <관련법규>/<관련규정> 섹션 제거
        text = self._remove_law_section(text)
        
        # 유지해야 할 마커 패턴 (줄바꿈 + 마커)
        # 이 패턴들 앞의 줄바꿈은 유지
        preserve_patterns = [
            (r'\n\s*ㅇ\s*', '\n○ '),      # ㅇ 마커
            (r'\n\s*○\s*', '\n○ '),      # ○ 마커
            (r'\n\s*□\s*', '\n□ '),       # □ 마커
            (r'\n\s*-\s*', '\n- '),        # - 마커 (줄 시작)
            (r'\n\s*\((\d+)\)\s*', r'\n(\1) '),  # (1), (2) 등
        ]
        
        # 먼저 마커 패턴을 임시 토큰으로 대체
        result = text
        placeholders = {}
        for i, (pattern, replacement) in enumerate(preserve_patterns):
            placeholder = f'__MARKER_{i}__'
            # 패턴을 찾아서 placeholder로 대체
            matches = re.findall(pattern, result)
            for match in matches:
                placeholders[placeholder] = replacement
            result = re.sub(pattern, placeholder, result)
        
        # 나머지 줄바꿈을 공백으로 대체
        result = re.sub(r'\n+', ' ', result)
        
        # 임시 토큰을 원래 마커로 복원
        for placeholder, replacement in placeholders.items():
            result = result.replace(placeholder, replacement)
        
        # 연속 공백 정리
        result = re.sub(r' +', ' ', result)
        
        # 앞뒤 공백 제거
        result = result.strip()
        
        return result

    def _split_incidents(self):
        """
        각 제재 건에서 사건들을 분리하여 개별 행으로 변환
        예: 제목1, 내용1, 제목2, 내용2 -> 두 개의 별도 행으로 분리
        """
        split_results = []
        
        for item in self.results:
            # 기본 필드 추출 (줄바꿈 정리 적용)
            base_data = {
                '금융회사명': item.get('금융회사명', ''),
                '업종': item.get('업종', '기타'),
                '제재조치일': item.get('제재조치일', ''),
                '제재내용': self._clean_content(item.get('제재내용', '')),
                '상세페이지URL': item.get('상세페이지URL', '')
            }
            
            # 사건 수 확인
            incident_count = len([k for k in item.keys() if k.startswith('제목')])
            
            if incident_count == 0:
                # 사건이 없는 경우 기본 데이터만 저장
                split_results.append({
                    **base_data,
                    '제목': '',
                    '내용': '',
                    '관련법규': ''
                })
            else:
                # 각 사건을 별도 행으로 분리
                for i in range(1, incident_count + 1):
                    title = item.get(f'제목{i}', '')
                    raw_content = item.get(f'내용{i}', '')
                    
                    # 관련법규 추출 (정리 전 원본에서 추출)
                    related_laws = self._extract_related_laws(raw_content)
                    
                    # 내용 정리 (<관련법규> 섹션 제거 및 줄바꿈 정리)
                    content = self._clean_content(raw_content)
                    
                    split_results.append({
                        **base_data,
                        '제목': title,
                        '내용': content,
                        '관련법규': related_laws
                    })
        
        return split_results

    def save_results(self, filename='kofiu_results_v2.json'):
        """결과 저장 (JSON, CSV) - output 폴더에 저장"""
        # output 폴더 생성
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # 파일명만 추출 (경로가 포함된 경우)
        base_filename = os.path.basename(filename)
        json_filepath = os.path.join(output_dir, base_filename)
        
        # 사건별로 분리된 결과 생성
        split_results = self._split_incidents()
        
        # JSON 저장 (분리된 결과)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(split_results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {json_filepath}에 저장되었습니다.")
        print(f"  (원본: {len(self.results)}개 제재 건 -> 분리 후: {len(split_results)}개 사건)")

        try:
            import csv
            csv_filename = base_filename.replace('.json', '.csv')
            csv_filepath = os.path.join(output_dir, csv_filename)
            
            if split_results:
                # 필드 순서: 업종, 금융회사명, 제목, 내용, 관련법규, 제재내용, 제재조치일, 상세페이지URL
                fieldnames = ['업종', '금융회사명', '제목', '내용', '관련법규', '제재내용', '제재조치일', '상세페이지URL']

                with open(csv_filepath, 'w', encoding='utf-8-sig', newline='') as f:
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

                print(f"CSV 파일도 {csv_filepath}에 저장되었습니다.")
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
    print(f"총 {len(results)}개 제재 건 수집 (사건별로 분리되어 저장됨)")
    print("=" * 60)

