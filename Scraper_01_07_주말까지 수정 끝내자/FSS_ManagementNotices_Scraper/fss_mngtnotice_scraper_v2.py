# fss_mngtnotice_scraper_v2.py
"""
금융감독원(FSS) 경영유의사항 공시 스크래퍼 v2
- common/file_extractor.py의 FileExtractor를 사용하여 PDF 추출
- KoFIU_Scraper/extract_metadata.py의 함수들을 재사용 (패턴 변경: 3. 조치내용, 4. 조치대상사실)
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
import platform

# Windows 콘솔 인코딩 설정
if platform.system() == 'Windows':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)  # UTF-8 코드 페이지
        kernel32.SetConsoleCP(65001)
    except:
        pass

# common 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.file_extractor import FileExtractor

# OCR 추출 모듈 import
#from ocr_extractor import OCRExtractor
from FSS_ManagementNotices_Scraper.ocr_extractor import OCRExtractor

# 같은 폴더의 extract_metadata 모듈에서 함수 import (FSS_ManagementNotices 전용)
from FSS_ManagementNotices_Scraper.extract_metadata import (
    extract_metadata_from_content as extract_metadata_from_content_normal,
    extract_sanction_details as extract_sanction_details_base,
    extract_incidents as extract_incidents_base,
    format_date_to_iso
)

# OCR 전용 extract_metadata 모듈 import
try:
    from FSS_ManagementNotices_Scraper.extract_metadata_ocr import (
        extract_metadata_from_content as extract_metadata_from_content_ocr,
        extract_sanction_details as extract_sanction_details_ocr_base,
        extract_incidents as extract_incidents_ocr_base
    )    
    OCR_MODULE_AVAILABLE = True
except ImportError:
    OCR_MODULE_AVAILABLE = False
    # OCR 모듈이 없으면 일반 함수를 사용
    extract_metadata_from_content_ocr = extract_metadata_from_content_normal
    extract_sanction_details_ocr_base = extract_sanction_details_base
    extract_incidents_ocr_base = extract_incidents_base

sys.stdout.reconfigure(encoding='utf-8')


# ManagementNotices 전용 패턴으로 래핑
def extract_sanction_details_management(content):
    """
    경영유의사항용 제재내용 추출 (3. 조치내용 패턴 우선)
    """
    if not content or content.startswith('['):
        return ""
    
    # 3. 조치내용 패턴을 우선으로 검색
    sanction_patterns = [
        # "3. 조치내용" 형식 (우선)
        r'3\.\s*조\s*치\s*내\s*용',
        r'3\.\s*조치내용',
        r'3\.\s*조치\s*내용',
        r'3\s*\.\s*조\s*치\s*내\s*용',
        # "3. 제재조치내용" 형식
        r'3\.\s*제\s*재\s*조\s*치\s*내\s*용',
        r'3\.\s*제재조치내용',
        r'3\.\s*제재조치\s*내용',
        # "3. 제재내용" 형식
        r'3\.\s*제\s*재\s*내\s*용',
        r'3\.\s*제재내용',
        r'3\.\s*제재\s*내용',
        # "3. 처분내용" 형식
        r'3\.\s*처\s*분\s*내\s*용',
        r'3\.\s*처분내용',
        r'3\.\s*처분\s*내용',
    ]
    
    start_pos = None
    for pattern in sanction_patterns:
        match = re.search(pattern, content)
        if match:
            start_pos = match.end()
            break
    
    if start_pos is None:
        return ""
    
    # 다음 항목(4. 로 시작) 또는 문서 끝까지의 내용 추출
    remaining_content = content[start_pos:]
    
    # 다음 번호 항목(4., 5. 등) 찾기
    next_section_match = re.search(r'\n\s*[4-9]\.\s*[가-힣]', remaining_content)
    if next_section_match:
        table_content = remaining_content[:next_section_match.start()]
    else:
        table_content = remaining_content
    
    # 표 데이터 파싱: 줄바꿈으로 분리
    lines = table_content.strip().split('\n')
    
    # 빈 줄 및 공백만 있는 줄 제거
    lines = [line.strip() for line in lines if line.strip()]
    
    if len(lines) <= 1:
        # 제목행만 있거나 데이터가 없는 경우
        return ""
    
    # 첫 번째 줄(제목행) 제외하고 나머지 반환
    data_lines = lines[1:]
    
    # 데이터 행들을 줄바꿈으로 연결
    result = '\n'.join(data_lines)
    
    # "*조치사유", "*제재사유" 등 표 이후 텍스트 제거
    reason_patterns = [
        r'\*?\s*조\s*치\s*사\s*유',
        r'\*?\s*제\s*재\s*사\s*유',
        r'\*?\s*조\s*치\s*대\s*상\s*사\s*실',
        r'\*?\s*제\s*재\s*대\s*상\s*사\s*실',
    ]
    for pattern in reason_patterns:
        reason_match = re.search(pattern, result)
        if reason_match:
            result = result[:reason_match.start()].strip()
            break
    
    # 페이지 번호 제거
    from extract_metadata import remove_page_numbers
    result = remove_page_numbers(result)
    
    return result.strip()


def extract_incidents_management(content):
    """
    경영유의사항용 사건 추출 (4. 조치대상사실 패턴 우선)
    extract_incidents_base를 재사용하되, 패턴 우선순위 조정
    """
    if not content or content.startswith('['):
        return {}
    
    # OCR 텍스트 전처리: OCR 오류만 수정 (정상 띄어쓰기는 보존)
    # extract_metadata의 collapse_split_syllables는 OCR 오류만 수정하므로 사용
    # 하지만 여기서는 원본을 그대로 사용하여 띄어쓰기 보존
    # content = collapse_split_syllables(content)  # 띄어쓰기 보존을 위해 주석 처리
    
    # 4. 조치대상사실 패턴을 우선으로 검색하여 섹션 시작 위치 찾기
    section4_patterns = [
        # "4. 조치대상사실" 형식 (우선)
        r'4\.\s*조\s*치\s*대\s*상\s*사\s*실',
        r'4\.\s*조치대상사실',
        r'4\.\s*조치대상\s*사실',
        # "4. 제재대상사실" 형식 (fallback)
        r'4\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'4\.\s*제재대상사실',
        r'4\.\s*제재대상\s*사실',
    ]
    
    section_start = -1
    for pattern in section4_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            section_start = match.end()
            break
    
    if section_start == -1:
        # 패턴을 찾지 못하면 기본 함수 사용
        return extract_incidents_base(content)
    
    # 4번 항목 이후의 내용만 추출
    section_text = content[section_start:]
    
    # 다음 번호 항목(5., 6. 등) 또는 문서 끝까지
    next_section_match = re.search(r'\n\s*[5-9]\.\s*[가-힣]', section_text)
    if next_section_match:
        section_text = section_text[:next_section_match.start()]
    
    # 섹션 시작 부분에 "4. 조치대상사실"을 추가하여 기본 함수가 정상 작동하도록
    processed_content = "4. 조치대상사실\n" + section_text
    
    # 기본 함수 호출
    return extract_incidents_base(processed_content)


class FSSManagementNoticesScraperV2:
    """금융감독원 경영유의사항 공시 스크래퍼 (FileExtractor 사용)"""
    
    def __init__(self):
        self.base_url = "https://www.fss.or.kr"
        self.list_url_template = "https://www.fss.or.kr/fss/job/openInfoImpr/list.do?menuNo=200483&pageIndex={page}&sdate={sdate}&edate={edate}&searchCnd=4&searchWrd="
        
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
        
        # 업종 분류 매핑 로드
        self.industry_map = self._load_industry_classification()
        
        # OCR 관련 초기화
        self.ocr_extractor = OCRExtractor()  # 하이브리드 OCR 사용
        self.min_text_length = 200  # 최소 텍스트 길이 (미만이면 OCR 시도)
        self.ocr_initialized = False
        self.ocr_available = False
    
    def _initialize_ocr(self):
        """OCR 초기화 (Tesseract 경로 설정)"""
        if self.ocr_initialized:
            return
        self.ocr_initialized = True
        
        if not PYMUPDF_AVAILABLE or not PYTESSERACT_AVAILABLE:
            print("  ※ OCR 모듈(PyMuPDF, pytesseract, Pillow) 중 일부가 설치되어 있지 않아 OCR을 사용할 수 없습니다.")
            self.ocr_available = False
            return
        
        # Windows에서 Tesseract 경로 찾기
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\USER\AppData\Local\Tesseract-OCR\tesseract.exe',
            r'C:\Users\USER\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
        ]
        
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                self.ocr_available = True
                print(f"  OCR 사용 준비 완료 (Tesseract 경로: {path})")
                return
        
        print("  ※ Tesseract 실행 파일을 찾을 수 없어 OCR을 사용할 수 없습니다.")
        self.ocr_available = False
    
    def _ocr_pdf(self, file_path):
        """OCR을 사용하여 PDF에서 텍스트 추출 (이미지 기반 PDF용)"""
        if not self.ocr_available:
            return None
        
        try:
            print(f"  OCR 추출 시도 중...")
            doc = fitz.open(str(file_path))
            texts = []
            
            for page_num, page in enumerate(doc):
                # 페이지를 이미지로 변환 (400 DPI - 해상도 증가로 정확도 향상)
                mat = fitz.Matrix(400 / 72, 400 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert('L')
                
                # 이미지 전처리: 대비 향상 (보수적 접근)
                from PIL import ImageEnhance
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.2)  # 대비 20% 증가
                
                # 여러 OCR 설정 시도 (더 다양한 PSM 모드 추가)
                configs = [
                    ('kor+eng', '--oem 3 --psm 6'),   # 단일 블록
                    ('kor+eng', '--oem 3 --psm 4'),   # 단일 컬럼
                    ('kor+eng', '--oem 3 --psm 11'),  # 희미한 텍스트
                    ('kor', '--oem 3 --psm 6'),
                    ('kor', '--oem 3 --psm 4'),
                    ('kor', '--oem 3 --psm 11'),
                ]
                
                best_text = ''
                best_score = 0
                
                for lang, cfg in configs:
                    try:
                        candidate = pytesseract.image_to_string(image, lang=lang, config=cfg)
                        if candidate:
                            # 결과 품질 평가: 한글 문자 비율과 길이를 고려
                            korean_chars = sum(1 for c in candidate if '\uAC00' <= c <= '\uD7A3')
                            total_chars = len(candidate.replace(' ', '').replace('\n', ''))
                            korean_ratio = korean_chars / total_chars if total_chars > 0 else 0
                            
                            # 점수: 길이 + 한글 비율 가중치
                            score = len(candidate) + (korean_ratio * 1000)
                            
                            if score > best_score:
                                best_text = candidate
                                best_score = score
                    except Exception:
                        continue
                
                if best_text:
                    texts.append(best_text)
                    print(f"    페이지 {page_num + 1}: {len(best_text)}자 추출")
            
            doc.close()
            
            full_text = '\n'.join(t.strip() for t in texts if t).strip()
            if full_text:
                print(f"  ✓ OCR로 {len(full_text)}자 추출 완료")
            return full_text if full_text else None
            
        except Exception as e:
            print(f"  ✗ OCR 처리 중 오류: {e}")
            return None
    
    def _load_industry_classification(self):
        """금융회사별 업종분류 CSV 파일 로드 (KoFIU_Scraper의 파일 사용)"""
        industry_map = {}
        # KoFIU_Scraper의 업종분류 CSV 파일 경로
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, '..', 'KoFIU_Scraper', '금융회사별_업종분류.csv')
        
        try:
            # utf-8-sig 인코딩 사용하여 BOM 자동 처리
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    company = row.get('금융회사명', '').strip()
                    industry = row.get('업종', '').strip()
                    if company and industry:
                        industry_map[company] = industry
            print(f"  업종 분류 매핑 로드 완료: {len(industry_map)}개")
        except Exception as e:
            print(f"  업종 분류 CSV 로드 실패: {e}")
        
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
    
    def get_page(self, url, retry=3):
        """페이지 가져오기 (재시도 로직 포함)"""
        for attempt in range(retry):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response
            except Exception as e:
                if attempt < retry - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  요청 실패 (재시도 {attempt + 1}/{retry}): {e}")
                    time.sleep(wait_time)
                else:
                    print(f"  요청 최종 실패: {e}")
                    raise
    
    def is_pdf_url(self, url: str) -> bool:
        """URL이 직접 PDF 파일인지 확인"""
        if not url:
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith('.pdf') or 'file=' in parsed.query.lower()
    
    def derive_filename(self, url: str, link_text: str = "") -> str:
        """URL 또는 링크 텍스트에서 파일명 추출"""
        candidates = []
        
        if link_text and link_text.strip():
            name = link_text.strip()
            if name.lower().endswith('.pdf'):
                candidates.append(name)
        
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        if 'file' in query_params:
            file_param = query_params['file'][0]
            candidates.append(unquote(file_param))
        
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
            tuple: (추출된 내용, 문서유형, 파일다운로드URL)
        """
        try:
            # PDF URL인 경우 직접 다운로드
            if self.is_pdf_url(detail_url):
                filename = self.derive_filename(detail_url, link_text)
                print(f"  PDF 다운로드 시도: {filename}")
                
                file_url = detail_url  # PDF URL이 직접 파일 다운로드 URL
                
                # FileExtractor로 파일 다운로드
                file_path, actual_filename = self.file_extractor.download_file(
                    url=detail_url,
                    filename=filename,
                    referer=self.base_url
                )
                
                if file_path and os.path.exists(file_path):
                    # FileExtractor로 PDF 내용 추출
                    content = self.file_extractor.extract_pdf_content(file_path)
                    doc_type = 'PDF-텍스트'
                    ocr_attempted = False
                    
                    # 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                    if not content or len(content.strip()) < self.min_text_length:
                        print(f"  텍스트 추출 실패 또는 부족 ({len(content.strip()) if content else 0}자 < {self.min_text_length}자), OCR 시도...")
                        if self.ocr_extractor.is_available():
                            ocr_attempted = True
                            ocr_text = self.ocr_extractor.extract_text(file_path, mode='auto')
                            if ocr_text and len(ocr_text.strip()) >= self.min_text_length:
                                # OCR 결과가 있고 최소 길이 이상이면 사용
                                content = ocr_text
                                doc_type = 'PDF-OCR'
                                print(f"  ✓ OCR 추출 성공 ({len(ocr_text)}자)")
                            elif ocr_text:
                                # OCR 결과가 있지만 너무 짧은 경우도 사용 (최소한 OCR은 시도했으므로)
                                content = ocr_text
                                doc_type = 'PDF-OCR'
                                print(f"  ⚠ OCR 추출 완료 (길이 부족: {len(ocr_text)}자)")
                            else:
                                print(f"  ✗ OCR 추출 실패 (결과 없음)")
                        else:
                            print(f"  ✗ OCR 사용 불가 (is_available() = False)")
                    
                    # 임시 파일 삭제
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    
                    if content and content.strip():
                        print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                        return content, doc_type, file_url
                    else:
                        return "[PDF 파일이지만 텍스트 추출 실패]", 'PDF-OCR필요', file_url
                else:
                    return "[파일 다운로드 실패]", '오류', file_url
            
            # 일반 페이지에서 첨부파일 링크 찾기
            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.text, 'lxml')
            
            all_links = soup.find_all('a', href=True)
            file_url = ''  # 파일 다운로드 URL 초기화
            
            for link in all_links:
                href = link.get('href', '')
                link_text_inner = link.get_text(strip=True)
                
                # PDF 파일 링크 찾기 (다양한 패턴)
                if '/fss.hpdownload' in href or 'download' in href.lower() or '.pdf' in href.lower():
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
                        # URL 파라미터에서 파일명 추출
                        if 'file=' in href:
                            filename = unquote(href.split('file=')[-1].split('&')[0])
                    
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
                            doc_type = 'PDF-텍스트'
                            ocr_attempted = False
                            
                            # 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                            if not content or len(content.strip()) < self.min_text_length:
                                print(f"  텍스트 추출 실패 또는 부족 ({len(content.strip()) if content else 0}자 < {self.min_text_length}자), OCR 시도...")
                                self._initialize_ocr()
                                if self.ocr_available:
                                    ocr_attempted = True
                                    ocr_text = self._ocr_pdf(file_path)
                                    if ocr_text and len(ocr_text.strip()) >= self.min_text_length:
                                        # OCR 결과가 있고 최소 길이 이상이면 사용
                                        content = ocr_text
                                        doc_type = 'PDF-OCR'
                                        print(f"  ✓ OCR 추출 성공 ({len(ocr_text)}자)")
                                    elif ocr_text:
                                        # OCR 결과가 있지만 너무 짧은 경우도 사용 (최소한 OCR은 시도했으므로)
                                        content = ocr_text
                                        doc_type = 'PDF-OCR'
                                        print(f"  ⚠ OCR 추출 완료 (길이 부족: {len(ocr_text)}자)")
                                    else:
                                        print(f"  ✗ OCR 추출 실패 (결과 없음)")
                                else:
                                    print(f"  ✗ OCR 사용 불가 (ocr_available = False)")
                            
                            # 임시 파일 삭제
                            try:
                                os.remove(file_path)
                            except:
                                pass
                            
                            if content and content.strip():
                                print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                                return content, doc_type, file_url
                            else:
                                return f"[PDF 파일이지만 텍스트 추출 실패: {filename}]", 'PDF-OCR필요', file_url
                        else:
                            # 임시 파일 삭제
                            try:
                                os.remove(file_path)
                            except:
                                pass
                            return f"[{os.path.splitext(file_path)[1]} 파일은 현재 지원되지 않습니다: {filename}]", '기타첨부파일', file_url
                    break
            
            return "[첨부파일을 찾을 수 없습니다]", '첨부없음', ''
            
        except Exception as e:
            print(f"  첨부파일 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return f"[오류: {str(e)}]", '오류', ''
    
    def scrape_list_page(self, page_index, sdate='', edate=''):
        """목록 페이지 스크래핑"""
        url = self.list_url_template.format(page=page_index, sdate=sdate, edate=edate)
        
        print(f"\n페이지 {page_index} 스크래핑 중...")
        response = self.get_page(url)
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 테이블 찾기
        table = soup.find('table')
        if not table:
            print(f"  페이지 {page_index}: 테이블을 찾을 수 없습니다")
            return []
        
        rows = table.find_all('tr')[1:]  # 헤더 제외
        items = []
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 5:  # ManagementNotices는 조회수가 없으므로 5개 셀
                continue
            
            try:
                # 번호, 제재대상기관, 제재조치요구일, 제재조치요구내용(링크), 관련부서
                number = cells[0].get_text(strip=True)
                institution = cells[1].get_text(strip=True)
                date = cells[2].get_text(strip=True)
                content_cell = cells[3]
                department = cells[4].get_text(strip=True)
                
                # 링크 찾기
                link = content_cell.find('a', href=True)
                detail_url = None
                link_text = ""
                if link:
                    detail_url = urljoin(self.base_url, link['href'])
                    link_text = link.get_text(strip=True)
                
                items.append({
                    '제재대상기관': institution,
                    '제재조치요구일': date,
                    '관련부서': department,
                    '조회수': '-',  # ManagementNotices는 조회수 없음
                    '상세페이지URL': detail_url,
                    '_link_text': link_text
                })
                
            except Exception as e:
                print(f"  행 처리 중 오류: {e}")
                continue
        
        print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
        return items
    
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
        
        # 변환 실패 시 원본 반환 (경고는 나중에 처리)
        return date_str
    
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
        print("금융감독원 경영유의사항 공시 스크래핑 시작 (v2 - FileExtractor 사용)")
        if limit:
            print(f"  수집 제한: {limit}개")
        if after_date:
            print(f"  날짜 필터: {after_date} 이후")
        if sdate_normalized or edate_normalized:
            print(f"  검색 기간: {sdate_normalized or '전체'} ~ {edate_normalized or '전체'}")
        else:
            print(f"  검색 기간: 전체")
        print("=" * 60)
        
        # after_date 문자열을 datetime으로 변환
        after_datetime = self.parse_date(after_date) if after_date else None
        
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
            
            items = self.scrape_list_page(page, sdate=sdate_normalized, edate=edate_normalized)
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
                    post_date_str = item.get('제재조치요구일', '')
                    post_datetime = self.parse_date(post_date_str)
                    
                    if post_datetime:
                        if post_datetime < after_datetime:
                            # 날짜순 정렬이므로, 이 날짜보다 이전이면 더 이상 수집 불필요
                            print(f"  날짜 {post_date_str}가 기준일({after_date}) 이전이므로 건너뜀")
                            stop_by_date = True
                            break
                    
                detail_url = item.get('상세페이지URL')
                if detail_url and detail_url in seen_urls:
                    continue
                if detail_url:
                    seen_urls.add(detail_url)
                new_items.append(item)
            
            if new_items:
                all_items.extend(new_items)
            
            if not items:
                break
            
            time.sleep(1)
            page += 1
            
            # 최대 100페이지까지
            if page > 100:
                print(f"\n최대 페이지 수(100)에 도달하여 수집을 종료합니다.")
                break
        
        print(f"\n총 {len(all_items)}개 항목 수집 완료")
        
        print("\n상세 정보 및 첨부파일 추출 시작...")
        
        for idx, item in enumerate(all_items, 1):
            link_text = item.pop('_link_text', '')
            institution_from_list = item.get('제재대상기관', '')
            
            print(f"\n[{idx}/{len(all_items)}] {institution_from_list or link_text or 'N/A'} 처리 중...")
            
            if item.get('상세페이지URL'):
                attachment_content, doc_type, file_download_url = self.extract_attachment_content(
                    item['상세페이지URL'], 
                    link_text
                )
                item['제재조치내용'] = attachment_content
                item['문서유형'] = doc_type
                item['파일다운로드URL'] = file_download_url
                
                # OCR 추출 여부 설정
                is_ocr = doc_type == 'PDF-OCR'
                item['OCR추출여부'] = '예' if is_ocr else '아니오'
                
                # PDF 내용에서 금융회사명, 제재조치일, 제재내용 추출
                if attachment_content and not attachment_content.startswith('['):
                    # OCR로 추출한 경우 OCR 전용 함수 사용
                    
                    if is_ocr and OCR_MODULE_AVAILABLE:
                        extract_metadata_fn = extract_metadata_from_content_ocr
                        extract_sanction_fn = extract_sanction_details_management  # ManagementNotices 전용
                        extract_incidents_fn = extract_incidents_management  # ManagementNotices 전용
                        print(f"  OCR 텍스트로 메타데이터 추출 중...")
                    else:
                        extract_metadata_fn = extract_metadata_from_content_normal
                        extract_sanction_fn = extract_sanction_details_management  # ManagementNotices 전용
                        extract_incidents_fn = extract_incidents_management  # ManagementNotices 전용
                    
                    institution, sanction_date = extract_metadata_fn(attachment_content)
                    
                    # 금융회사명: PDF에서 추출 실패 시 목록에서 가져온 값 사용
                    if institution:
                        item['금융회사명'] = institution
                    elif institution_from_list:
                        item['금융회사명'] = institution_from_list
                    
                    # 업종 매핑
                    final_institution = item.get('금융회사명', institution_from_list)
                    industry = self.get_industry(final_institution)
                    item['업종'] = industry
                    print(f"  금융회사명: {final_institution} (업종: {industry})")
                    
                    if sanction_date:
                        item['제재조치일'] = sanction_date
                        print(f"  제재조치일 추출: {sanction_date}")
                    
                    # 제재내용 (표 데이터) 추출 - ManagementNotices 전용 함수 사용
                    sanction_details = extract_sanction_fn(attachment_content)
                    if sanction_details:
                        item['제재내용'] = sanction_details
                        print(f"  제재내용 추출: {len(sanction_details)}자")
                    
                    # 사건 제목/내용 추출 (4번 항목) - ManagementNotices 전용 함수 사용
                    incidents = extract_incidents_fn(attachment_content)
                    if incidents:
                        item.update(incidents)
                        incident_count = len([k for k in incidents.keys() if k.startswith('제목')])
                        print(f"  사건 추출: {incident_count}건")
                else:
                    # PDF 추출 실패 시 목록에서 가져온 정보 사용
                    if institution_from_list:
                        item['금융회사명'] = institution_from_list
                        item['업종'] = self.get_industry(institution_from_list)
                    else:
                        item['업종'] = '기타'
            else:
                item['제재조치내용'] = "[상세 페이지 URL이 없습니다]"
                item['문서유형'] = 'URL없음'
                item['OCR추출여부'] = '아니오'
                item['파일다운로드URL'] = ''
                if institution_from_list:
                    item['금융회사명'] = institution_from_list
                    item['업종'] = self.get_industry(institution_from_list)
                else:
                    item['업종'] = '기타'
            
            # OCR추출여부 필드가 없는 경우 기본값 설정
            if 'OCR추출여부' not in item:
                item['OCR추출여부'] = '아니오'
            
            # 업종 필드가 없는 경우 기타로 설정
            if '업종' not in item:
                item['업종'] = '기타'
            
            self.results.append(item)
            time.sleep(1)
        
        # 리소스 정리
        self.close()
        
        return self.results
    
    def close(self):
        """리소스 정리"""
        try:
            if self.temp_dir.exists():
                for file in self.temp_dir.iterdir():
                    try:
                        file.unlink()
                    except:
                        pass
                try:
                    self.temp_dir.rmdir()
                except:
                    pass
        except:
            pass
    
    def _clean_content(self, text):
        """
        텍스트에서 불필요한 줄바꿈만 제거 (띄어쓰기는 보존)
        - 특수 마커(ㅇ, □, -, (1) 등) 앞의 줄바꿈은 유지
        - 그 외 줄바꿈은 공백으로 대체 (단, 원본 띄어쓰기는 보존)
        - 연속된 줄바꿈만 처리하고 일반 공백은 그대로 유지
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
        
        # 나머지 줄바꿈을 공백으로 대체 (단, 연속된 줄바꿈만 처리)
        # 단일 줄바꿈은 공백으로, 연속된 줄바꿈은 하나의 공백으로
        result = re.sub(r'\n+', ' ', result)
        
        # 임시 토큰을 원래 마커로 복원
        for placeholder, replacement in placeholders.items():
            result = result.replace(placeholder, replacement)
        
        # 연속된 공백은 정리하되, 원본에 있던 공백은 보존
        # 단, 3개 이상 연속된 공백만 하나로 정리 (2개 공백은 보존)
        result = re.sub(r' {3,}', ' ', result)
        
        # 앞뒤 공백 제거
        result = result.strip()
        
        return result
    
    def _post_process_content(self, text):
        """
        '내용' 필드 후처리
        - <관련법규>, <관련규정> 앞에 줄바꿈 추가 (공백 포함 패턴도 처리)
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
            # 기본 필드 추출 (줄바꿈 정리 적용)
            # 제재조치일 포맷팅 (PDF에서 추출한 값 또는 목록에서 가져온 제재조치요구일)
            sanction_date = item.get('제재조치일', item.get('제재조치요구일', ''))
            if sanction_date:
                # format_date_to_iso 함수로 YYYY-MM-DD 형식으로 변환
                sanction_date = format_date_to_iso(sanction_date)
            
            # 제재내용: 후처리 적용
            raw_sanction_content = item.get('제재내용', '')
            if raw_sanction_content:
                cleaned_sanction_content = self._clean_content(raw_sanction_content)
                processed_sanction_content = self._post_process_sanction_content(cleaned_sanction_content)
            else:
                processed_sanction_content = ''
            
            base_data = {
                '구분': '경영유의',  # ManagementNotices 전용
                '출처': '금융감독원',
                '금융회사명': item.get('금융회사명', item.get('제재대상기관', '')),
                '업종': item.get('업종', '기타'),
                '제재조치일': sanction_date,
                '제재내용': processed_sanction_content,  # 후처리 적용
                '파일다운로드URL': item.get('파일다운로드URL', ''),
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
                    
                    # 내용: 후처리 적용
                    if raw_content:
                        cleaned_content = self._clean_content(raw_content)
                        processed_content = self._post_process_content(cleaned_content)
                    else:
                        processed_content = ''
                    
                    split_results.append({
                        **base_data,
                        '제목': title,
                        '내용': processed_content  # 후처리 적용
                    })
        
        return split_results
    
    def save_results(self, filename='fss_results.json'):
        """결과 저장 (JSON, CSV) - output 폴더에 저장"""
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
            csv_filename = base_filename.replace('.json', '.csv')
            csv_filepath = os.path.join(output_dir, csv_filename)
            
            if split_results:
                # 필드 순서: 구분, 출처, 업종, 금융회사명, 제목, 내용, 제재내용, 제재조치일, 파일다운로드URL, OCR추출여부
                fieldnames = ['구분', '출처', '업종', '금융회사명', '제목', '내용', '제재내용', '제재조치일', '파일다운로드URL', 'OCR추출여부']
                
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
# 독립 실행용 fss_mngtNotice_check
# -------------------------------------------------
from common.constants import URLStatus, LegalDocProvided
from common.common_http import check_url_status
from common.url_health_mapper import map_urlstatus_to_health_error
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error


def fss_mngtnotice_check() -> dict:
    """
    금융감독원 경영유의사항(행정지도·행정작용) 헬스체크
    - HealthErrorType 내부 raise
    - Alert 연동 가능 구조
    """

    LIST_URL = "https://www.fss.or.kr/fss/job/openInfoImpr/list.do?menuNo=200483&pageIndex=1"

    result = base_health_output(
        auth_src="금융감독원-경영유의사항",
        scraper_id="FSS_MNGTNOTICE",
        target_url=LIST_URL,
    )

    try:
        scraper = FSSManagementNoticesScraperV2()
        session = scraper.session

        # ======================================================
        # 0️⃣ HTTP 접근성 사전 체크
        # ======================================================
        http_result = check_url_status(LIST_URL)

        result["checks"]["http"] = {
            "ok": http_result["status"].name == "OK",
            "status_code": http_result["http_code"],
        }

        if http_result["status"] != URLStatus.OK:
            raise HealthCheckError(
                map_urlstatus_to_health_error(http_result["status"]),
                "목록 페이지 HTTP 접근 실패",
                LIST_URL,
            )
        
        # ======================================================
        # 1️⃣ 목록 페이지
        # ======================================================
        items = scraper.scrape_list_page(page_index=1, sdate='', edate='')
        if not items:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "목록 데이터 없음",
                selector="table > tbody > tr"
            )

        first = items[0]

        result["checks"]["list"] = {
            "ok": True,
            "count": 1,
            "title": first.get("제재대상기관", "")
        }

        # ======================================================
        # 2️⃣ 상세 페이지
        # ======================================================
        detail_url = first.get("상세페이지URL")
        if not detail_url:
            raise HealthCheckError(
                HealthErrorType.NO_DETAIL_URL,
                "상세 페이지 URL 누락",
                field="상세페이지URL"
            )

        try:
            resp = session.get(detail_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            raise HealthCheckError(
                HealthErrorType.HTTP_ERROR,
                f"상세 페이지 접근 실패: {e}",
                url=detail_url
            )

        result["checks"]["detail"] = {
            "ok": True,
            "url": detail_url,
            "content_length": len(resp.text)
        }

        # ======================================================
        # 3️⃣ 첨부파일 + PDF/OCR
        # ======================================================
        content, doc_type, file_url = scraper.extract_attachment_content(
            detail_url,
            first.get("_link_text", "")
        )

        # 첨부파일이 있는 경우만 체크 생성
        if file_url:
            try:
                head = session.head(file_url, timeout=15, allow_redirects=True)
                if head.status_code >= 400:
                    raise HealthCheckError(
                        HealthErrorType.FILE_DOWNLOAD_FAILED,
                        f"첨부파일 접근 실패 (HTTP {head.status_code})",
                        url=file_url
                    )

                result["checks"]["file_download"] = {
                    "url": file_url,
                    "success": True,
                    "message": "첨부파일 다운로드 가능"
                }

            except HealthCheckError:
                raise
            except Exception as e:
                raise HealthCheckError(
                    HealthErrorType.FILE_DOWNLOAD_FAILED,
                    str(e),
                    url=file_url
                )

        # PDF / OCR 파싱 실패
        if doc_type in ("PDF-OCR필요", "오류"):
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "PDF/OCR 본문 파싱 실패",
                url=file_url
            )

        if doc_type:
            result["checks"]["content_parse"] = {
                "success": True,
                "doc_type": doc_type,
                "message": f"{doc_type} 본문 파싱 가능"
            }

        result["ok"] = True
        result["status"] = "OK"

    except HealthCheckError as he:
        apply_health_error(result, he)

    except Exception as e:
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.UNKNOWN,
                str(e)
            )
        )

    finally:
        try:
            scraper.close()
        except:
            pass

    return result

# ==================================================
# scheduler call
# ==================================================
def run():
    scraper = FSSManagementNoticesScraperV2()
    results = scraper.scrape_all()
    scraper.save_results()
    
    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)
    
if __name__ == "__main__":
    # 기본 검색 기간 설정 (오늘 날짜 기준 일주일 전 ~ 오늘)
    today = datetime.now()
    default_edate = today.strftime('%Y-%m-%d')
    # 일주일 전 날짜 계산
    default_sdate = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    
    parser = argparse.ArgumentParser(description="금융감독원 경영유의사항 공시 스크래퍼 v2")
    parser.add_argument('--limit', type=int, default=None, help='수집할 최대 항목 수 (기본: 전체)')
    parser.add_argument('--sdate', type=str, default=default_sdate, help=f'검색 시작일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_sdate})')
    parser.add_argument('--edate', type=str, default=default_edate, help=f'검색 종료일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_edate})')
    parser.add_argument('--after', type=str, default=None, help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD)')
    parser.add_argument('--output', type=str, default='fss_results.json', help='출력 파일명 (기본: fss_results.json)')
    
    parser.add_argument(
        '--check',
        action='store_true',
        help='헬스체크 모드 실행 (스크래핑 미수행)'
    )

    args = parser.parse_args()
    
    # ===============================
    # 헬스체크 모드
    # ===============================
    if args.check:
        health_result = fss_mngtnotice_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)
   
    scraper = FSSManagementNoticesScraperV2()   
    results = scraper.scrape_all(
        limit=args.limit,
        after_date=args.after,
        sdate=args.sdate,
        edate=args.edate
    )
    scraper.save_results(filename=args.output)
    
    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)
    
    # 기본값으로 실행했을 때 데이터가 없는 경우 메시지 출력
    if len(results) == 0 and args.sdate == default_sdate and args.edate == default_edate and args.after is None:
        print("\n일주일 이내 업데이트된 게시물이 없습니다.")

