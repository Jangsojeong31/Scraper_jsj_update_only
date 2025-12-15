"""
OCR 후처리 모듈
OCR로 추출된 텍스트의 오류를 수정하고 품질을 개선
"""
import json
import re
import sys
import csv
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

sys.stdout.reconfigure(encoding='utf-8')

# 연속된 한글 음절 사이에 OCR로 삽입된 공백을 제거하기 위한 패턴
split_syllable_pattern = re.compile(r'((?:[가-힣]\s){2,}[가-힣])')


def collapse_split_syllables(text: str) -> str:
    """
    OCR 오류로 인한 한글 음절 사이의 공백만 제거 (정상 띄어쓰기는 보존)
    
    예: "기 관 과 태 료" -> "기관과태료" (OCR 오류)
    예: "기관 과 태료" -> "기관 과 태료" (정상 띄어쓰기 보존)
    
    패턴: 연속된 한글 음절 사이에 공백이 있는 경우만 제거
    """
    if not text:
        return text
    
    # 연속된 한글 음절 사이의 공백만 제거 (OCR 오류)
    result = split_syllable_pattern.sub(lambda m: m.group(0).replace(' ', ''), text)
    
    return result


def clean_ocr_artifacts(text):
    """OCR 인공물 제거 (개선된 버전)"""
    if not text:
        return text
    
    # 1. 특수문자 정규화 (먼저 처리)
    text = text.replace('ㆍ', '·')
    text = text.replace('，', ',')
    text = text.replace('。', '.')
    text = text.replace('、', ',')
    
    # 2. "_ ｜ -" 패턴 제거 (다양한 변형 포함)
    text = re.sub(r'_\s*[｜\|ㅣ]\s*-\s*', '', text)
    text = re.sub(r'_\s*[｜\|ㅣ]\s*', '', text)  # 뒤에 - 없이도 제거
    text = re.sub(r'_\s*[，,]\s*', '', text)  # "_ ，" 패턴 제거
    
    # 3. 한글 오인식 보정
    ocr_corrections = {
        '되직자': '퇴직자',
        '줌법': '준법',
        '되직': '퇴직',
        '줌법감시': '준법감시',
        '줌법감시인': '준법감시인',
        '과리료': '과태료',
        '제제내용': '제재내용',
    }
    for wrong, correct in ocr_corrections.items():
        text = text.replace(wrong, correct)
    
    # 4. 숫자-한글 사이 공백 제거 (예: "24 백만원" -> "24백만원")
    text = re.sub(r'(?<=\d)\s+(?=[가-힣])', '', text)
    
    # 5. 한글 글자 사이 공백 제거 (일반적인 단어 패턴)
    text = re.sub(r'등\s+록\s+취\s+소', '등록취소', text)
    text = re.sub(r'업\s+무\s+정\s+지', '업무정지', text)
    text = re.sub(r'과\s+태\s+료', '과태료', text)
    text = re.sub(r'견\s+책', '견책', text)
    text = re.sub(r'감\s+봉', '감봉', text)
    text = re.sub(r'기\s+관', '기관', text)
    text = re.sub(r'임\s+원', '임원', text)
    text = re.sub(r'직\s+원', '직원', text)
    text = re.sub(r'임\s+직\s+원', '임직원', text)
    text = re.sub(r'퇴\s+직\s+자', '퇴직자', text)
    text = re.sub(r'준\s+법', '준법', text)
    text = re.sub(r'백\s+만\s+원', '백만원', text)
    text = re.sub(r'만\s+원', '만원', text)
    text = re.sub(r'부\s+과', '부과', text)
    text = re.sub(r'주\s+의', '주의', text)
    text = re.sub(r'경\s+고', '경고', text)
    text = re.sub(r'상\s+당', '상당', text)
    text = re.sub(r'위\s+법', '위법', text)
    text = re.sub(r'부\s+당', '부당', text)
    text = re.sub(r'사\s+항', '사항', text)
    
    # 6. 고립된 문자 제거
    text = re.sub(r'\bㅣ\b', '', text)
    text = re.sub(r'\b\|\b(?![가-힣])', '', text)
    text = text.replace('`', '')
    
    # 7. 숫자 오인식 보정 (연속된 0이 3개 이상인 경우)
    text = re.sub(r'\b0{3,}\b', '', text)
    
    # 8. 과도한 공백 정리 (3개 이상 → 1개, 단 띄어쓰기는 보존)
    text = re.sub(r' {3,}', ' ', text)
    
    # 9. 앞쪽 불필요한 하이픈/점 제거
    text = text.lstrip('- ').lstrip('·').lstrip('- ')
    text = text.lstrip('. ')
    
    # 10. "ㅇ" 단독 문자 제거 (OCR 오류로 생성된 경우)
    text = re.sub(r'\bㅇ\b(?=\s)', '', text)
    text = re.sub(r'(?<=\s)\bㅇ\b', '', text)

    return text.strip()


def process_ocr_text(text, preserve_spacing=False):
    """
    OCR 텍스트 후처리
    
    Args:
        text: OCR로 추출된 텍스트
        preserve_spacing: 띄어쓰기 보존 여부 (True면 collapse_split_syllables 사용 안 함)
    
    Returns:
        후처리된 텍스트
    """
    if not text:
        return text
    
    # OCR 인공물 제거
    text = clean_ocr_artifacts(text)
    
    # 띄어쓰기 보존 옵션이 False인 경우에만 collapse_split_syllables 적용
    if not preserve_spacing:
        text = collapse_split_syllables(text)
    
    return text


def main():
    """OCR 후처리 메인 함수"""
    print("=" * 100)
    print("OCR 후처리 및 품질 개선")
    print("=" * 100)
    
    # JSON 파일 로드
    json_filename = 'fss_results.json'
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {json_filename}")
        return
    
    print(f"\n총 {len(data)}개 항목 로드")
    
    # OCR 추출된 항목만 후처리
    processed_count = 0
    for item in data:
        is_ocr = item.get('OCR추출여부') == '예'
        
        if is_ocr:
            # OCR 추출된 경우에만 후처리 (띄어쓰기 보존)
            if item.get('제재내용'):
                item['제재내용'] = process_ocr_text(item['제재내용'], preserve_spacing=True)
            
            if item.get('제목'):
                item['제목'] = process_ocr_text(item['제목'], preserve_spacing=True)
            
            if item.get('내용'):
                item['내용'] = process_ocr_text(item['내용'], preserve_spacing=True)
            
            processed_count += 1
    
    print(f"\nOCR 추출 항목 {processed_count}개 후처리 완료")
    
    # 저장
    if processed_count > 0:
        print("\n수정된 결과 저장 중...")
        
        # JSON 저장
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # CSV 재생성
        csv_filename = 'fss_results.csv'
        base_fieldnames = ['구분', '출처', '업종', '금융회사명', '제목', '내용', '제재내용', 
                          '제재조치일', '파일다운로드URL', 'OCR추출여부', '누락필드']
        
        csv_rows = []
        for item in data:
            row = {}
            for field in base_fieldnames:
                row[field] = item.get(field, '')
            csv_rows.append(row)
        
        with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=base_fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(csv_rows)
        
        print(f"   ✓ JSON 및 CSV 파일 저장 완료")
    
    print("\n" + "=" * 100)
    print(f"완료! (처리된 항목: {processed_count}개)")
    print("=" * 100)


if __name__ == '__main__':
    main()

