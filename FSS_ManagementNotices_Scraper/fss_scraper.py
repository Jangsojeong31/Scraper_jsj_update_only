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


sys.stdout.reconfigure(encoding='utf-8')

class FSSImprovementScraper:
    def __init__(self):
        self.base_url = "https://www.fss.or.kr"
        self.list_url = "https://www.fss.or.kr/fss/job/openInfoImpr/list.do?menuNo=200483&pageIndex={page}&sdate=2025-01-01&edate=2025-11-06&searchCnd=4&searchWrd="
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

                if '/fss.hpdownload' in href or 'download' in href.lower() or '.pdf' in href.lower():
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
        url = self.list_url.format(page=page_index)

        print(f"\n페이지 {page_index} 스크래핑 중...")
        response = self.get_page(url)
        soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)

        table = soup.find('table')
        if not table:
            print(f"  페이지 {page_index}: 테이블을 찾을 수 없습니다")
            return []

        rows = table.find_all('tr')[1:]
        items = []

        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 5:
                continue

            try:
                number = cells[0].get_text(strip=True)
                institution = cells[1].get_text(strip=True)
                date = cells[2].get_text(strip=True)
                content_cell = cells[3]
                department = cells[4].get_text(strip=True)

                link = content_cell.find('a', href=True)
                detail_url = urljoin(self.base_url, link['href']) if link else None
                link_text = link.get_text(strip=True) if link else ''

                items.append({
                    '번호': number,
                    '제재대상기관': institution,
                    '제재조치요구일': date,
                    '관련부서': department,
                    '조회수': '-',
                    '상세페이지URL': detail_url,
                    '_link_text': link_text
                })

            except Exception as e:
                print(f"  행 처리 중 오류: {e}")
                continue

        print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
        return items

    def scrape_all(self):
        print("=" * 60)
        print("금융감독원 경영유의사항 공시 스크래핑 시작")
        print("=" * 60)

        all_items = []
        seen_numbers = set()
        page = 1

        while True:
            items = self.scrape_list_page(page)
            if not items:
                print(f"\n페이지 {page}에서 더 이상 항목이 없어 수집을 종료합니다.")
                break

            new_items = []
            for item in items:
                number = item.get('번호')
                if number in seen_numbers:
                    continue
                seen_numbers.add(number)
                new_items.append(item)

            if not new_items:
                print(f"\n페이지 {page}에서 새로운 항목이 없어 수집을 종료합니다.")
                break

            all_items.extend(new_items)
            time.sleep(1)
            page += 1

        print(f"\n총 {len(all_items)}개 항목 수집 완료")

        print("\n상세 정보 및 첨부파일 추출 시작...")
        for idx, item in enumerate(all_items, 1):
            print(f"\n[{idx}/{len(all_items)}] {item['제재대상기관']} 처리 중...")

            link_text = item.pop('_link_text', '')
            if item['상세페이지URL']:
                attachment_content, doc_type = self.extract_attachment_content(item['상세페이지URL'], link_text)
                item['제재조치내용'] = attachment_content
                item['문서유형'] = doc_type
            else:
                item['제재조치내용'] = "[상세 페이지 URL이 없습니다]"
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

        return self.results

    def save_results(self, filename='fss_results.json'):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {filename}에 저장되었습니다. (총 {len(self.results)}개)")

        try:
            import csv
            csv_filename = filename.replace('.json', '.csv')
            if self.results:
                fieldnames = ['번호', '제재대상기관', '제재조치요구일', '관련부서', '조회수', '문서유형', '상세페이지URL', '제재조치내용']

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
    scraper = FSSImprovementScraper()
    results = scraper.scrape_all()
    scraper.save_results()

    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

