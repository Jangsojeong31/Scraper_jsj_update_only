import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin, urlparse
import pdfplumber
import PyPDF2
from pathlib import Path
import io

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

class FSSCraper:
    def __init__(self):
        self.base_url = "https://www.fss.or.kr"
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
        """페이지 가져오기 (재시도 로직 포함)"""
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
    
    def extract_pdf_text(self, file_path):
        """PDF 파일에서 텍스트 추출 후 유형 정보 반환"""
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

        # OCR 시도
        self.initialize_ocr()
        ocr_text = self.ocr_pdf(file_path) if self.ocr_available else None
        if ocr_text and len(ocr_text) > max(extracted_length, 0):
            return ocr_text.strip(), 'PDF-OCR'

        if extracted_text:
            doc_type = 'PDF-텍스트' if extracted_length >= self.min_text_length else 'PDF-OCR필요'
            return extracted_text, doc_type

        return None, 'PDF-OCR필요'
    
    def download_file(self, url, filename):
        """파일 다운로드"""
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
    
    def extract_attachment_content(self, detail_url):
        """상세 페이지에서 첨부파일 찾아서 내용 및 유형 추출"""
        try:
            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 첨부파일 섹션 찾기
            attachment_text = ""
            doc_type = '첨부없음'
            
            # 모든 링크를 확인하여 PDF 파일 찾기
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                link_text = link.get_text(strip=True)
                
                # PDF 파일 링크 찾기 (다양한 패턴)
                if '/fss.hpdownload' in href or 'download' in href.lower() or '.pdf' in href.lower():
                    # URL 구성
                    if href.startswith('/'):
                        file_url = urljoin(self.base_url, href)
                    elif href.startswith('http'):
                        file_url = href
                    else:
                        file_url = urljoin(detail_url, href)
                    
                    # 파일명 추출
                    filename = link_text.strip()
                    if not filename or len(filename) < 3:
                        # URL에서 파일명 추출 시도
                        if 'file=' in href:
                            from urllib.parse import unquote
                            filename = unquote(href.split('file=')[-1].split('&')[0])
                        else:
                            filename = href.split('/')[-1].split('?')[0]
                    
                    # 확장자 확인
                    if not filename.lower().endswith('.pdf'):
                        # URL 파라미터에서 파일명 추출
                        if 'file=' in href:
                            from urllib.parse import unquote
                            filename = unquote(href.split('file=')[-1].split('&')[0])
                    
                    if not filename.lower().endswith('.pdf'):
                        continue
                    
                    print(f"  첨부파일 발견: {filename}")
                    
                    # 파일 다운로드
                    file_path = self.download_file(file_url, filename)
                    if file_path:
                        # PDF 파일인 경우 텍스트 추출
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
                        
                        # 파일 삭제
                        try:
                            file_path.unlink()
                            print(f"  임시 파일 삭제 완료: {filename}")
                        except:
                            pass
                        
                        break  # 첫 번째 첨부파일만 처리
            
            # 첨부파일을 찾지 못한 경우
            if not attachment_text:
                attachment_text = "[첨부파일을 찾을 수 없습니다]"
                doc_type = '첨부없음'
            
            return attachment_text, doc_type
            
        except Exception as e:
            print(f"  첨부파일 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return f"[오류: {str(e)}]", '오류'
    
    def scrape_list_page(self, page_index):
        """목록 페이지 스크래핑"""
        url = f"https://www.fss.or.kr/fss/job/openInfo/list.do?menuNo=200476&pageIndex={page_index}&sdate=2025-01-01&edate=2025-11-06&searchCnd=4&searchWrd="
        
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
                if link:
                    detail_url = urljoin(self.base_url, link['href'])
                
                items.append({
                    '번호': number,
                    '제재대상기관': institution,
                    '제재조치요구일': date,
                    '관련부서': department,
                    '조회수': view_count,
                    '상세페이지URL': detail_url
                })
                
            except Exception as e:
                print(f"  행 처리 중 오류: {e}")
                continue
        
        print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
        return items
    
    def scrape_all(self):
        """전체 스크래핑 실행"""
        print("=" * 60)
        print("금융감독원 제재조치 현황 스크래핑 시작")
        print("=" * 60)
        
        # 26페이지 모두 스크래핑
        all_items = []
        for page in range(1, 27):
            items = self.scrape_list_page(page)
            all_items.extend(items)
            time.sleep(1)  # 서버 부하 방지
        
        print(f"\n총 {len(all_items)}개 항목 수집 완료")
        
        # 각 항목의 상세 정보 및 첨부파일 추출
        print("\n상세 정보 및 첨부파일 추출 시작...")
        for idx, item in enumerate(all_items, 1):
            print(f"\n[{idx}/{len(all_items)}] {item['제재대상기관']} 처리 중...")
            
            if item['상세페이지URL']:
                attachment_content, doc_type = self.extract_attachment_content(item['상세페이지URL'])
                item['제재조치내용'] = attachment_content
                item['문서유형'] = doc_type
            else:
                item['제재조치내용'] = "[상세 페이지 URL이 없습니다]"
                item['문서유형'] = 'URL없음'
            
            # 상세페이지URL은 최종 결과에서 제거 (필요시 주석 해제)
            # del item['상세페이지URL']
            
            self.results.append(item)
            time.sleep(1)  # 서버 부하 방지
        
        # 임시 디렉토리 정리
        try:
            for file in self.temp_dir.iterdir():
                file.unlink()
            self.temp_dir.rmdir()
            print("\n임시 파일 정리 완료")
        except:
            pass
        
        return self.results
    
    def save_results(self, filename='fss_results.json'):
        """결과를 JSON 파일로 저장"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {filename}에 저장되었습니다. (총 {len(self.results)}개)")
        
        # CSV로도 저장 (선택적)
        try:
            import csv
            csv_filename = filename.replace('.json', '.csv')
            if self.results:
                # 필드명 순서 정의
                fieldnames = ['번호', '제재대상기관', '제재조치요구일', '관련부서', '조회수', '문서유형', '상세페이지URL', '제재조치내용']
                
                with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    
                    for item in self.results:
                        row = {}
                        for field in fieldnames:
                            value = item.get(field, '')
                            # None이나 빈 값 처리
                            if value is None:
                                value = ''
                            # 문자열로 변환
                            row[field] = str(value)
                        
                        # CSV writer는 자동으로 따옴표 처리 및 줄바꿈 처리
                        writer.writerow(row)
                
                print(f"CSV 파일도 {csv_filename}에 저장되었습니다.")
        except Exception as e:
            print(f"CSV 저장 중 오류 (무시): {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    scraper = FSSCraper()
    results = scraper.scrape_all()
    scraper.save_results()
    
    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

