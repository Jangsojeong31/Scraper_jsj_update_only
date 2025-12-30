# kofiu_scraper_v2.py

"""
금융정보분석원(KoFIU) 제재공시 스크래퍼 v2
- common/file_extractor.py의 FileExtractor를 사용하여 PDF 추출
- OCR 기능 포함 (텍스트 추출 실패 시 폴백)
"""
import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
import argparse
import csv
import io
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from pathlib import Path
import sys

# OCR 라이브러리 import
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    PYTESSERACT_AVAILABLE = False

# common 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.file_extractor import FileExtractor
from KoFIU_Scraper.extract_metadata import extract_metadata_from_content, extract_sanction_details, extract_incidents, format_date_to_iso
from KoFIU_Scraper.ocr_extractor import OCRExtractor
from KoFIU_Scraper.post_process_ocr import process_ocr_text, clean_content_symbols

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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = Path(script_dir) / "output" / "downloads"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.download_dir = str(output_dir)  # 파일 다운로드 디렉토리
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
        
        # OCR 관련 초기화
        self.min_text_length = 200  # 최소 텍스트 길이 (미만이면 OCR 시도)
        self.ocr_extractor = OCRExtractor()  # 하이브리드 OCR 사용
        
        if SELENIUM_AVAILABLE:
            # 기본은 headless로 동작
            self._init_selenium(headless=True)
    
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
        - 법인 형태 정규화 후 매칭
        - 부분 매칭 시도 (최소 3자 이상, 회사명에 포함되어 있는 경우)
        - 매칭되지 않으면 '기타' 반환
        """
        if not institution_name:
            return '기타'
        
        # 정확한 매칭
        clean_name = institution_name.strip()
        if clean_name in self.industry_map:
            return self.industry_map[clean_name]
        
        # 법인 형태 정규화 함수
        def normalize_company_name(name):
            """법인 형태 제거 후 정규화"""
            # (주), ㈜, 주식회사 등 제거
            name = re.sub(r'\(주\)|㈜|주식회사', '', name)
            # 특수문자 및 공백 제거
            name = re.sub(r'[*\s]', '', name)
            return name
        
        # 법인 형태 제거 후 매칭
        clean_name_normalized = normalize_company_name(clean_name)
        for company, industry in self.industry_map.items():
            company_normalized = normalize_company_name(company)
            if clean_name_normalized == company_normalized:
                return industry
        
        # 부분 매칭 시도 (최소 3자 이상인 경우만)
        # 금융회사명이 3자 미만이면 부분 매칭 시도하지 않음
        if len(clean_name_normalized) >= 3:
            for company, industry in self.industry_map.items():
                company_normalized = normalize_company_name(company)
                # 회사명도 3자 이상인 경우만 매칭 시도
                if len(company_normalized) >= 3:
                    # 금융회사명이 회사명을 포함하는 경우
                    if company_normalized in clean_name_normalized:
                        return industry
                    # 회사명이 금융회사명을 포함하는 경우
                    if clean_name_normalized in company_normalized:
                        return industry
        
        return '기타'
    
    def _init_selenium(self, headless=True):
        """Selenium 드라이버 초기화"""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ko-KR')
            # 불필요한 로그 메시지 숨기기
            chrome_options.add_argument('--log-level=3')  # INFO 레벨 이상만 출력
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 다운로드 디렉토리 설정
            prefs = {
                'download.default_directory': str(os.path.abspath(self.download_dir)),
                'download.prompt_for_download': False,
                'download.directory_upgrade': True,
                'safebrowsing.enabled': True
            }
            chrome_options.add_experimental_option('prefs', prefs)
            
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
        # .pdf 확장자 체크
        if path.endswith('.pdf') or '.pdf' in query:
            return True
        # downloadBoard.do 같은 다운로드 엔드포인트도 PDF로 인식
        if 'downloadboard.do' in path:
            return True
        return False

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

    def download_file_from_list(self, file_id=None, file_list_id=None, li_num=None, pdf_url=None, filename='', page_index=1):
        """
        리스트 페이지에서 첨부파일 버튼 클릭하여 리스트 확장 후 전체다운로드 버튼 클릭하여 파일 다운로드
        
        Args:
            file_id: fileId 파라미터
            file_list_id: file_list ID
            li_num: li_num 텍스트 (번호) - 리스트에서 안정적으로 항목 찾기용
            pdf_url: 직접 다운로드 시도할 PDF 절대경로 URL
            filename: 파일명
            page_index: 페이지 인덱스
        
        Returns:
            tuple: (다운로드 성공 여부, 저장된 파일 경로)
        """
        try:
            if not SELENIUM_AVAILABLE or not self.driver:
                return False, None
            
            # li_num이 없으면 안정적으로 찾기 어려움
            if not li_num:
                return False, None
            
            # 파일명 추출 또는 생성
            if not filename or len(filename.strip()) < 3:
                filename = f"attachment_{int(time.time()*1000)}.pdf"
            
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            
            # 파일명 정리 (특수문자 제거) + li_num prefix로 식별성 확보
            safe_filename = filename
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                safe_filename = safe_filename.replace(char, '_')
            if li_num:
                safe_filename = f"n{li_num}_{safe_filename}"
            
            # 파일 저장 경로
            file_path = os.path.join(self.download_dir, safe_filename)
            
            # 이미 파일이 있으면 크기 검사 후 재다운로드 여부 결정
            if os.path.exists(file_path):
                existing_size = os.path.getsize(file_path)
                # 10KB 미만이면 HTML 등 실패로 간주하고 재다운로드 시도
                if existing_size < 10 * 1024:
                    print(f"  기존 파일이 너무 작아 재다운로드 시도: {safe_filename} ({existing_size} bytes)")
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                else:
                    print(f"  기존 파일 발견: {safe_filename}")
                    return True, file_path
            
            print(f"  파일 다운로드 시도: {filename}")

            # 항상 대상 페이지로 이동 (마지막에 머무른 페이지가 다를 수 있음)
            try:
                self.driver.get(self.list_url)
                time.sleep(2)
                if page_index and page_index > 1:
                    self.driver.execute_script(f"goPaging_PagingView('{page_index}');")
                    time.sleep(2)
            except Exception:
                pass
            
            # 다운로드 전 파일 수 확인
            before_files = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            
            # 대상 li 찾기 우선순위: li_num -> file_list_id -> href(file_id) -> data-fileid
            download_success = False
            target_li = None

            # 0) li_num으로 찾기 (가장 안정적)
            if li_num:
                try:
                    target_li = self.driver.find_element(
                        By.XPATH,
                        f"//li[contains(@class,'bo_li')][.//span[contains(@class,'li_num') and normalize-space(text())='{li_num}']]"
                    )
                except Exception:
                    target_li = None

            # 1) file_list_id로 찾기
            if not target_li and file_list_id:
                try:
                    file_list_element = self.driver.find_element(By.ID, file_list_id)
                    target_li = file_list_element.find_element(By.XPATH, "./ancestor::li[contains(@class, 'bo_li')]")
                except Exception as e:
                    print(f"  ⚠ file_list_id로 찾기 실패: {e}")
                    target_li = None

            # 2) href에 file_id가 포함된 링크로 찾기
            if not target_li and file_id:
                try:
                    link_matches = self.driver.find_elements(
                        By.XPATH, f"//a[contains(@href, '{file_id}')]"
                    )
                    if link_matches:
                        target_li = link_matches[0].find_element(By.XPATH, "./ancestor::li[contains(@class, 'bo_li')]")
                except Exception:
                    target_li = None

            # 3) data-fileid로 찾기
            if not target_li and file_id:
                try:
                    candidates = self.driver.find_elements(By.XPATH, "//li[@data-fileid]")
                    for li in candidates:
                        data_id = li.get_attribute('data-fileid') or ""
                        if file_id == data_id:
                            target_li = li.find_element(By.XPATH, "./ancestor::li[contains(@class, 'bo_li')]")
                            break
                except Exception as e:
                    print(f"  ⚠ data-fileid 검색 실패: {e}")
                    target_li = None

            if target_li:
                try:
                    parent_div = target_li.find_element(By.XPATH, ".//div[contains(@class, 'hidden_file_g')]")
                    parent_li = target_li

                    # 먼저 "첨부파일" 버튼 찾아서 클릭 (리스트 확장)
                    attach_btn = None
                    try:
                        attach_buttons = parent_li.find_elements(By.XPATH, 
                            ".//a[contains(text(), '첨부파일')] | "
                            ".//button[contains(text(), '첨부파일')] | "
                            ".//a[contains(@class, 'btn_file_open')] | "
                            ".//span[contains(text(), '첨부파일')]/parent::* | "
                            ".//*[contains(@class, 'attach')] | "
                            ".//*[contains(@onclick, 'file')]")
                        
                        if attach_buttons:
                            attach_btn = attach_buttons[0]
                    except:
                        attach_btn = None
                    
                    # 첨부파일 버튼을 찾지 못한 경우, 더 넓은 범위에서 찾기
                    if not attach_btn:
                        try:
                            all_links = parent_li.find_elements(By.TAG_NAME, "a")
                            for link in all_links:
                                link_text = link.text.strip()
                                if '첨부' in link_text or '파일' in link_text:
                                    attach_btn = link
                                    break
                        except:
                            attach_btn = None
                    
                    # 첨부파일 버튼 클릭 (리스트 확장)
                    if attach_btn:
                        try:
                            self.driver.execute_script("arguments[0].click();", attach_btn)
                            time.sleep(1.5)  # 리스트 확장 대기
                            print(f"  ✓ 첨부파일 버튼 클릭 (리스트 확장)")
                        except Exception as e:
                            print(f"  ⚠ 첨부파일 버튼 클릭 실패: {e}")

                    # 방법1: 확장된 영역에서 PDF href를 새로 읽어 GET 시도
                    fresh_pdf_url = None
                    try:
                        pdf_link = parent_div.find_element(By.XPATH, ".//a[contains(@class, 'pdf')]")
                        href = pdf_link.get_attribute("href") or ""
                        if href:
                            if href.startswith("http"):
                                fresh_pdf_url = href
                            elif href.startswith("/"):
                                fresh_pdf_url = f"{self.base_url}{href}"
                            else:
                                fresh_pdf_url = f"{self.base_url}/{href.lstrip('/')}"
                    except Exception:
                        fresh_pdf_url = None

                    target_pdf_url = fresh_pdf_url or pdf_url

                    if target_pdf_url:
                        try:
                            headers = {
                                'Referer': self.list_url,
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            }
                            r = self.session.get(target_pdf_url, headers=headers, timeout=30, stream=True, verify=False)
                            ct = r.headers.get('Content-Type', '').lower()
                            content_length = int(r.headers.get('Content-Length') or 0)
                            if r.status_code == 200 and ('pdf' in ct or 'application/octet-stream' in ct) and content_length > 0:
                                with open(file_path, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                final_size = os.path.getsize(file_path)
                                if final_size < 10 * 1024 or 'html' in ct:
                                    print(f"  ⚠ 방법1(GET) 응답이 HTML/소용량({final_size} bytes), 방법2로 폴백")
                                    try:
                                        os.remove(file_path)
                                    except Exception:
                                        pass
                                else:
                                    print(f"  ✓ 방법1(GET) 성공: {final_size} bytes")
                                    return True, file_path
                        except Exception as e:
                            print(f"  ⚠ 방법1(GET) 실패: {e}")

                    # 방법2: 전체다운로드 버튼 찾기 및 클릭
                    all_download = parent_div.find_elements(By.XPATH, ".//a[contains(@class, 'all_download')]")
                    if all_download:
                        self.driver.execute_script("arguments[0].click();", all_download[0])
                        download_success = True
                        print(f"  ✓ 전체다운로드 버튼 클릭")
                    else:
                        print(f"  ⚠ 전체다운로드 버튼을 찾을 수 없습니다")
                except Exception as e:
                    print(f"  ⚠ 대상 li 처리 실패: {e}")

            if not target_li:
                print("  ⚠ 대상 li를 찾지 못했습니다")
                return False, None
            
            if not download_success:
                return False, None
            
            # 다운로드 대기 (30초)
            for i in range(30):
                time.sleep(1)
                after_files = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
                new_files = after_files - before_files
                if new_files:
                    break
                # .crdownload 파일 확인
                if i == 29 and os.path.exists(self.download_dir):
                    all_files = os.listdir(self.download_dir)
                    crdownload_files = [f for f in all_files if f.endswith('.crdownload')]
                    if crdownload_files:
                        for j in range(20):
                            time.sleep(1)
                            current_files = os.listdir(self.download_dir)
                            if not any(f.endswith('.crdownload') for f in current_files):
                                after_files = set(current_files)
                                new_files = after_files - before_files
                                break
            
            # 다운로드된 파일 찾기
            after_files = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = after_files - before_files
            
            if new_files:
                # 가장 최근 파일 찾기
                latest_file_path = None
                latest_time = 0
                for new_file in new_files:
                    file_path_full = os.path.join(self.download_dir, new_file)
                    if os.path.exists(file_path_full):
                        file_time = os.path.getctime(file_path_full)
                        if file_time > latest_time:
                            latest_time = file_time
                            latest_file_path = file_path_full
                
                if latest_file_path:
                    # 파일명이 다르면 원하는 이름으로 변경
                    if latest_file_path != file_path:
                        try:
                            os.rename(latest_file_path, file_path)
                        except:
                            file_path = latest_file_path
                    
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f"  ✓ 파일 다운로드 완료: {safe_filename} ({file_size} bytes)")
                        return True, file_path
            
            return False, None
            
        except Exception as e:
            print(f"  파일 다운로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return False, None

    def extract_attachment_content(self, detail_url, link_text='', force_ocr=False):
        """
        첨부파일 내용 추출 (FileExtractor 사용)
        
        Args:
            detail_url: 상세 페이지 URL
            link_text: 링크 텍스트
            force_ocr: True면 무조건 OCR 시도
        
        Returns:
            tuple: (추출된 내용, 문서유형, 파일다운로드URL)
        """
        try:
            # PDF URL인 경우 직접 다운로드
            if self.is_pdf_url(detail_url):
                filename = self.derive_filename(detail_url, link_text)
                print(f"  PDF 다운로드 시도: {filename}")
                
                # 파일명 정리 (특수문자 제거)
                safe_filename = filename
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    safe_filename = safe_filename.replace(char, '_')
                
                # output/downloads에 저장할 경로
                final_file_path = os.path.join(self.download_dir, safe_filename)
                
                # 이미 파일이 있으면 재다운로드하지 않음
                if os.path.exists(final_file_path):
                    print(f"  기존 파일 발견: {safe_filename}")
                    file_path = final_file_path
                else:
                    # FileExtractor로 파일 다운로드 (임시로 temp_dir에 다운로드)
                    file_path, actual_filename = self.file_extractor.download_file(
                        url=detail_url,
                        filename=filename,
                        referer=self.list_url
                    )
                    
                    # 다운로드된 파일을 output/downloads로 이동
                    if file_path and os.path.exists(file_path):
                        try:
                            import shutil
                            shutil.move(file_path, final_file_path)
                            file_path = final_file_path
                            print(f"  ✓ 파일 저장: {safe_filename}")
                        except Exception as e:
                            print(f"  ⚠ 파일 이동 실패: {e}, 원본 위치 유지")
                
                if file_path and os.path.exists(file_path):
                    # FileExtractor로 PDF 내용 추출
                    content = self.file_extractor.extract_pdf_content(file_path)
                    doc_type = 'PDF-텍스트'
                    
                    # force_ocr가 True이거나 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                    if force_ocr or not content or len(content.strip()) < self.min_text_length:
                        if self.ocr_extractor.is_available():
                            ocr_text = self.ocr_extractor.extract_text(file_path, mode='auto')
                            if ocr_text:
                                # OCR 결과 후처리 (띄어쓰기 보존)
                                content = process_ocr_text(ocr_text, preserve_spacing=True)
                                doc_type = 'PDF-OCR'
                                print(f"  ✓ OCR 추출 및 후처리 완료 ({len(content)}자)")
                            else:
                                print(f"  ✗ OCR 추출 실패 (결과 없음)")
                        else:
                            print(f"  ✗ OCR 사용 불가")
                    
                    # 파일 삭제하지 않고 유지
                    if content and content.strip():
                        print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자), 파일 저장: {file_path}")
                        return content, doc_type, file_path
                    else:
                        return "[PDF 파일이지만 텍스트 추출 실패]", 'PDF-OCR필요', file_path
                else:
                    return "[파일 다운로드 실패]", '오류', detail_url
            
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

                    # 파일명 정리 (특수문자 제거)
                    safe_filename = filename
                    invalid_chars = '<>:"/\\|?*'
                    for char in invalid_chars:
                        safe_filename = safe_filename.replace(char, '_')
                    
                    # output/downloads에 저장할 경로
                    final_file_path = os.path.join(self.download_dir, safe_filename)
                    
                    # 이미 파일이 있으면 재다운로드하지 않음
                    if os.path.exists(final_file_path):
                        print(f"  기존 파일 발견: {safe_filename}")
                        file_path = final_file_path
                    else:
                        # FileExtractor로 파일 다운로드 (임시로 temp_dir에 다운로드)
                        file_path, actual_filename = self.file_extractor.download_file(
                            url=file_url,
                            filename=filename,
                            referer=detail_url
                        )
                        
                        # 다운로드된 파일을 output/downloads로 이동
                        if file_path and os.path.exists(file_path):
                            try:
                                import shutil
                                shutil.move(file_path, final_file_path)
                                file_path = final_file_path
                                print(f"  ✓ 파일 저장: {safe_filename}")
                            except Exception as e:
                                print(f"  ⚠ 파일 이동 실패: {e}, 원본 위치 유지")
                    
                    if file_path and os.path.exists(file_path):
                        if file_path.lower().endswith('.pdf'):
                            content = self.file_extractor.extract_pdf_content(file_path)
                            doc_type = 'PDF-텍스트'
                            
                            # force_ocr가 True이거나 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                            if force_ocr or not content or len(content.strip()) < self.min_text_length:
                                if self.ocr_extractor.is_available():
                                    ocr_text = self.ocr_extractor.extract_text(file_path, mode='auto')
                                    if ocr_text:
                                        # OCR 결과 후처리 (띄어쓰기 보존)
                                        content = process_ocr_text(ocr_text, preserve_spacing=True)
                                        doc_type = 'PDF-OCR'
                                        print(f"  ✓ OCR 추출 및 후처리 완료 ({len(content)}자)")
                                    else:
                                        print(f"  ✗ OCR 추출 실패 (결과 없음)")
                                else:
                                    print(f"  ✗ OCR 사용 불가")
                            
                            # 파일 삭제하지 않고 유지
                            if content and content.strip():
                                print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자), 파일 저장: {file_path}")
                                return content, doc_type, file_path
                            else:
                                return f"[PDF 파일이지만 텍스트 추출 실패: {filename}]", 'PDF-OCR필요', file_path
                        else:
                            # PDF가 아닌 파일도 저장
                            return f"[{os.path.splitext(file_path)[1]} 파일은 현재 지원되지 않습니다: {filename}]", '기타첨부파일', file_path
                    break

            return "[첨부파일을 찾을 수 없습니다]", '첨부없음', ''

        except Exception as e:
            print(f"  첨부파일 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return f"[오류: {str(e)}]", '오류', ''

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
                    
                    # 제목에서 금융회사명 추출 (형식: "{금융회사명} 제재내용 공개안")
                    institution_from_title = ""
                    if title:
                        # "제재내용 공개안" 또는 "제재" 앞까지 추출
                        match = re.match(r'^(.+?)\s+제재', title)
                        if match:
                            institution_from_title = match.group(1).strip()
                    
                    # 날짜 추출 (첫 번째 li_date가 게시일)
                    date_spans = li.find_all('span', class_='li_date')
                    post_date = ""
                    if date_spans:
                        post_date = date_spans[0].get_text(strip=True)
                    
                    # 번호(span.li_num) 추출 (목록 위치 구분용)
                    li_num_span = li.find('span', class_='li_num')
                    li_num_text = li_num_span.get_text(strip=True) if li_num_span else ''

                    # 첨부파일 링크 찾기 - href와 fileId 추출
                    hidden_file_div = li.find('div', class_='hidden_file_g')
                    pdf_url = None
                    pdf_filename = None
                    file_id = None  # fileId 저장 (다운로드용)
                    file_list_id = None  # file_list ID 저장 (다운로드용)
                    
                    if hidden_file_div:
                        file_list = hidden_file_div.find('ul', class_='file_list')
                        if file_list:
                            # file_list ID 추출
                            file_list_id = file_list.get('id')
                            
                            # li 태그에서 data-fileid 속성 추출
                            li_item = file_list.find('li')
                            if li_item and li_item.get('data-fileid'):
                                file_id = li_item.get('data-fileid')
                            
                            pdf_link = file_list.find('a', class_='pdf')
                            if pdf_link:
                                pdf_filename = pdf_link.get_text(strip=True)
                                # href 추출 (다운로드 URL)
                                href = pdf_link.get('href', '')
                                if href:
                                    # 상대 경로인 경우 base_url과 결합
                                    if href.startswith('/'):
                                        pdf_url = f"{self.base_url}{href}"
                                    elif href.startswith('http'):
                                        pdf_url = href
                                    else:
                                        pdf_url = f"{self.base_url}/{href}"
                                
                                # href에서 fileId 추출 (data-fileid가 없는 경우)
                                if not file_id and href:
                                    if 'fileId=' in href:
                                        parsed = urlparse(href)
                                        query_params = parse_qs(parsed.query)
                                        if 'fileId' in query_params:
                                            file_id = query_params['fileId'][0]
                    
                    items.append({
                        '_file_id': file_id,  # fileId 저장
                        '_pdf_filename': pdf_filename,
                        '_pdf_download_url': pdf_url,  # 다운로드 URL 저장
                        '_file_list_id': file_list_id,  # file_list ID 저장
                        '_li_num': li_num_text,  # li_num 저장 (안정적 식별자)
                        '_link_text': title,
                        '_post_date': post_date,
                        '_institution_from_title': institution_from_title,  # 목록에서 추출한 금융회사명
                        '_page_index': page_index,  # 페이지 인덱스 저장 (다운로드용)
                        '첨부파일URL': pdf_url  # 기존 호환성 유지
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
    
    def normalize_date_format(self, date_str):
        """
        날짜 문자열을 YYYY-MM-DD 형식으로 변환
        지원 형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
        """
        if not date_str:
            return ''
        
        date_str = date_str.strip()
        if not date_str:
            return ''
        
        # 이미 YYYY-MM-DD 형식이면 그대로 반환
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # 다른 형식 변환 시도
        date_obj = self.parse_date(date_str)
        if date_obj:
            return date_obj.strftime('%Y-%m-%d')
        
        return ''

    def scrape_all(self, limit=None, after_date=None, sdate='', edate=''):
        """
        전체 페이지 스크래핑
        
        Args:
            limit: 수집할 최대 항목 수 (None이면 전체 수집)
            after_date: 이 날짜 이후 항목만 수집 (YYYY-MM-DD 또는 YYYY.MM.DD 형식)
            sdate: 검색 시작일 (YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD 형식 지원)
            edate: 검색 종료일 (YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD 형식 지원)
        """
        # 날짜 형식 정규화 (YYYY-MM-DD로 통일)
        sdate_normalized = self.normalize_date_format(sdate) if sdate else ''
        edate_normalized = self.normalize_date_format(edate) if edate else ''
        
        print("=" * 60)
        print("금융정보분석원 제재공시 스크래핑 시작 (v2 - FileExtractor 사용)")
        if limit:
            print(f"  수집 제한: {limit}개")
        if after_date:
            print(f"  날짜 필터: {after_date} 이후")
        if sdate_normalized or edate_normalized:
            print(f"  검색 기간: {sdate_normalized or '전체'} ~ {edate_normalized or '전체'}")
        else:
            print(f"  검색 기간: 전체")
        print("=" * 60)
        
        # 날짜 문자열을 datetime으로 변환
        after_datetime = self.parse_date(after_date) if after_date else None
        sdate_datetime = self.parse_date(sdate_normalized) if sdate_normalized else None
        edate_datetime = self.parse_date(edate_normalized) if edate_normalized else None
        
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
            
            # 날짜 기준 종료 (루프 시작 전에 체크)
            if stop_by_date:
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
            page_has_valid_items = False  # 이 페이지에 범위 내 항목이 있는지
            
            for item in items:
                # limit 체크
                if limit and len(all_items) + len(new_items) >= limit:
                    break
                
                # 날짜 필터링
                post_date_str = item.get('_post_date', '')
                post_datetime = self.parse_date(post_date_str)
                
                # 날짜 필터링이 필요한 경우
                if sdate_datetime or edate_datetime or after_datetime:
                    if not post_datetime:
                        # 날짜를 파싱할 수 없으면 건너뜀 (안전을 위해)
                        if post_date_str:
                            print(f"  날짜 파싱 실패: '{post_date_str}' - 건너뜀")
                        continue
                    
                    # 필터링 조건 확인
                    is_before_sdate = sdate_datetime and post_datetime < sdate_datetime
                    is_after_edate = edate_datetime and post_datetime > edate_datetime
                    is_before_after_date = after_datetime and post_datetime < after_datetime
                    
                    # 범위 밖 항목은 건너뜀
                    if is_before_sdate or is_after_edate or is_before_after_date:
                        continue
                    
                    # 범위 내 항목 발견
                    page_has_valid_items = True
                    
                pdf_url = item.get('첨부파일URL')
                if pdf_url and pdf_url in seen_urls:
                    continue
                if pdf_url:
                    seen_urls.add(pdf_url)
                new_items.append(item)
            
            # 페이지의 모든 항목을 확인한 후 처리
            if new_items:
                all_items.extend(new_items)
            
            # 날짜 필터링이 있고, 이 페이지에 범위 내 항목이 없고, 목록이 날짜순 정렬되어 있다면 중단 고려
            # (최신순 정렬 가정: 시작일보다 이전 항목만 있고 범위 내 항목이 없으면 더 이상 읽을 필요 없음)
            # 하지만 안전을 위해 연속으로 2페이지에서 범위 내 항목이 없을 때만 중단
            if (sdate_datetime or edate_datetime or after_datetime) and not page_has_valid_items:
                # 이 페이지에 범위 내 항목이 없음
                # 연속으로 범위 밖 페이지가 나오는지 추적
                if not hasattr(self, '_consecutive_empty_pages'):
                    self._consecutive_empty_pages = 0
                
                if items:  # 페이지에 항목은 있지만 모두 범위 밖
                    self._consecutive_empty_pages += 1
                    if self._consecutive_empty_pages >= 2:
                        # 연속 2페이지에서 범위 내 항목이 없으면 중단 (최신순 정렬 가정)
                        print(f"\n연속 {self._consecutive_empty_pages}페이지에서 범위 내 항목이 없어 수집을 종료합니다.")
                        stop_by_date = True
                        break
                else:  # 빈 페이지
                    self._consecutive_empty_pages = 0  # 빈 페이지는 카운트 리셋
            else:
                # 범위 내 항목이 있으면 카운터 리셋
                if hasattr(self, '_consecutive_empty_pages'):
                    self._consecutive_empty_pages = 0
            
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

        print("\n파일 다운로드 및 상세 정보 추출 시작...")
        
        for idx, item in enumerate(all_items, 1):
            link_text = item.pop('_link_text', '')
            pdf_filename = item.pop('_pdf_filename', '')
            item.pop('_post_date', None)  # 임시 필드 제거
            institution_from_title = item.pop('_institution_from_title', '')  # 목록에서 추출한 금융회사명
            file_id = item.pop('_file_id', None)  # fileId 추출
            file_list_id = item.pop('_file_list_id', None)  # file_list_id 추출
            li_num = item.pop('_li_num', None)  # li_num 추출 (안정적 식별자)
            page_index = item.pop('_page_index', 1)  # 페이지 인덱스 추출
            pdf_download_url = item.pop('_pdf_download_url', None)  # 다운로드 URL 추출
            
            print(f"\n[{idx}/{len(all_items)}] {pdf_filename or link_text or 'N/A'} 처리 중...")
            
            # 파일 다운로드 (별도 처리)
            saved_file_path = None
            if file_id or li_num:
                print(f"  파일 다운로드 중...")
                download_success, saved_file_path = self.download_file_from_list(
                    file_id=file_id,
                    file_list_id=file_list_id,
                    li_num=li_num,
                    pdf_url=pdf_download_url,
                    filename=pdf_filename or link_text,
                    page_index=page_index
                )
                if download_success and saved_file_path:
                    item['저장된파일경로'] = saved_file_path
                    item['파일경로'] = saved_file_path  # DB 매핑용 컬럼
                    print(f"  ✓ 파일 다운로드 완료: {os.path.basename(saved_file_path)}")
                else:
                    print(f"  ⚠ 파일 다운로드 실패")
            
            # 첨부파일 내용 추출
            # 다운로드된 파일이 있으면 그 파일에서 내용 추출, 없으면 기존 로직 사용
            attachment_content = None
            doc_type = None
            
            if saved_file_path and os.path.exists(saved_file_path):
                # 다운로드된 파일에서 내용 추출
                print(f"  다운로드된 파일에서 내용 추출 중...")
                content = self.file_extractor.extract_pdf_content(saved_file_path)
                doc_type = 'PDF-텍스트'
                
                # 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                if not content or len(content.strip()) < self.min_text_length:
                    if self.ocr_extractor.is_available():
                        ocr_text = self.ocr_extractor.extract_text(saved_file_path, mode='auto')
                        if ocr_text:
                            content = process_ocr_text(ocr_text, preserve_spacing=True)
                            doc_type = 'PDF-OCR'
                            print(f"  ✓ OCR 추출 및 후처리 완료 ({len(content)}자)")
                
                attachment_content = content if content and content.strip() else "[PDF 파일이지만 텍스트 추출 실패]"
                file_download_url = item.get('첨부파일URL', '')
            elif item.get('첨부파일URL'):
                # 기존 로직: URL에서 다운로드하여 내용 추출
                attachment_content, doc_type, _ = self.extract_attachment_content(
                    item['첨부파일URL'], 
                    pdf_filename or link_text
                )
            
            if attachment_content:
                if saved_file_path:
                    item['파일경로'] = saved_file_path  # DB 매핑용 컬럼
                item['제재조치내용'] = attachment_content
                
                # OCR 추출 여부 설정
                is_ocr = doc_type == 'PDF-OCR'
                item['OCR추출여부'] = '예' if is_ocr else '아니오'
                
                # PDF 내용에서 금융회사명, 제재조치일, 제재내용 추출
                # V3: extract_metadata.py만 사용 (OCR/일반 텍스트 모두 동일한 함수 사용)
                if attachment_content and not attachment_content.startswith('['):
                    if is_ocr:
                        print(f"  OCR 텍스트로 메타데이터 추출 중...")
                    
                    institution, sanction_date = extract_metadata_from_content(attachment_content)
                    
                    # 금융회사명: 목록에서 추출한 값 우선, 없으면 PDF에서 추출한 값 사용
                    if institution_from_title:
                        item['금융회사명'] = institution_from_title
                        print(f"  금융회사명 (목록): {institution_from_title}")
                    elif institution:
                        # 마지막 '*', '@' 제거
                        institution = institution.rstrip('*@')
                        item['금융회사명'] = institution
                        print(f"  금융회사명 (PDF): {institution}")
                    
                    # 업종 매핑
                    final_institution = item.get('금융회사명', '')
                    if final_institution:
                        industry = self.get_industry(final_institution)
                        item['업종'] = industry
                        print(f"  업종: {industry}")
                    else:
                        item['업종'] = '기타'
                    if sanction_date:
                        item['제재조치일'] = sanction_date
                        print(f"  제재조치일 추출: {sanction_date}")
                    
                    # 제재내용 (표 데이터) 추출
                    try:
                        sanction_details = extract_sanction_details(attachment_content)
                        if sanction_details:
                            item['제재내용'] = sanction_details
                            print(f"  제재내용 추출: {len(sanction_details)}자")
                        else:
                            print(f"  제재내용 추출: 없음")
                    except Exception as e:
                        print(f"  ⚠ 제재내용 추출 중 오류 발생: {e}")
                        import traceback
                        traceback.print_exc()
                        item['제재내용'] = ''
                    
                    # 사건 제목/내용 추출 (4번 항목)
                    incidents = {}
                    try:
                        print(f"  사건 제목/내용 추출 중...")
                        incidents = extract_incidents(attachment_content)
                        if incidents:
                            # OCR 추출인 경우 '내용' 필드에 clean_content_symbols 적용 (FSS와 동일)
                            if is_ocr:
                                for key in list(incidents.keys()):
                                    if key.startswith('내용'):
                                        # 먼저 process_ocr_text로 기본 후처리 (띄어쓰기 보존)
                                        processed = process_ocr_text(incidents[key], preserve_spacing=True)
                                        # 그 다음 clean_content_symbols로 조사 뒤 띄어쓰기 추가
                                        incidents[key] = clean_content_symbols(processed)
                            item.update(incidents)
                            incident_count = len([k for k in incidents.keys() if k.startswith('제목')])
                            print(f"  사건 추출: {incident_count}건")
                        else:
                            print(f"  사건 추출: 없음")
                    except Exception as e:
                        print(f"  ⚠ 사건 추출 중 오류 발생: {e}")
                        import traceback
                        traceback.print_exc()
                        # 오류가 발생해도 계속 진행
                        incidents = {}
                    
                    # 메타데이터 추출 결과가 모두 비어있고, 일반 텍스트 추출이었던 경우 OCR 재시도
                    # 금융회사명, 제재조치일은 제외 (목록에서 추출하거나 필수 항목이 아님)
                    has_metadata = (
                        item.get('제재내용') or 
                        incidents
                    )
                    
                    if (not has_metadata and 
                        doc_type == 'PDF-텍스트' and 
                        attachment_content and 
                        len(attachment_content.strip()) > 0 and
                        not attachment_content.startswith('[')):
                        print(f"  ⚠ 메타데이터 추출 실패 - OCR 재시도 중...")
                        # 1순위: 이미 다운로드한 파일(saved_file_path)로 OCR 재시도
                        ocr_source_path = saved_file_path if saved_file_path and os.path.exists(saved_file_path) else None
                        # 2순위: URL 재다운로드 (fallback)
                        if not ocr_source_path:
                            ocr_retry_url = item['첨부파일URL'] if self.is_pdf_url(item['첨부파일URL']) else file_download_url
                            if ocr_retry_url and self.is_pdf_url(ocr_retry_url):
                                filename = self.derive_filename(ocr_retry_url, pdf_filename or link_text)
                                ocr_source_path, _ = self.file_extractor.download_file(
                                    url=ocr_retry_url,
                                    filename=filename,
                                    referer=self.list_url if self.is_pdf_url(item['첨부파일URL']) else item['첨부파일URL']
                                )
                        
                        if ocr_source_path and os.path.exists(ocr_source_path) and self.ocr_extractor.is_available():
                            ocr_text = self.ocr_extractor.extract_text(ocr_source_path, mode='auto')
                            if ocr_text:
                                # OCR 결과 후처리
                                ocr_content = process_ocr_text(ocr_text, preserve_spacing=True)
                                item['제재조치내용'] = ocr_content
                                item['OCR추출여부'] = '예'
                                doc_type = 'PDF-OCR'
                                is_ocr = True
                                
                                print(f"  ✓ OCR 재시도 성공 ({len(ocr_content)}자)")
                                
                                # OCR 텍스트로 메타데이터 재추출
                                institution, sanction_date = extract_metadata_from_content(ocr_content)
                                
                                if institution_from_title:
                                    item['금융회사명'] = institution_from_title
                                elif institution:
                                    institution = institution.rstrip('*@')
                                    item['금융회사명'] = institution
                                
                                final_institution = item.get('금융회사명', '')
                                if final_institution:
                                    industry = self.get_industry(final_institution)
                                    item['업종'] = industry
                                else:
                                    item['업종'] = '기타'
                                
                                if sanction_date:
                                    item['제재조치일'] = sanction_date
                                
                                try:
                                    sanction_details = extract_sanction_details(ocr_content)
                                    if sanction_details:
                                        item['제재내용'] = sanction_details
                                except Exception as e:
                                    item['제재내용'] = ''
                                
                                try:
                                    incidents = extract_incidents(ocr_content)
                                    if incidents:
                                        for key in list(incidents.keys()):
                                            if key.startswith('내용'):
                                                processed = process_ocr_text(incidents[key], preserve_spacing=True)
                                                incidents[key] = clean_content_symbols(processed)
                                        item.update(incidents)
                                except Exception as e:
                                    incidents = {}
                            else:
                                print(f"  ✗ OCR 재시도 실패 (결과 없음)")
                        else:
                            print(f"  ✗ OCR 재시도 불가 (파일 경로 없음 또는 OCR 사용 불가)")
            else:
                item['제재조치내용'] = "[첨부파일 URL이 없습니다]"
                # 목록에서 추출한 금융회사명이 있으면 사용
                if institution_from_title:
                    item['금융회사명'] = institution_from_title
                    industry = self.get_industry(institution_from_title)
                    item['업종'] = industry
                    print(f"  금융회사명 (목록): {institution_from_title} (업종: {industry})")
                else:
                    item['업종'] = '기타'
                item['OCR추출여부'] = '아니오'
            
            # 업종 필드가 없는 경우 기타로 설정
            if '업종' not in item:
                item['업종'] = '기타'
            
            # OCR추출여부 필드가 없는 경우 기본값 설정
            if 'OCR추출여부' not in item:
                item['OCR추출여부'] = '아니오'

            self.results.append(item)
            time.sleep(1)

        # 리소스 정리
        self.close()

        return self.results

    def _clean_content(self, text):
        """
        텍스트에서 불필요한 줄바꿈 제거
        - 특수 마커(ㅇ, □, -, (1) 등) 앞의 줄바꿈은 유지
        - 그 외 줄바꿈은 공백으로 대체
        """
        if not text:
            return text
        
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
    
    def _post_process_content(self, text):
        """
        '내용' 필드 후처리
        - <관련법규>, <관련규정>, <조치할사항> 앞에 줄바꿈 추가 (공백 포함 패턴도 처리)
        - (가), (나), (다) 등 앞에 줄바꿈 추가
        """
        if not text:
            return text
        
        result = text
        
        # <관련법규> 앞에 줄바꿈 추가 (공백 포함 패턴도 처리)
        # <관련법규> 또는 < 관련법규 > 형태 모두 처리
        # 줄바꿈이 없는 경우에만 줄바꿈 추가
        result = re.sub(r'(?<![\n\r])\s*<(\s*)관련법규(\s*)>', r'\n<\1관련법규\2>', result)
        
        # <관련규정> 앞에 줄바꿈 추가 (공백 포함 패턴도 처리)
        # <관련규정> 또는 < 관련규정 > 형태 모두 처리
        # 줄바꿈이 없는 경우에만 줄바꿈 추가
        result = re.sub(r'(?<![\n\r])\s*<(\s*)관련규정(\s*)>', r'\n<\1관련규정\2>', result)
        
        # <조치할사항> 또는 <조시할사항> 앞에 줄바꿈 추가 (공백 포함 패턴도 처리)
        # 줄바꿈이 없는 경우에만 줄바꿈 추가
        result = re.sub(r'(?<![\n\r])\s*<(\s*)조치할사항(\s*)>', r'\n<\1조치할사항\2>', result)
        result = re.sub(r'(?<![\n\r])\s*<(\s*)조시할사항(\s*)>', r'\n<\1조시할사항\2>', result)
        
        # (가), (나), (다) 등 한글 괄호 패턴 앞에 줄바꿈 추가
        # 반각 괄호: (가), ( 가 ), (나) 등
        # 전각 괄호: （가）, （ 가 ）, （나） 등
        # 원문자: ㈎(가), ㈏(나), ㈐(다) 등
        # 줄바꿈이 없는 경우에만 줄바꿈 추가 (이미 줄바꿈이 있으면 중복 방지)
        # 반각 괄호 패턴 (공백 포함 가능)
        result = re.sub(r'(?<![\n\r])\s*\(\s*([가-하])\s*\)', r'\n(\1)', result)
        # 전각 괄호 패턴 (공백 포함 가능)
        result = re.sub(r'(?<![\n\r])\s*（\s*([가-하])\s*）', r'\n(\1)', result)
        # 원문자 패턴 (㈎=가, ㈏=나, ㈐=다, ... ㈛=하)
        # 유니코드 범위: ㈎(U+320E) ~ ㈛(U+321B)
        result = re.sub(r'(?<![\n\r])\s*([㈎-㈛])', r'\n\1', result)
        
        return result
    
    def _post_process_sanction_content(self, text):
        """
        '제재내용' 필드 후처리
        - "기 관" -> "기관"
        - "임 원" -> "임원"
        - "직 원" -> "직원"
        - "임 직 원" -> "임직원" (먼저 처리)
        - "임직원", "임원", "직원" 앞에 줄바꿈 추가
        """
        if not text:
            return text
        
        result = text
        
        # 공백 제거: "기 관" -> "기관"
        result = re.sub(r'기\s+관', '기관', result)
        
        # "임 직 원" -> "임직원" (먼저 처리하여 "임직원"을 하나의 단어로 만듦)
        result = re.sub(r'임\s+직\s+원', '임직원', result)
        
        # "임 원" -> "임원" (단, "임직원"이 아닌 경우만)
        result = re.sub(r'임\s+원(?!직)', '임원', result)
        
        # "직 원" -> "직원" (단, "임직원"이 아닌 경우만)
        result = re.sub(r'(?<!임)직\s+원', '직원', result)
        
        # "임직원" 앞에 줄바꿈 추가 (이미 줄바꿈이 없을 경우)
        result = re.sub(r'(?<!\n)임직원', '\n임직원', result)
        
        # "임원" 앞에 줄바꿈 추가 (이미 줄바꿈이 없고, "임직원"이 아닌 경우만)
        result = re.sub(r'(?<!\n)(?<!임)임원', '\n임원', result)
        
        # "직원" 앞에 줄바꿈 추가 (이미 줄바꿈이 없고, "임직원"이 아닌 경우만)
        result = re.sub(r'(?<!\n)(?<!임직)직원', '\n직원', result)
        
        return result

    def _split_incidents(self):
        """
        각 제재 건에서 사건들을 분리하여 개별 행으로 변환
        예: 제목1, 내용1, 제목2, 내용2 -> 두 개의 별도 행으로 분리
        """
        split_results = []
        
        for item in self.results:
            # 기본 필드 추출 (줄바꿈 정리 및 후처리 적용)
            raw_sanction_content = item.get('제재내용', '')
            cleaned_sanction_content = self._clean_content(raw_sanction_content)
            processed_sanction_content = self._post_process_sanction_content(cleaned_sanction_content)
            
            # 제재조치일 포맷팅 (PDF에서 추출한 값)
            sanction_date = item.get('제재조치일', '')
            if sanction_date:
                # format_date_to_iso 함수로 YYYY-MM-DD 형식으로 변환
                sanction_date = format_date_to_iso(sanction_date)
            
            base_data = {
                '구분': '제재사례',
                '출처': '금융정보분석원',
                '금융회사명': item.get('금융회사명', ''),
                '업종': item.get('업종', '기타'),
                '제재조치일': sanction_date,
                '제재내용': processed_sanction_content,
                '파일경로': item.get('파일경로', item.get('저장된파일경로', '')),
                'OCR추출여부': item.get('OCR추출여부', '아니오')
            }
            
            # 사건 수 확인
            incident_count = len([k for k in item.keys() if k.startswith('제목')])
            
            if incident_count == 0:
                # 사건이 없는 경우 기본 데이터만 저장
                split_results.append({
                    **base_data,
                    '제목': '',
                    '내용': ''
                })
            else:
                # 각 사건을 별도 행으로 분리
                for i in range(1, incident_count + 1):
                    title = item.get(f'제목{i}', '')
                    raw_content = item.get(f'내용{i}', '')
                    
                    # 내용 정리 (줄바꿈 정리 및 후처리)
                    cleaned_content = self._clean_content(raw_content)
                    processed_content = self._post_process_content(cleaned_content)
                    
                    split_results.append({
                        **base_data,
                        '제목': title,
                        '내용': processed_content
                    })
        
        return split_results

    def save_results(self, filename='kofiu_results.json'):
        """결과 저장 (JSON, CSV) - output 폴더에 저장"""
        # 스크립트 디렉토리 (루트 디렉토리)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # output 폴더 생성
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
                # 필드 순서: 구분, 출처, 업종, 금융회사명, 제목, 내용, 제재내용, 제재조치일, 파일경로, OCR추출여부
                fieldnames = ['구분', '출처', '업종', '금융회사명', '제목', '내용', '제재내용', '제재조치일', '파일경로', 'OCR추출여부']

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

# -------------------------------------------------
# Health Check 모드
# -------------------------------------------------
from typing import Dict
from common.common_http import check_url_status
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_schema import base_health_output
from common.constants import URLStatus
from common.url_health_mapper import map_urlstatus_to_health_error
from common.base_scraper import BaseScraper
from KoFIU_Scraper.extractor.pdf_extractor import PDFExtractor
from KoFIU_Scraper.extractor.ocr_extractor import OCRExtractor

def kofiu_health_check() -> Dict:

    def safe_remove(path: str):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    BASE_URL = "https://www.kofiu.go.kr"
    LIST_URL = "https://www.kofiu.go.kr/kor/notification/sanctions.do"
    OUTPUT_DIR = "output/downloads"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start_time = time.perf_counter()
    result = base_health_output(
        auth_src="금융위원회-금융정보분석원 > 제재공시",
        scraper_id="KOFIU",
        target_url=LIST_URL,
    )

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=ko-KR")
    prefs = {
        "download.default_directory": os.path.abspath(OUTPUT_DIR),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = None
    try:
        # ======================================================
        # HTTP 접근성 사전 체크
        # ======================================================
        http_result = check_url_status(
            LIST_URL,
            use_selenium=True,
            allow_fallback=False,
        )

        result["checks"]["http"] = {
            "ok": http_result["status"] == URLStatus.OK,
            "status": http_result["status"].name,
            "status_code": http_result["http_code"],
        }

        if http_result["status"] != URLStatus.OK:
            raise HealthCheckError(
                map_urlstatus_to_health_error(http_result["status"]),
                "목록 페이지 HTTP 접근 실패",
                target=LIST_URL,
            )
                
        baseScraper = BaseScraper()
        # driver = webdriver.Chrome(options=chrome_options)        
        driver = baseScraper._create_webdriver(chrome_options)
        # Headless 모드에서 다운로드 허용 설정 (중요)
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": os.path.abspath(OUTPUT_DIR)
        })        
        driver.get(LIST_URL)
        wait = WebDriverWait(driver, 15)

        # 1. 첫 번째 게시물 선택
        first_li = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.bo_li")))
        title = first_li.find_element(By.CSS_SELECTOR, "p.li_subject").text.strip()
        result["checks"]["list"] = {
            "success": True,
            "count": 1,
            "title": title
        }

        # 2. 첨부파일 처리용 기본 구조
        file_check = {
            "download_ok": False,
            "selenium_required": True,
            "text_extract_ok": False,
            "ocr_available": False,
            "reason": None,
            "message": None,
            "download_url": None,
            "path": None
        }

        try:
            # 첨부파일 버튼 클릭
            btn_file_open = first_li.find_element(By.CSS_SELECTOR, "a.btn_file_open")
            driver.execute_script("arguments[0].click();", btn_file_open)

            # PDF 링크 대기 및 클릭
            pdf_link_selector = "ul.file_list a.pdf"
            pdf_link_elem = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"li.bo_li {pdf_link_selector}")
            ))
            href = pdf_link_elem.get_attribute("href")
            download_url = urljoin(BASE_URL, href)
            file_check["download_url"] = download_url

            # ======================================================
            # 4-1. 다운로드 클릭
            # ======================================================
            driver.execute_script("arguments[0].click();", pdf_link_elem)

            # 다운로드 완료 대기
            timeout = 20
            save_path = None
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".pdf")]
                if files:
                    potential_path = os.path.join(OUTPUT_DIR, files[-1])
                    if os.path.getsize(potential_path) > 0:
                        save_path = potential_path
                        break
                time.sleep(1)

            if save_path:
                file_check.update(download_ok=True, path=save_path)
                # PDF 본문 추출 시도
                try:
                    text = PDFExtractor.extract_text(save_path)
                    if text.strip():
                        result["checks"]["pdf_parse"] = {
                            "success": True,
                            "message": "PDF 본문 파싱 가능"
                        }
                        file_check["text_extract_ok"] = True
                except Exception as e:
                    # PDF 파싱 실패 시 OCR 추출 시도
                    try:
                        ocr_text = OCRExtractor().extract_text(save_path)
                        if ocr_text.strip():
                            result["checks"]["ocr_parse"] = {
                                "success": True,
                                "message": "OCR 본문 파싱 가능"
                            }
                            file_check["ocr_available"] = True
                    except Exception as e2:
                        result["checks"]["ocr_parse"] = {
                            "success": False,
                            "message": f"[OCR_FAIL] {e2}"
                        }
            else:
                file_check.update(reason="DOWNLOAD_FAIL", message="PDF 다운로드 실패 또는 타임아웃")

        except Exception as e:
            file_check.update(reason="ELEMENT_NOT_FOUND", message=str(e))

        # FSS 스타일 출력
        result["checks"]["file_download"] = {
            "url": file_check.get("download_url"),
            "success": file_check.get("download_ok", False),
            "message": "첨부파일 다운로드 가능" if file_check.get("download_ok") else file_check.get("message")
        }

        # 헬스 체크 최종 상태
        result["ok"] = file_check["download_ok"]
        result["status"] = "OK" if result["ok"] else "FAIL"
        result["elapsed_ms"] = int((time.perf_counter() - start_time) * 1000)

        return result

    except Exception as e:
        raise HealthCheckError(HealthErrorType.UNKNOWN_ERROR, str(e), "kofiu_health_check")

    finally:
        # ===============================
        # ✅ 기능 완료 후 파일 삭제
        # ===============================
        safe_remove(save_path)

        if driver:
            driver.quit()

# ==================================================
# scheduler call
# ==================================================
def run(csv_path=None, limit=0):
    scraper = KoFIUScraperV2()
    results = scraper.scrape_all()
    scraper.save_results()

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 제재 건 수집 (사건별로 분리되어 저장됨)")
    print("=" * 60)


if __name__ == "__main__":
    # 기본 검색 기간 설정 (오늘 날짜 기준 일주일 전 ~ 오늘)
    today = datetime.now()
    default_edate = today.strftime('%Y-%m-%d')
    # 일주일 전 날짜 계산
    default_sdate = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    
    parser = argparse.ArgumentParser(description='금융정보분석원(KoFIU) 제재공시 스크래퍼')
    parser.add_argument('--limit', type=int, default=None,
                        help='수집할 최대 항목 수 (기본값: 전체 수집)')
    parser.add_argument('--after', type=str, default=None,
                        help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD 또는 YYYY.MM.DD, 기본값: None)')
    parser.add_argument('--sdate', type=str, default=default_sdate,
                        help=f'검색 시작일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_sdate})')
    parser.add_argument('--edate', type=str, default=default_edate,
                        help=f'검색 종료일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_edate})')
    parser.add_argument('--output', type=str, default='kofiu_results.json',
                        help='출력 파일명 (기본값: kofiu_results.json)')
    
    # -------------------------------------------------
    # Health Check 모드
    # -------------------------------------------------
    parser.add_argument(
        "--check",
        action="store_true",
        help="Health Check만 실행하고 종료",
    )

    args = parser.parse_args()
    
    # -------------------------------------------------
    # Health Check 모드
    # python kofiu_scraper_v2.py --check
    # -------------------------------------------------
    import json
    if args.check:
        result = kofiu_health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scraper = KoFIUScraperV2()
    results = scraper.scrape_all(limit=args.limit, after_date=args.after, sdate=args.sdate, edate=args.edate)
    scraper.save_results(filename=args.output)

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 제재 건 수집 (사건별로 분리되어 저장됨)")
    print("=" * 60)
    
    # 기본값으로 실행했을 때 데이터가 없는 경우 메시지 출력
    if len(results) == 0 and args.sdate == default_sdate and args.edate == default_edate and args.after is None:
        print("\n일주일 이내 업데이트된 게시물이 없습니다.")

