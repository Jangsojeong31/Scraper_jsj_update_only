import json
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import time
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Tesseract 경로 설정
tesseract_paths = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\USER\AppData\Local\Tesseract-OCR\tesseract.exe',
    r'C:\Users\USER\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
]

tesseract_found = False
for path in tesseract_paths:
    if os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        tesseract_found = True
        print(f"Tesseract 찾음: {path}")
        break

if not tesseract_found:
    print("Tesseract-OCR을 찾을 수 없습니다.")
    sys.exit(1)

# JSON 파일 읽기
with open('fss_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 짧은 내용을 가진 항목 찾기 (제재조치내용 또는 제재내용 확인)
short_items = []
for item in data:
    content = item.get('제재조치내용', '') or item.get('제재내용', '')
    if len(content) < 100:
        short_items.append(item)

print(f"OCR 처리할 항목: {len(short_items)}개")
if short_items:
    # 번호 필드가 있으면 사용, 없으면 인덱스 사용
    numbers = []
    for idx, item in enumerate(short_items, 1):
        if '번호' in item and item['번호']:
            numbers.append(str(item['번호']))
        else:
            numbers.append(f"항목{idx}")
    print(f"번호: {', '.join(numbers)}")
print("=" * 80)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def ocr_pdf(pdf_path):
    """PDF에서 OCR로 텍스트 추출 (한글 지원)"""
    try:
        doc = fitz.open(pdf_path)
        full_text = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 페이지를 고해상도 이미지로 변환 (300 DPI)
            mat = fitz.Matrix(300/72, 300/72)
            pix = page.get_pixmap(matrix=mat)
            
            # PIL Image로 변환
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            
            # 이미지 전처리 (그레이스케일 변환)
            image = image.convert('L')
            
            # OCR 실행 - kor 옵션만 사용 (한글 우선)
            try:
                # Tesseract 설정 - PSM 모드 6 (단일 블록 텍스트로 가정)
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(image, lang='kor', config=custom_config)
                if text.strip():
                    full_text.append(text)
            except Exception as e:
                print(f"        OCR 오류: {e}")
                # 실패 시 기본 설정으로 재시도
                try:
                    text = pytesseract.image_to_string(image, lang='kor')
                    if text.strip():
                        full_text.append(text)
                except:
                    pass
        
        doc.close()
        result = '\n'.join(full_text).strip()
        return result if result else "[OCR 텍스트 추출 실패]"
        
    except Exception as e:
        print(f"      OCR 오류: {e}")
        return "[OCR 오류 발생]"

# 각 항목 처리
updated_count = 0
failed_count = 0

for idx, item in enumerate(short_items, 1):
    # 식별자 생성 (번호가 있으면 사용, 없으면 인덱스)
    item_id = item.get('번호', f"항목{idx}")
    company_name = item.get('금융회사명', item.get('제재대상기관', 'N/A'))
    print(f"\n[{idx}/{len(short_items)}] 번호 {item_id}: {company_name}")
    
    try:
        # 상세 페이지 URL 확인 (상세페이지URL 또는 파일다운로드URL 사용)
        detail_url = item.get('상세페이지URL', '') or item.get('파일다운로드URL', '')
        if not detail_url:
            print(f"  ✗ 상세 페이지 URL이 없음")
            failed_count += 1
            continue
        
        # 상세 페이지 접속
        response = requests.get(detail_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 첨부파일 찾기
        attach_links = soup.find_all('a', href=lambda x: x and 'download' in x.lower())
        if not attach_links:
            attach_links = soup.find_all('a', string=lambda x: x and '.pdf' in x.lower() if x else False)
        
        pdf_downloaded = False
        
        for link in attach_links:
            href = link.get('href', '')
            text_content = link.get_text(strip=True)
            
            if '.pdf' in href.lower() or '.pdf' in text_content.lower():
                # PDF URL 구성
                if not href.startswith('http'):
                    if href.startswith('/'):
                        pdf_url = 'https://www.fss.or.kr' + href
                    else:
                        pdf_url = 'https://www.fss.or.kr/fss/job/openInfo/' + href
                else:
                    pdf_url = href
                
                print(f"  PDF 다운로드: {text_content[:50]}")
                
                # PDF 다운로드
                pdf_response = requests.get(pdf_url, headers=headers, timeout=15)
                
                if pdf_response.status_code == 200:
                    temp_filename = f'temp_ocr_{item_id}.pdf'
                    with open(temp_filename, 'wb') as f:
                        f.write(pdf_response.content)
                    
                    print(f"    크기: {len(pdf_response.content)} bytes")
                    print(f"    OCR 처리 중...")
                    
                    # OCR로 텍스트 추출
                    extracted_text = ocr_pdf(temp_filename)
                    print(f"    추출된 텍스트 길이: {len(extracted_text)} 자")
                    
                    if len(extracted_text) > 100 and not extracted_text.startswith('['):
                        # 원래 데이터에서 해당 항목 찾아서 업데이트
                        # 번호로 매칭 시도, 없으면 파일다운로드URL로 매칭
                        updated = False
                        for data_item in data:
                            # 번호로 매칭
                            if '번호' in item and '번호' in data_item and data_item.get('번호') == item.get('번호'):
                                data_item['제재조치내용'] = extracted_text
                                if '제재내용' not in data_item or not data_item.get('제재내용'):
                                    data_item['제재내용'] = ''  # 제재내용은 나중에 추출
                                updated = True
                                updated_count += 1
                                print(f"    ✓ 업데이트 완료")
                                break
                            # 파일다운로드URL로 매칭 (번호가 없는 경우)
                            elif not item.get('번호') and data_item.get('파일다운로드URL') == item.get('파일다운로드URL'):
                                data_item['제재조치내용'] = extracted_text
                                if '제재내용' not in data_item or not data_item.get('제재내용'):
                                    data_item['제재내용'] = ''  # 제재내용은 나중에 추출
                                updated = True
                                updated_count += 1
                                print(f"    ✓ 업데이트 완료")
                                break
                        
                        if not updated:
                            print(f"    ⚠ 해당 항목을 데이터에서 찾을 수 없음")
                    else:
                        print(f"    ✗ 추출 실패 또는 내용 부족")
                        failed_count += 1
                    
                    # 임시 파일 삭제
                    try:
                        os.remove(temp_filename)
                    except:
                        pass
                    
                    pdf_downloaded = True
                    break
        
        if not pdf_downloaded:
            print(f"  ✗ PDF 파일을 찾을 수 없음")
            failed_count += 1
        
        # 서버 부담을 줄이기 위해 딜레이
        time.sleep(1)
        
    except Exception as e:
        print(f"  오류: {e}")
        failed_count += 1
        import traceback
        traceback.print_exc()
        continue

print("\n" + "=" * 80)
print(f"OCR 처리 완료:")
print(f"  성공: {updated_count}개")
print(f"  실패: {failed_count}개")

# JSON 파일 저장
if updated_count > 0:
    with open('fss_results.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\nJSON 파일 업데이트 완료!")
    
    # 성공한 항목 번호 출력
    success_numbers = []
    for item in short_items:
        item_id = item.get('번호', '')
        for data_item in data:
            # 번호로 매칭
            if item_id and '번호' in data_item and data_item.get('번호') == item_id:
                content = data_item.get('제재조치내용', '') or data_item.get('제재내용', '')
                if len(content) > 100:
                    success_numbers.append(str(item_id))
                    break
            # 파일다운로드URL로 매칭 (번호가 없는 경우)
            elif not item_id and data_item.get('파일다운로드URL') == item.get('파일다운로드URL'):
                content = data_item.get('제재조치내용', '') or data_item.get('제재내용', '')
                if len(content) > 100:
                    success_numbers.append(f"URL:{item.get('파일다운로드URL', '')[:30]}")
                    break
    
    if success_numbers:
        print(f"\nOCR 성공한 항목 번호: {', '.join(success_numbers)}")
else:
    print("\n업데이트할 내용이 없습니다.")

print("\n다음 단계: fss_scraper_v2.py 또는 run_pipeline.py를 실행하여 제재대상과 제재내용을 추출하세요.")

