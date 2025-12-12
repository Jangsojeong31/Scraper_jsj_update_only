"""
금융감독원(FSS) 제재조치 현황 스크래퍼 v2
- common/file_extractor.py의 FileExtractor를 사용하여 PDF 추출
- KoFIU_Scraper/extract_metadata.py의 함수들을 재사용
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
from datetime import datetime
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

# KoFIU_Scraper의 extract_metadata 모듈에서 함수 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'KoFIU_Scraper'))
from extract_metadata import (
    extract_metadata_from_content as extract_metadata_from_content_normal,
    extract_sanction_details as extract_sanction_details_normal,
    extract_incidents as extract_incidents_normal
)

# OCR 전용 extract_metadata 모듈 import
try:
    from extract_metadata_ocr import (
        extract_metadata_from_content as extract_metadata_from_content_ocr,
        extract_sanction_details as extract_sanction_details_ocr,
        extract_incidents as extract_incidents_ocr
    )
    OCR_MODULE_AVAILABLE = True
except ImportError:
    OCR_MODULE_AVAILABLE = False
    # OCR 모듈이 없으면 일반 함수를 사용
    extract_metadata_from_content_ocr = extract_metadata_from_content_normal
    extract_sanction_details_ocr = extract_sanction_details_normal
    extract_incidents_ocr = extract_incidents_normal

sys.stdout.reconfigure(encoding='utf-8')


class FSSScraperV2:
    """금융감독원 제재조치 현황 스크래퍼 (FileExtractor 사용)"""
    
    def __init__(self):
        self.base_url = "https://www.fss.or.kr"
        self.list_url_template = "https://www.fss.or.kr/fss/job/openInfo/list.do?menuNo=200476&pageIndex={page}&sdate={sdate}&edate={edate}&searchCnd=4&searchWrd="
        
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
                # 페이지를 이미지로 변환 (300 DPI)
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert('L')
                
                # 여러 OCR 설정 시도
                configs = [
                    ('kor+eng', '--oem 3 --psm 6'),
                    ('kor+eng', '--oem 3 --psm 4'),
                    ('kor', '--oem 3 --psm 6'),
                    ('kor', '--oem 3 --psm 4'),
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
    
    def close(self):
        """리소스 정리"""
        # 임시 파일 정리
        try:
            for file in self.temp_dir.iterdir():
                file.unlink()
            self.temp_dir.rmdir()
            print("\n임시 파일 정리 완료")
        except Exception:
            pass

    def get_page(self, url, retry=3):
        """HTTP GET 요청 (재시도 로직 포함)"""
        for i in range(retry):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                response.encoding = 'utf-8'
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
                    referer=self.base_url
                )
                
                if file_path and os.path.exists(file_path):
                    # FileExtractor로 PDF 내용 추출
                    content = self.file_extractor.extract_pdf_content(file_path)
                    doc_type = 'PDF-텍스트'
                    
                    # 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                    if not content or len(content.strip()) < self.min_text_length:
                        self._initialize_ocr()
                        if self.ocr_available:
                            ocr_text = self._ocr_pdf(file_path)
                            if ocr_text and len(ocr_text) > len(content or ''):
                                content = ocr_text
                                doc_type = 'PDF-OCR'
                    
                    # 임시 파일 삭제
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    
                    if content and content.strip():
                        print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                        return content, doc_type
                    else:
                        return "[PDF 파일이지만 텍스트 추출 실패]", 'PDF-OCR필요'
                else:
                    return "[파일 다운로드 실패]", '오류'
            
            # 일반 페이지에서 첨부파일 링크 찾기
            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.text, 'lxml')

            all_links = soup.find_all('a', href=True)
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
                            
                            # 텍스트 추출 실패 또는 너무 짧으면 OCR 시도
                            if not content or len(content.strip()) < self.min_text_length:
                                self._initialize_ocr()
                                if self.ocr_available:
                                    ocr_text = self._ocr_pdf(file_path)
                                    if ocr_text and len(ocr_text) > len(content or ''):
                                        content = ocr_text
                                        doc_type = 'PDF-OCR'
                            
                            # 임시 파일 삭제
                            try:
                                os.remove(file_path)
                            except:
                                pass
                            
                            if content and content.strip():
                                print(f"  ✓ PDF 내용 추출 완료 ({len(content)}자)")
                                return content, doc_type
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
            if len(cells) < 6:  # 6개 셀: 번호, 기관, 일자, 내용, 부서, 조회수
                continue
            
            try:
                # 번호, 제재대상기관, 제재조치요구일, 제재조치요구내용(링크), 관련부서, 조회수
                number = cells[0].get_text(strip=True)
                institution = cells[1].get_text(strip=True)
                date = cells[2].get_text(strip=True)
                content_cell = cells[3]
                department = cells[4].get_text(strip=True)
                view_count = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                
                # 링크 찾기
                link = content_cell.find('a', href=True)
                detail_url = None
                link_text = ""
                if link:
                    detail_url = urljoin(self.base_url, link['href'])
                    link_text = link.get_text(strip=True)
                
                items.append({
                    '번호': number,
                    '제재대상기관': institution,
                    '제재조치요구일': date,
                    '조회수': view_count,
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
        print("금융감독원 제재조치 현황 스크래핑 시작 (v2 - FileExtractor 사용)")
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
                attachment_content, doc_type = self.extract_attachment_content(
                    item['상세페이지URL'], 
                    link_text
                )
                item['제재조치내용'] = attachment_content
                item['문서유형'] = doc_type
                
                # PDF 내용에서 금융회사명, 제재조치일, 제재내용 추출
                if attachment_content and not attachment_content.startswith('['):
                    # OCR로 추출한 경우 OCR 전용 함수 사용
                    is_ocr = doc_type == 'PDF-OCR'
                    
                    if is_ocr and OCR_MODULE_AVAILABLE:
                        extract_metadata_fn = extract_metadata_from_content_ocr
                        extract_sanction_fn = extract_sanction_details_ocr
                        extract_incidents_fn = extract_incidents_ocr
                        print(f"  OCR 텍스트로 메타데이터 추출 중...")
                    else:
                        extract_metadata_fn = extract_metadata_from_content_normal
                        extract_sanction_fn = extract_sanction_details_normal
                        extract_incidents_fn = extract_incidents_normal
                    
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
                    
                    # 제재내용 (표 데이터) 추출
                    sanction_details = extract_sanction_fn(attachment_content)
                    if sanction_details:
                        item['제재내용'] = sanction_details
                        print(f"  제재내용 추출: {len(sanction_details)}자")
                    
                    # 사건 제목/내용 추출 (4번 항목)
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
                if institution_from_list:
                    item['금융회사명'] = institution_from_list
                    item['업종'] = self.get_industry(institution_from_list)
                else:
                    item['업종'] = '기타'
            
            # 업종 필드가 없는 경우 기타로 설정
            if '업종' not in item:
                item['업종'] = '기타'

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

    def _split_incidents(self):
        """
        각 제재 건에서 사건들을 분리하여 개별 행으로 변환
        예: 제목1, 내용1, 제목2, 내용2 -> 두 개의 별도 행으로 분리
        """
        split_results = []
        
        for item in self.results:
            # 기본 필드 추출 (줄바꿈 정리 적용)
            base_data = {
                '금융회사명': item.get('금융회사명', item.get('제재대상기관', '')),
                '업종': item.get('업종', '기타'),
                '제재조치일': item.get('제재조치일', item.get('제재조치요구일', '')),
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
                    '내용': ''
                })
            else:
                # 각 사건을 별도 행으로 분리
                for i in range(1, incident_count + 1):
                    title = item.get(f'제목{i}', '')
                    raw_content = item.get(f'내용{i}', '')
                    
                    # 내용 정리 (<관련법규>/<관련규정> 섹션 제거 및 줄바꿈 정리)
                    content = self._clean_content(raw_content)
                    
                    split_results.append({
                        **base_data,
                        '제목': title,
                        '내용': content
                    })
        
        return split_results

    def save_results(self, filename='fss_results.json'):
        """결과 저장 (JSON, CSV) - 루트 디렉토리에 저장"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 파일명만 추출 (경로가 포함된 경우)
        base_filename = os.path.basename(filename)
        json_filepath = os.path.join(script_dir, base_filename)
        
        # 사건별로 분리된 결과 생성
        split_results = self._split_incidents()
        
        # JSON 저장 (분리된 결과)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(split_results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {json_filepath}에 저장되었습니다.")
        print(f"  (원본: {len(self.results)}개 제재 건 -> 분리 후: {len(split_results)}개 사건)")

        try:
            csv_filename = base_filename.replace('.json', '.csv')
            csv_filepath = os.path.join(script_dir, csv_filename)
            
            if split_results:
                # 필드 순서: 업종, 금융회사명, 제목, 내용, 제재내용, 제재조치일, 상세페이지URL
                fieldnames = ['업종', '금융회사명', '제목', '내용', '제재내용', '제재조치일', '상세페이지URL']

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
    # 기본 검색 기간 설정 (오늘 날짜 기준)
    today = datetime.now()
    default_edate = today.strftime('%Y-%m-%d')
    # 기본 시작일: 1년 전
    default_sdate = (datetime(today.year - 1, today.month, today.day)).strftime('%Y-%m-%d')
    
    parser = argparse.ArgumentParser(description='금융감독원(FSS) 제재조치 현황 스크래퍼')
    parser.add_argument('--limit', type=int, default=None,
                        help='수집할 최대 항목 수 (기본값: 전체 수집)')
    parser.add_argument('--after', type=str, default='2024.03.30',
                        help='이 날짜 이후 항목만 수집 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: 2024.03.30)')
    parser.add_argument('--sdate', type=str, default=default_sdate,
                        help=f'검색 시작일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_sdate})')
    parser.add_argument('--edate', type=str, default=default_edate,
                        help=f'검색 종료일 (형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, 기본값: {default_edate})')
    parser.add_argument('--output', type=str, default='fss_results.json',
                        help='출력 파일명 (기본값: fss_results.json)')
    
    args = parser.parse_args()
    
    scraper = FSSScraperV2()
    results = scraper.scrape_all(
        limit=args.limit, 
        after_date=args.after,
        sdate=args.sdate,
        edate=args.edate
    )
    scraper.save_results(filename=args.output)

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 제재 건 수집 (사건별로 분리되어 저장됨)")
    print("=" * 60)

