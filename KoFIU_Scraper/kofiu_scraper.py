import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import pdfplumber
import PyPDF2
from pathlib import Path
import io
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

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

class KoFIUScraper:
    def __init__(self):
        self.base_url = "https://www.kofiu.go.kr"
        self.list_url = "https://www.kofiu.go.kr/kor/notification/sanctions.do"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        self.results = []
        self.temp_dir = Path("temp_downloads")
        self.temp_dir.mkdir(exist_ok=True)
        self.min_text_length = 200  # 최소 텍스트 길이 (미만이면 OCR 시도)
        self.ocr_initialized = False
        self.ocr_available = False
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
        except Exception as e:
            print(f"  ※ Selenium 초기화 실패: {e}")
            self.driver = None
    
    def __del__(self):
        """소멸자에서 드라이버 종료"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def initialize_ocr(self):
        if self.ocr_initialized:
            return
        self.ocr_initialized = True
        if fitz is None or pytesseract is None or Image is None:
            print("  ※ OCR 모듈(PyMuPDF, pytesseract, Pillow) 중 일부가 설치되어 있지 않아 OCR을 사용할 수 없습니다.")
            self.ocr_available = False
            return

        tesseract_paths = [
            r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
            r'C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe',
            r'C:\\Users\\USER\\AppData\\Local\\Tesseract-OCR\\tesseract.exe',
            r'C:\\Users\\USER\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe'
        ]

        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                self.ocr_available = True
                print(f"  OCR 사용 준비 완료 (Tesseract 경로: {path})")
                break

        if not self.ocr_available:
            print("  ※ Tesseract 실행 파일을 찾을 수 없어 OCR을 사용할 수 없습니다.")

    def ocr_pdf(self, file_path):
        if not self.ocr_available:
            return None

        try:
            doc = fitz.open(str(file_path))
            texts = []
            for page in doc:
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert('L')
                configs = [
                    ('kor+eng', '--oem 3 --psm 6'),
                    ('kor+eng', '--oem 3 --psm 4'),
                    ('kor', '--oem 3 --psm 6'),
                    ('kor', '--oem 3 --psm 4')
                ]
                best_text = ''
                for lang, cfg in configs:
                    try:
                        candidate = pytesseract.image_to_string(image, lang=lang, config=cfg)
                        if candidate and len(candidate) > len(best_text):
                            best_text = candidate
                    except Exception:
                        continue
                if best_text:
                    texts.append(best_text)
            doc.close()
            full_text = '\n'.join(t.strip() for t in texts if t).strip()
            return full_text if full_text else None
        except Exception as e:
            print(f"  OCR 처리 중 오류: {e}")
            return None

    def get_page(self, url, retry=3):
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

    def extract_metadata_from_content(self, content):
        """PDF 내용에서 제재대상기관과 제재조치요구일 추출"""
        import re
        
        institution = ""
        sanction_date = ""
        
        if not content or content.startswith('['):
            return institution, sanction_date
        
        # 제재대상기관 추출: "1. 금융기관명" 또는 "1. 금 융 기 관 명" 뒤의 기관명
        institution_patterns = [
            r'1\.\s*금\s*융\s*기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*금융기관명\s*[:：]?\s*([^\n\r]+)',
            r'1\s*\.\s*금\s*융\s*기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
        ]
        
        for pattern in institution_patterns:
            match = re.search(pattern, content)
            if match:
                institution = match.group(1).strip()
                # 다음 줄까지 포함될 수 있으므로 줄바꿈 전까지만
                institution = institution.split('\n')[0].strip()
                # 특수문자 제거
                institution = re.sub(r'^[:\-\.\s]+', '', institution)
                institution = re.sub(r'[\-\.\s]+$', '', institution)
                if institution:
                    break
        
        # 제재조치요구일 추출: "2. 제재조치일" 또는 "2. 제 재 조 치 일" 뒤의 날짜
        date_patterns = [
            r'2\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
            r'2\.\s*제재조치일\s*[:：]?\s*([^\n\r]+)',
            r'2\s*\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content)
            if match:
                sanction_date = match.group(1).strip()
                # 다음 줄까지 포함될 수 있으므로 줄바꿈 전까지만
                sanction_date = sanction_date.split('\n')[0].strip()
                # 특수문자 제거
                sanction_date = re.sub(r'^[:\-\.\s]+', '', sanction_date)
                sanction_date = re.sub(r'[\-\.\s]+$', '', sanction_date)
                if sanction_date:
                    break
        
        return institution, sanction_date
    
    def extract_pdf_text(self, file_path):
        extracted_text = None
        extracted_length = 0

        try:
            with pdfplumber.open(file_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                if text.strip():
                    extracted_text = text.strip()
                    extracted_length = len(extracted_text)
        except Exception as e:
            print(f"pdfplumber로 추출 실패: {e}")

        if not extracted_text:
            try:
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    if text.strip():
                        extracted_text = text.strip()
                        extracted_length = len(extracted_text)
            except Exception as e:
                print(f"PyPDF2로 추출 실패: {e}")

        if extracted_text and extracted_length >= self.min_text_length:
            return extracted_text, 'PDF-텍스트'

        self.initialize_ocr()
        ocr_text = self.ocr_pdf(file_path) if self.ocr_available else None
        if ocr_text and len(ocr_text) > max(extracted_length, 0):
            return ocr_text.strip(), 'PDF-OCR'

        if extracted_text:
            doc_type = 'PDF-텍스트' if extracted_length >= self.min_text_length else 'PDF-OCR필요'
            return extracted_text, doc_type

        return None, 'PDF-OCR필요'

    def download_file(self, url, filename):
        try:
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()

            file_path = self.temp_dir / filename
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return file_path
        except Exception as e:
            print(f"파일 다운로드 실패: {e}")
            return None

    def is_pdf_url(self, url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()
        return path.endswith('.pdf') or '.pdf' in query

    def derive_filename(self, url: str, link_text: str = "") -> str:
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

    def _extract_from_selenium_page(self, soup, detail_id):
        """Selenium으로 로드된 페이지에서 첨부파일 추출"""
        try:
            # 파일 리스트 찾기
            file_list = soup.find('ul', id=f'file_list_{detail_id}')
            if not file_list:
                return "[첨부파일을 찾을 수 없습니다]", '첨부없음'
            
            # PDF 링크 찾기
            pdf_links = file_list.find_all('a', class_='pdf')
            if not pdf_links:
                return "[PDF 파일을 찾을 수 없습니다]", '첨부없음'
            
            # 첫 번째 PDF 다운로드
            pdf_link = pdf_links[0]
            href = pdf_link.get('href', '')
            if href.startswith('/'):
                file_url = urljoin(self.base_url, href)
            else:
                file_url = href
            
            filename = pdf_link.get_text(strip=True)
            if not filename or len(filename) < 3:
                filename = href.split('/')[-1].split('?')[0] if href else f"file_{detail_id}.pdf"
            
            print(f"  첨부파일 발견: {filename}")
            
            file_path = self.download_file(file_url, filename)
            if file_path and file_path.exists():
                if file_path.suffix.lower() == '.pdf':
                    content, detected_type = self.extract_pdf_text(file_path)
                    if content:
                        print(f"  PDF 내용 추출 완료 ({len(content)}자)")
                        try:
                            file_path.unlink()
                        except:
                            pass
                        return content, detected_type
                    else:
                        try:
                            file_path.unlink()
                        except:
                            pass
                        return f"[PDF 파일이지만 텍스트 추출 실패: {filename}]", 'PDF-OCR필요'
            
            return "[첨부파일 다운로드 실패]", '오류'
            
        except Exception as e:
            print(f"  Selenium 페이지에서 추출 중 오류: {e}")
            return f"[오류: {str(e)}]", '오류'
    
    def extract_attachment_content(self, detail_url, link_text=''):
        try:
            if self.is_pdf_url(detail_url):
                filename = self.derive_filename(detail_url, link_text)
                file_path = self.download_file(detail_url, filename)
                if file_path and file_path.exists():
                    content, detected_type = self.extract_pdf_text(file_path)
                    if content:
                        try:
                            file_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return content, detected_type
                    else:
                        try:
                            file_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return "[첨부파일에서 텍스트를 추출하지 못했습니다]", 'PDF-OCR필요'

            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)

            attachment_text = ""
            doc_type = '첨부없음'

            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                link_text = link.get_text(strip=True)

                if '/download' in href.lower() or 'download' in href.lower() or '.pdf' in href.lower():
                    if href.startswith('/'):
                        file_url = urljoin(self.base_url, href)
                    elif href.startswith('http'):
                        file_url = href
                    else:
                        file_url = urljoin(detail_url, href)

                    filename = link_text.strip()
                    if not filename or len(filename) < 3:
                        if 'file=' in href:
                            from urllib.parse import unquote
                            filename = unquote(href.split('file=')[-1].split('&')[0])
                        else:
                            filename = href.split('/')[-1].split('?')[0]

                    if not filename.lower().endswith('.pdf'):
                        if 'file=' in href:
                            from urllib.parse import unquote
                            filename = unquote(href.split('file=')[-1].split('&')[0])

                    if not filename.lower().endswith('.pdf'):
                        continue

                    print(f"  첨부파일 발견: {filename}")

                    file_path = self.download_file(file_url, filename)
                    if file_path and file_path.exists():
                        if file_path.suffix.lower() == '.pdf':
                            content, detected_type = self.extract_pdf_text(file_path)
                            if content:
                                attachment_text = content
                                doc_type = detected_type
                                print(f"  PDF 내용 추출 완료 ({len(content)}자)")
                            else:
                                attachment_text = f"[PDF 파일이지만 텍스트 추출 실패: {filename}]"
                                doc_type = 'PDF-OCR필요'
                        else:
                            attachment_text = f"[{file_path.suffix} 파일은 현재 지원되지 않습니다: {filename}]"
                            doc_type = '기타첨부파일'

                        try:
                            file_path.unlink()
                            print(f"  임시 파일 삭제 완료: {filename}")
                        except Exception:
                            pass

                        break

            if attachment_text:
                return attachment_text, doc_type

            if self.is_pdf_url(detail_url):
                filename = self.derive_filename(detail_url, link_text)
                file_path = self.download_file(detail_url, filename)
                if file_path and file_path.exists():
                    content, detected_type = self.extract_pdf_text(file_path)
                    if content:
                        attachment_text = content
                        doc_type = detected_type
                    else:
                        attachment_text = "[첨부파일에서 텍스트를 추출하지 못했습니다]"
                        doc_type = 'PDF-OCR필요'
                    try:
                        file_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return attachment_text, doc_type

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
                time.sleep(3)  # JavaScript 로드 대기
            else:
                # 2페이지 이후는 JavaScript 함수로 페이지 이동
                self.driver.execute_script(f"goPaging_PagingView('{page_index}');")
                time.sleep(3)  # 페이지 로드 대기
            
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
                    # 번호
                    num_span = li.find('span', class_='li_num')
                    number = num_span.get_text(strip=True) if num_span else ""
                    
                    # 제목 및 링크
                    subject_p = li.find('p', class_='li_subject')
                    title_link = subject_p.find('a') if subject_p else None
                    title = title_link.get_text(strip=True) if title_link else ""
                    
                    # JavaScript 링크에서 ID 추출
                    detail_id = None
                    if title_link and title_link.get('href', '').startswith('javascript:'):
                        href = title_link.get('href', '')
                        import re
                        match = re.search(r"viewLink\(['\"]?(\d+)['\"]?\)", href)
                        if match:
                            detail_id = match.group(1)
                    
                    # 날짜
                    date_spans = li.find_all('span', class_='li_date')
                    date = ""
                    view_count = ""
                    if date_spans:
                        date = date_spans[0].get_text(strip=True) if len(date_spans) > 0 else ""
                        if len(date_spans) > 1:
                            view_text = date_spans[1].get_text(strip=True)
                            # "조회수: 773" 형식에서 숫자 추출
                            import re
                            view_match = re.search(r'조회수:\s*(\d+)', view_text)
                            if view_match:
                                view_count = view_match.group(1)
                    
                    # 제재대상기관은 제목에서 추출 (예: "하나증권 제재내용 공개안" -> "하나증권")
                    institution = title.replace(' 제재내용 공개안', '').strip() if title else ""
                    
                    # 첨부파일 링크 찾기 (hidden_file_g 안에 있음)
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
                        '번호': number,
                        '제목': title,
                        '제재대상기관': institution,
                        '공시일': date,
                        '조회수': view_count,
                        '상세페이지URL': pdf_url,  # PDF 링크를 직접 사용
                        '_detail_id': detail_id,
                        '_pdf_filename': pdf_filename,
                        '_link_text': title
                    })
                    
                except Exception as e:
                    print(f"  항목 처리 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
            return items
            
        except Exception as e:
            print(f"  페이지 {page_index} 스크래핑 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def scrape_all(self):
        print("=" * 60)
        print("금융정보분석원 제재공시 스크래핑 시작")
        print("=" * 60)
        
        if not SELENIUM_AVAILABLE:
            print("  ※ Selenium이 설치되어 있지 않아 스크래핑을 수행할 수 없습니다.")
            print("     pip install selenium 을 실행하여 설치해주세요.")
            return []

        all_items = []
        seen_numbers = set()
        page = 1
        empty_pages = 0  # 연속으로 빈 페이지가 나오는 횟수

        while True:
            items = self.scrape_list_page(page)
            if not items:
                empty_pages += 1
                if empty_pages >= 2:  # 연속 2페이지가 비어있으면 종료
                    print(f"\n페이지 {page}에서 더 이상 항목이 없어 수집을 종료합니다.")
                    break
            else:
                empty_pages = 0

            new_items = []
            for item in items:
                number = item.get('번호')
                if number and number in seen_numbers:
                    continue
                if number:
                    seen_numbers.add(number)
                new_items.append(item)

            if new_items:
                all_items.extend(new_items)
            
            # 다음 페이지 확인
            if not items:
                # 항목이 없으면 종료
                break
            
            # 페이지네이션 확인 (다음 페이지가 있는지)
            try:
                # 총 페이지 수 확인
                total_pages = 10  # 기본값
                try:
                    # "1 / 10" 형식에서 총 페이지 수 추출
                    page_info = self.driver.find_element(By.XPATH, "//div[@class='paging']//div[contains(text(), '/')]")
                    page_text = page_info.text.strip()
                    import re
                    match = re.search(r'/\s*(\d+)', page_text)
                    if match:
                        total_pages = int(match.group(1))
                        print(f"  총 페이지 수: {total_pages}")
                except:
                    pass
                
                # 다음 페이지 버튼 확인
                try:
                    next_button = self.driver.find_element(By.XPATH, "//a[contains(@class, 'next') and not(contains(@href, 'void(0)'))]")
                    next_href = next_button.get_attribute('href')
                    if 'void(0)' in next_href or not next_button.is_enabled():
                        # 다음 페이지가 없으면 종료
                        if page >= total_pages:
                            print(f"\n모든 페이지 수집 완료 (총 {total_pages}페이지)")
                            break
                except:
                    # 다음 버튼을 찾을 수 없으면 총 페이지 수로 확인
                    if page >= total_pages:
                        print(f"\n모든 페이지 수집 완료 (총 {total_pages}페이지)")
                        break
                
                # 다음 페이지로 이동
                if page < total_pages:
                    try:
                        # JavaScript 함수로 다음 페이지 이동
                        self.driver.execute_script(f"goPaging_PagingView('{page + 1}');")
                        time.sleep(2)  # 페이지 로드 대기
                    except Exception as e:
                        print(f"  다음 페이지 이동 실패: {e}")
                        break
                else:
                    break
                    
            except Exception as e:
                print(f"  페이지네이션 확인 중 오류: {e}")
                # 오류 발생 시 안전하게 종료
                if page > 1:
                    break
            
            time.sleep(1)
            page += 1
            
            # 안전장치: 최대 100페이지까지만
            if page > 100:
                print(f"\n최대 페이지 수(100)에 도달하여 수집을 종료합니다.")
                break

        print(f"\n총 {len(all_items)}개 항목 수집 완료")

        print("\n상세 정보 및 첨부파일 추출 시작...")
        
        for idx, item in enumerate(all_items, 1):
            print(f"\n[{idx}/{len(all_items)}] {item.get('제목', 'N/A')} 처리 중...")

            link_text = item.pop('_link_text', '')
            pdf_filename = item.pop('_pdf_filename', '')
            item.pop('_detail_id', None)  # 더 이상 필요 없음
            
            if item.get('상세페이지URL'):
                # PDF URL이 직접 있으므로 다운로드
                attachment_content, doc_type = self.extract_attachment_content(item['상세페이지URL'], pdf_filename or link_text)
                item['제재조치내용'] = attachment_content
                item['문서유형'] = doc_type
                
                # PDF 내용에서 제재대상기관과 제재조치요구일 추출
                if attachment_content and not attachment_content.startswith('['):
                    institution, sanction_date = self.extract_metadata_from_content(attachment_content)
                    if institution:
                        item['제재대상기관'] = institution
                        print(f"  제재대상기관 추출: {institution}")
                    if sanction_date:
                        item['제재조치요구일'] = sanction_date
                        print(f"  제재조치요구일 추출: {sanction_date}")
            else:
                item['제재조치내용'] = "[첨부파일 URL이 없습니다]"
                item['문서유형'] = 'URL없음'

            self.results.append(item)
            time.sleep(1)

        try:
            for file in self.temp_dir.iterdir():
                file.unlink()
            self.temp_dir.rmdir()
            print("\n임시 파일 정리 완료")
        except Exception:
            pass
        
        # Selenium 드라이버 종료
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except:
                pass

        return self.results

    def save_results(self, filename='kofiu_results.json'):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {filename}에 저장되었습니다. (총 {len(self.results)}개)")

        try:
            import csv
            csv_filename = filename.replace('.json', '.csv')
            if self.results:
                fieldnames = ['번호', '제목', '제재대상기관', '제재조치요구일', '공시일', '조회수', '문서유형', '상세페이지URL', '제재조치내용']

                with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
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

                print(f"CSV 파일도 {csv_filename}에 저장되었습니다.")
        except Exception as e:
            print(f"CSV 저장 중 오류 (무시): {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    scraper = KoFIUScraper()
    results = scraper.scrape_all()
    scraper.save_results()

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

