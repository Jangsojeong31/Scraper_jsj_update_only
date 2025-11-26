"""
파일 다운로드 및 내용 추출 공통 모듈
HWP, PDF, ZIP 파일 처리
"""
import os
import time
import zipfile
import shutil
import tempfile
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup

# olefile 라이브러리 import
try:
    import olefile
except ImportError:
    olefile = None

# pyhwp 라이브러리 import
try:
    from hwp5.xmlmodel import Hwp5File
    from hwp5.hwp5txt import TextTransform
    from hwp5.hwp5html import HTMLTransform
    from contextlib import closing
    PYHWP_AVAILABLE = True
except ImportError as e:
    PYHWP_AVAILABLE = False
    Hwp5File = None
    TextTransform = None
    HTMLTransform = None
    closing = None
    print(f"pyhwp import 실패: {e}")

# PDF 라이브러리 import
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    PyPDF2 = None
    print("PyPDF2 import 실패, pdfplumber 시도")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    pdfplumber = None
    if not PYPDF2_AVAILABLE:
        print("pdfplumber import 실패, PDF 처리 불가")


class FileExtractor:
    """파일 다운로드 및 내용 추출 클래스"""
    
    def __init__(self, download_dir: str = "output/downloads", session=None):
        """
        Args:
            download_dir: 다운로드 디렉토리 경로
            session: requests.Session 객체 (파일 다운로드용)
        """
        self.download_dir = download_dir
        self.session = session
        os.makedirs(self.download_dir, exist_ok=True)
    
    def download_file(
        self, 
        url: str, 
        filename: str, 
        use_selenium: bool = False, 
        driver=None,
        referer: str = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        파일 다운로드
        
        Args:
            url: 다운로드 URL
            filename: 저장할 파일명
            use_selenium: Selenium 사용 여부
            driver: Selenium 드라이버 (use_selenium=True일 때 필요)
            referer: Referer 헤더 값 (선택사항)
            
        Returns:
            (다운로드된 파일 경로, 실제 파일명) 튜플 또는 (None, None)
        """
        try:
            if use_selenium and driver:
                # Selenium으로 다운로드 (쿠키 및 세션 유지)
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                # 다운로드 디렉토리 설정
                filepath = os.path.join(os.path.abspath(self.download_dir), filename)
                
                # Chrome 옵션에 다운로드 경로 설정 (이미 열린 드라이버는 설정 불가)
                # 대신 직접 URL로 이동하여 다운로드
                driver.get(url)
                time.sleep(3)  # 다운로드 대기
                
                # 다운로드된 파일 찾기
                # 파일이 다운로드 디렉토리에 있는지 확인
                if os.path.exists(filepath):
                    return filepath, os.path.basename(filepath)
                
                # 파일명이 다를 수 있으므로 최근 파일 찾기
                if os.path.exists(self.download_dir):
                    files = os.listdir(self.download_dir)
                    if files:
                        # 가장 최근 파일
                        latest_file = max([os.path.join(self.download_dir, f) for f in files], 
                                         key=os.path.getctime)
                        actual_filename = os.path.basename(latest_file)
                        # 파일명 변경
                        if latest_file != filepath:
                            os.rename(latest_file, filepath)
                            actual_filename = os.path.basename(filepath)
                        return filepath, actual_filename
                
                return None, None
            else:
                # requests로 다운로드
                if not self.session:
                    raise ValueError("requests.Session이 필요합니다. session 파라미터를 제공하거나 use_selenium=True를 사용하세요.")
                
                # URL 인코딩 처리
                from urllib.parse import quote, urlparse, parse_qs, urlencode
                parsed = urlparse(url)
                if parsed.query:
                    # 쿼리 파라미터 인코딩
                    params = parse_qs(parsed.query)
                    encoded_params = urlencode(params, doseq=True, quote_via=quote)
                    url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{encoded_params}"
                
                # Referer 헤더 추가
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                if referer:
                    headers['Referer'] = referer
                
                response = self.session.get(url, headers=headers, timeout=30, stream=True, verify=False)
                response.raise_for_status()
                
                # Content-Disposition 헤더에서 파일명 추출
                actual_filename = filename  # 기본값
                content_disposition = response.headers.get('Content-Disposition', '')
                if content_disposition:
                    # filename="파일명.hwp" 또는 filename*=UTF-8''파일명.hwp 형식
                    filename_match = re.search(r'filename[*]?=["\']?([^"\';]+)["\']?', content_disposition, re.IGNORECASE)
                    if filename_match:
                        extracted_filename = filename_match.group(1)
                        # URL 디코딩
                        from urllib.parse import unquote
                        extracted_filename = unquote(extracted_filename)
                        # 인코딩 문제 해결 (한글 파일명)
                        try:
                            # filename*=UTF-8'' 형식 처리
                            if "filename*=" in content_disposition:
                                # RFC 5987 형식: filename*=UTF-8''encoded_filename
                                utf8_match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
                                if utf8_match:
                                    extracted_filename = unquote(utf8_match.group(1))
                            # 일반적인 경우 latin-1 -> utf-8 변환 시도
                            if 'utf-8' in content_disposition.lower() or 'utf8' in content_disposition.lower():
                                try:
                                    extracted_filename = extracted_filename.encode('latin-1').decode('utf-8')
                                except:
                                    pass
                        except:
                            pass
                        if extracted_filename:
                            actual_filename = extracted_filename
                            print(f"  다운로드 응답에서 파일명 추출: {actual_filename}")
                
                # Content-Type 확인
                content_type = response.headers.get('Content-Type', '').lower()
                if 'html' in content_type or 'text' in content_type:
                    print(f"  ⚠ 경고: 다운로드된 파일이 HTML/텍스트 형식입니다. (Content-Type: {content_type})")
                
                filepath = os.path.join(self.download_dir, filename)
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # 파일 크기 확인
                file_size = os.path.getsize(filepath)
                if file_size < 1000:
                    print(f"  ⚠ 경고: 다운로드된 파일 크기가 매우 작습니다 ({file_size} bytes). 실제 파일이 아닐 수 있습니다.")
                    # 파일 내용 확인 (첫 100 bytes)
                    with open(filepath, 'rb') as f:
                        first_bytes = f.read(100)
                        if b'<html' in first_bytes.lower() or b'<!doctype' in first_bytes.lower():
                            print(f"  ✗ 다운로드된 파일이 HTML 페이지입니다.")
                            os.remove(filepath)
                            return None, None
                
                return filepath, actual_filename
        except Exception as e:
            print(f"파일 다운로드 실패: {url} - {e}")
            return None, None
    
    def extract_files_from_zip(self, zip_path: str) -> Optional[str]:
        """
        ZIP 파일에서 HWP 또는 PDF 파일을 찾아 추출 (HWP 우선)
        
        Args:
            zip_path: ZIP 파일 경로
            
        Returns:
            압축 해제된 파일 경로 (HWP 또는 PDF) 또는 None
        """
        if not zipfile.is_zipfile(zip_path):
            return None

        try:
            print(f"  ZIP 파일 감지, 압축 해제 중...")
            
            # 임시 디렉토리에 압축 해제
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                    
                    # HWP 파일 찾기 (우선)
                    hwp_files = []
                    pdf_files = []
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if file.lower().endswith('.hwp'):
                                hwp_files.append(file_path)
                            elif file.lower().endswith('.pdf'):
                                pdf_files.append(file_path)
                    
                    # HWP 파일이 있으면 우선 사용
                    if hwp_files:
                        extracted_file = hwp_files[0]
                        print(f"  ZIP 내부에서 HWP 파일 발견: {os.path.basename(extracted_file)} (총 {len(hwp_files)}개)")
                        temp_file_path = os.path.join(self.download_dir, f"temp_{os.path.basename(extracted_file)}")
                        shutil.copy2(extracted_file, temp_file_path)
                        return temp_file_path
                    # PDF 파일이 있으면 사용
                    elif pdf_files:
                        extracted_file = pdf_files[0]
                        print(f"  ZIP 내부에서 PDF 파일 발견: {os.path.basename(extracted_file)} (총 {len(pdf_files)}개)")
                        temp_file_path = os.path.join(self.download_dir, f"temp_{os.path.basename(extracted_file)}")
                        shutil.copy2(extracted_file, temp_file_path)
                        return temp_file_path
                    else:
                        print(f"  ⚠ ZIP 파일 내부에 HWP 또는 PDF 파일을 찾을 수 없습니다.")
                        return None
                        
        except Exception as e:
            print(f"  ✗ ZIP 파일 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def extract_pdf_content(self, filepath: str) -> str:
        """
        PDF 파일에서 텍스트 내용 추출
        
        Args:
            filepath: PDF 파일 경로
            
        Returns:
            추출된 텍스트 내용
        """
        content = ""
        
        if not os.path.exists(filepath):
            print(f"  ✗ PDF 파일이 존재하지 않음: {filepath}")
            return ""
        
        file_size = os.path.getsize(filepath)
        print(f"  PDF 파일 크기: {file_size} bytes")
        
        # pdfplumber 우선 시도 (더 정확함)
        if PDFPLUMBER_AVAILABLE and pdfplumber:
            try:
                print(f"  pdfplumber 사용 가능, 추출 시도 중...")
                with pdfplumber.open(filepath) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    content = '\n\n'.join(pages_text)
                if content and content.strip():
                    print(f"  ✓ pdfplumber로 {len(content)}자 추출 완료")
                else:
                    print(f"  ⚠ pdfplumber 추출 결과가 비어있음")
                    content = ""
            except Exception as e:
                print(f"  ✗ pdfplumber 추출 실패: {e}")
                content = ""
        
        # pdfplumber가 실패하면 PyPDF2 시도
        if not content and PYPDF2_AVAILABLE and PyPDF2:
            try:
                print(f"  PyPDF2 사용 가능, 추출 시도 중...")
                with open(filepath, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    pages_text = []
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    content = '\n\n'.join(pages_text)
                if content and content.strip():
                    print(f"  ✓ PyPDF2로 {len(content)}자 추출 완료")
                else:
                    print(f"  ⚠ PyPDF2 추출 결과가 비어있음")
                    content = ""
            except Exception as e:
                print(f"  ✗ PyPDF2 추출 실패: {e}")
                content = ""
        
        if not content:
            print(f"  ✗ 모든 PDF 추출 방법 실패")
        
        # 제어 문자 및 특수 문자 제거
        if content:
            # NULL 바이트 제거
            content = content.replace('\x00', '')
            # 연속된 공백 정리
            content = re.sub(r'[ \t]+', ' ', content)
            # 연속된 줄바꿈 정리
            content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
            print(f"  최종 추출된 내용: {len(content)}자")
        
        return content.strip()
    
    def extract_hwp_content(self, filepath: str) -> str:
        """
        HWP 또는 PDF 파일에서 텍스트 내용 추출
        ZIP 파일인 경우 자동으로 압축 해제 후 파일 추출
        
        Args:
            filepath: HWP/PDF 파일 경로 또는 ZIP 파일 경로
            
        Returns:
            추출된 텍스트 내용 (제어 문자 제거됨)
        """
        content = ""
        
        # 파일 존재 확인
        if not os.path.exists(filepath):
            print(f"  ✗ 파일이 존재하지 않음: {filepath}")
            return ""
        
        # PDF 파일인지 확인
        if filepath.lower().endswith('.pdf'):
            return self.extract_pdf_content(filepath)
        
        # ZIP 파일인지 확인 (HWPX가 아닌 일반 ZIP)
        if zipfile.is_zipfile(filepath):
            # HWPX 형식인지 확인 (Contents/section0.xml이 있으면 HWPX)
            try:
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    if 'Contents/section0.xml' in zip_ref.namelist():
                        # HWPX 형식이면 기존 로직 사용
                        print(f"  HWPX 형식으로 인식, 기존 로직 사용")
                    else:
                        # 일반 ZIP 파일이면 내부 파일 추출 (HWP 또는 PDF)
                        extracted_file = self.extract_files_from_zip(filepath)
                        if extracted_file:
                            # 추출된 파일 타입에 따라 처리
                            if extracted_file.lower().endswith('.pdf'):
                                content = self.extract_pdf_content(extracted_file)
                            else:
                                content = self._extract_hwp_content_internal(extracted_file)
                            # 임시 파일 삭제
                            try:
                                if os.path.exists(extracted_file):
                                    os.remove(extracted_file)
                            except:
                                pass
                            return content
                        else:
                            print(f"  ⚠ ZIP 파일에서 HWP 또는 PDF 파일을 찾을 수 없습니다.")
                            return ""
            except Exception as e:
                print(f"  ✗ ZIP 파일 확인 실패: {e}")
                return ""
        
        # 일반 HWP 파일 처리
        return self._extract_hwp_content_internal(filepath)
    
    def _extract_hwp_content_internal(self, filepath: str) -> str:
        """
        HWP 파일에서 텍스트 내용 추출 (내부 메서드)
        
        Args:
            filepath: HWP 파일 경로
            
        Returns:
            추출된 텍스트 내용 (제어 문자 제거됨)
        """
        content = ""
        
        file_size = os.path.getsize(filepath)
        print(f"  파일 크기: {file_size} bytes")
        
        try:
            # pyhwp를 사용하여 텍스트 추출 (우선 시도)
            if PYHWP_AVAILABLE and Hwp5File and TextTransform:
                print(f"  pyhwp 사용 가능, 추출 시도 중...")
                try:
                    text_transform = TextTransform()
                    transform_text = text_transform.transform_hwp5_to_text
                    html_transform = HTMLTransform()
                    html_text = ""
                    text_extraction_success = False
                    
                    with closing(Hwp5File(filepath)) as hwp5file:
                        # 1) 본문 텍스트 추출
                        with tempfile.NamedTemporaryFile(mode='wb+', delete=False) as tmp_txt:
                            tmp_txt_path = tmp_txt.name
                            try:
                                transform_text(hwp5file, tmp_txt)
                                tmp_txt.seek(0)
                                content_bytes = tmp_txt.read()
                                content = content_bytes.decode('utf-8', errors='ignore')
                                text_extraction_success = True
                            except Exception as e:
                                # 텍스트 추출 실패 시 즉시 폴백으로 넘어감
                                print(f"  ✗ pyhwp 텍스트 추출 실패: {e}")
                                content = ""
                                raise  # 예외를 다시 발생시켜 외부 except로 이동
                            finally:
                                try:
                                    os.unlink(tmp_txt_path)
                                except:
                                    pass

                        # 2) HTML 변환 후 <table> 파싱 → Markdown으로 병합 (텍스트 추출 성공한 경우에만)
                        if text_extraction_success and content:
                            try:
                                # HTMLTransform을 사용하여 HTML 변환 (새로운 Hwp5File 인스턴스 필요)
                                with closing(Hwp5File(filepath)) as hwp5file_html:
                                    with tempfile.TemporaryDirectory() as tmp_dir:
                                        html_transform.transform_hwp5_to_dir(hwp5file_html, tmp_dir)
                                        # 변환된 HTML 파일 찾기 (tmp_dir이 닫히기 전에 처리)
                                        html_files = [f for f in os.listdir(tmp_dir) if f.endswith('.html') or f.endswith('.xhtml')]
                                        if html_files:
                                            html_file_path = os.path.join(tmp_dir, html_files[0])
                                            with open(html_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                                html_text = f.read()
                                            
                                            if html_text and html_text.strip():
                                                soup = BeautifulSoup(html_text, 'html.parser')
                                                tables = soup.find_all('table')
                                                print(f"  HTML에서 {len(tables)}개의 표 발견")
                                                if tables:
                                                    md_sections = []
                                                    for t_idx, t in enumerate(tables):
                                                        headers = []
                                                        thead = t.find('thead')
                                                        if thead:
                                                            ths = thead.find_all(['th','td'])
                                                            headers = [th.get_text(strip=True) for th in ths]
                                                        if not headers:
                                                            first_tr = t.find('tr')
                                                            if first_tr:
                                                                headers = [c.get_text(strip=True) for c in first_tr.find_all(['th','td'])]
                                                        rows_md = []
                                                        if headers:
                                                            rows_md.append('| ' + ' | '.join(headers) + ' |')
                                                            rows_md.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
                                                        
                                                        body_rows = t.find_all('tr')
                                                        start_idx = 1 if headers and body_rows else 0
                                                        for tr_idx, tr in enumerate(body_rows):
                                                            if tr_idx < start_idx:
                                                                continue
                                                            cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
                                                            if cells:
                                                                rows_md.append('| ' + ' | '.join(cells) + ' |')
                                                        if rows_md:
                                                            md_sections.append('\n'.join(rows_md))
                                                            print(f"    표 {t_idx + 1}: {len(rows_md)}행 변환 완료")
                                                    
                                                    if md_sections:
                                                        tables_md = '\n\n'.join(md_sections)
                                                        # 본문에서 <표> 플레이스홀더를 실제 표 데이터로 교체
                                                        if '<표>' in content:
                                                            # 각 <표>를 실제 표 데이터로 교체
                                                            parts = content.split('<표>')
                                                            new_content = parts[0]
                                                            for i, part in enumerate(parts[1:], 1):
                                                                if i <= len(md_sections):
                                                                    new_content += '\n\n' + md_sections[i-1] + '\n\n' + part
                                                                else:
                                                                    new_content += '<표>' + part
                                                            content = new_content
                                                        else:
                                                            # <표>가 없으면 끝에 추가
                                                            if content and not content.endswith('\n'):
                                                                content += '\n'
                                                            content += '\n[표]\n\n' + tables_md
                                                        print(f"  총 {len(md_sections)}개의 표를 Markdown으로 변환하여 추가")
                                                else:
                                                    print(f"  HTML에서 표를 찾지 못함")

                            except Exception as e:
                                # HTML 변환 실패 시 표 병합 생략 (본문은 이미 추출됨)
                                print(f"  ⚠ HTML 변환 실패 (본문은 이미 추출됨): {e}")

                    if content and content.strip():
                        print(f"  ✓ pyhwp로 {len(content)}자 추출 완료")
                    else:
                        print(f"  ⚠ pyhwp 추출 결과가 비어있음")
                        content = ""
                except Exception as e:
                    print(f"  ✗ pyhwp 추출 실패: {e}")
                    # traceback은 너무 길어서 제거 (필요시 주석 해제)
                    # import traceback
                    # traceback.print_exc()
                    content = ""
            else:
                print(f"  ⚠ pyhwp 사용 불가 (PYHWP_AVAILABLE={PYHWP_AVAILABLE})")
            
            # pyhwp가 없거나 실패한 경우 폴백 방법 사용
            if not content:
                print(f"  폴백 방법 시도 중...")
                # HWPX 형식 (ZIP 기반)인지 확인
                if zipfile.is_zipfile(filepath):
                    try:
                        with zipfile.ZipFile(filepath, 'r') as zip_ref:
                            if 'Contents/section0.xml' in zip_ref.namelist():
                                xml_content = zip_ref.read('Contents/section0.xml')
                                soup = BeautifulSoup(xml_content, 'xml')
                                content = soup.get_text(separator='\n', strip=True)
                            else:
                                for name in zip_ref.namelist():
                                    if name.endswith('.xml'):
                                        try:
                                            xml_content = zip_ref.read(name)
                                            soup = BeautifulSoup(xml_content, 'xml')
                                            text = soup.get_text(separator='\n', strip=True)
                                            if text:
                                                content += text + "\n"
                                        except:
                                            pass
                    except Exception as e:
                        print(f"  HWPX 파싱 실패: {e}")
                
                # OLE2 형식인 경우 - PrvText 사용
                if not content and olefile and olefile.isOleFile(filepath):
                    try:
                        ole = olefile.OleFileIO(filepath)
                        if ole.exists('PrvText'):
                            try:
                                stream = ole.openstream('PrvText')
                                data = stream.read()
                                prv_text = data.decode('utf-16le', errors='ignore')
                                if prv_text and len(prv_text.strip()) > 10:
                                    content = prv_text
                                    print(f"  PrvText에서 {len(content)}자 추출 (폴백)")
                            except:
                                pass
                        ole.close()
                    except Exception as e:
                        print(f"  OLE2 파싱 실패: {e}")
            
            # 제어 문자 및 특수 문자 제거 (엑셀 호환을 위해)
            if content:
                # NULL 바이트 제거
                content = content.replace('\x00', '')
                # XML 호환되지 않는 문자 제거 (제어 문자, 단 \n, \r, \t는 유지)
                content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
                # 연속된 공백 정리
                content = re.sub(r'[ \t]+', ' ', content)
                # 연속된 줄바꿈 정리
                content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
                print(f"  최종 추출된 내용: {len(content)}자")
            else:
                print(f"  ✗ 모든 추출 방법 실패 - 빈 내용 반환")
            
            return content.strip()
        except Exception as e:
            print(f"  ✗ HWP 파일 읽기 오류: {filepath} - {e}")
            import traceback
            traceback.print_exc()
            return ""

