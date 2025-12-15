"""
extract_sanctions.py - 제재내용 보완 및 정제 스크립트 (ManagementNotices용)
- fss_scraper_v2.py에서 기본 추출이 완료된 데이터를 보완/정제
- 제재내용 보완 (OCR 공백 제거, 더 정확한 추출 시도)
- OCR 공백 제거 (제재내용, 제목, 내용 필드)
- 3. 조치내용, 4. 조치대상사실 패턴 사용
"""
import json
import re
import csv
import sys
import os
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

# post_process_ocr 모듈에서 collapse_split_syllables import
from post_process_ocr import collapse_split_syllables


# UTF-8 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

# KoFIU_Scraper의 extract_metadata 모듈 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'KoFIU_Scraper'))
from extract_metadata import remove_page_numbers

# ManagementNotices 전용 함수 (fss_scraper_v2.py에서 정의)
# 여기서는 재정의
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
    result = remove_page_numbers(result)
    
    return result.strip()


def extract_sanction_info(content, is_ocr=False):
    """
    제재조치내용에서 제재내용 추출 (보완/정제용)
    ManagementNotices 전용: 3. 조치내용 패턴 사용
    
    Args:
        content: PDF 내용
        is_ocr: OCR 추출 여부 (True인 경우에만 OCR 오류 보정)
    """
    if not content or content.startswith('[') or content.startswith('[오류'):
        return '', ''
    
    # OCR 추출된 경우에만 OCR 오류 보정 (띄어쓰기 보존)
    # OCR 오류: 한글 음절 사이에 삽입된 공백만 제거 (예: "기 관" -> "기관")
    # 정상 띄어쓰기는 보존 (예: "기관 과" -> "기관 과")
    if is_ocr:
        content = collapse_split_syllables(content)
    
    # ManagementNotices 전용 함수 사용
    sanction = extract_sanction_details_management(content)
    
    return None, sanction  # 제재대상은 반환하지 않음


if __name__ == "__main__":
    import os
    
    # JSON 파일 읽기
    print("JSON 파일 읽는 중...")
    with open('fss_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"총 {len(data)}개 항목 로드 완료")
    
    # ========================================================================
    # 보완/정제 단계
    # ========================================================================
    # fss_scraper_v2.py에서 기본 추출이 완료되었으므로, 여기서는 보완/정제만 수행
    # - 제재내용 보완 (OCR 공백 제거, 더 정확한 추출 시도)
    # - OCR 공백 제거 (제재내용, 제목, 내용 필드)
    # - 사건 추출은 이미 fss_scraper_v2.py에서 완료되었으므로 스킵
    # ========================================================================
    print("\n[보완/정제 단계] 제재내용 보완 중...")
    for idx, item in enumerate(data, 1):
        # fss_scraper_v2.py 구조: 제재조치내용이 없을 수 있고, 제재내용이 이미 있을 수 있음
        content = item.get('제재조치내용', '')  # 원본 PDF 내용 (없을 수 있음)
        existing_sanction = item.get('제재내용', '')  # 이미 추출된 제재내용
        
        # 제재내용이 없으면 원본 내용에서 추출 시도 (띄어쓰기 보존)
        if not existing_sanction and content:
            is_ocr = item.get('OCR추출여부') == '예'
            result = extract_sanction_info(content, is_ocr=is_ocr)
            if isinstance(result, tuple) and len(result) == 2:
                _, sanction = result  # 제재대상은 무시
                # 제재내용만 저장
                if sanction and sanction != '-':
                    item['제재내용'] = sanction
            else:
                # 간단한 패턴으로 제재내용 추출 시도 (띄어쓰기 보존)
                # OCR 추출된 경우에만 OCR 오류 보정
                is_ocr = item.get('OCR추출여부') == '예'
                search_content = collapse_split_syllables(content) if is_ocr else content
                inline_pattern = re.compile(r'(?:제재대상|대상)\s*(?:제재내용|내용)\s*(?:기관|임원|직원|임직원)\s*([^\r\n]+)', re.DOTALL)
                simple_match = inline_pattern.search(search_content)
                if simple_match:
                    sanction = simple_match.group(1).strip()
                    # 연속된 공백만 정리 (원본 띄어쓰기는 보존)
                    sanction = re.sub(r' {3,}', ' ', sanction)  # 3개 이상 연속된 공백만 정리
                    if sanction:
                        item['제재내용'] = sanction
        
        # OCR 후처리는 post_process_ocr.py에서 처리하므로 여기서는 제거
        # (extract_sanction_info 함수 내에서만 OCR 오류 보정 사용)
        
        # 구분, 출처 필드 추가 (없는 경우)
        if '구분' not in item:
            item['구분'] = '경영유의'
        if '출처' not in item:
            item['출처'] = '금융감독원'
        
        # 누락필드 계산
        missing_fields = []
        if not item.get('제재내용') or str(item.get('제재내용', '')).strip() in ['', '-']:
            missing_fields.append('제재내용')
        if not item.get('제목') or str(item.get('제목', '')).strip() in ['', '-']:
            missing_fields.append('제목')
        if not item.get('내용') or str(item.get('내용', '')).strip() in ['', '-']:
            missing_fields.append('내용')
        item['누락필드'] = ','.join(missing_fields) if missing_fields else ''
        
        # 사건제목과 사건내용은 이미 fss_scraper_v2.py에서 추출되었으므로 스킵
        # (제목, 내용 필드가 이미 있음)
        
        if idx % 50 == 0:
            print(f"  {idx}개 항목 처리 완료...")
    
    # 결과 저장
    print("\n결과 저장 중...")
    with open('fss_results.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("JSON 파일 저장 완료")
    
    # CSV 파일도 재생성
    print("CSV 파일 재생성 중...")
    csv_filename = 'fss_results.csv'
    
    # CSV 파일 재생성 (fss_scraper_v2.py 구조에 맞게)
    # 이미 사건별로 분리되어 있으므로 그대로 사용
    csv_rows = []
    # fss_scraper_v2.py 필드: 구분, 출처, 업종, 금융회사명, 제목, 내용, 제재내용, 제재조치일, 파일다운로드URL
    # OCR추출여부, 누락필드 필드도 포함
    base_fieldnames = ['구분', '출처', '업종', '금융회사명', '제목', '내용', '제재내용', '제재조치일', '파일다운로드URL', 'OCR추출여부', '누락필드']
    
    for item in data:
        row = {}
        for field in base_fieldnames:
            row[field] = item.get(field, '')
        csv_rows.append(row)
    
    fieldnames = base_fieldnames
    with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for row in csv_rows:
            csv_row = {}
            for field in fieldnames:
                value = row.get(field, '')
                if value is None:
                    value = ''
                value_str = str(value).strip()
                if not value_str:
                    value_str = '-'
                csv_row[field] = value_str
            writer.writerow(csv_row)
    
    print(f"CSV 파일 저장 완료: {csv_filename}")
    
    # 샘플 확인
    print("\n처리 결과 샘플 (첫 5개):")
    for i in range(min(5, len(data))):
        item = data[i]
        sanction = item.get('제재내용', '')
        company = item.get('금융회사명', item.get('제재대상기관', 'N/A'))
        print(f"\n[{i+1}] {company}")
        if sanction and sanction != '-':
            sanction_short = sanction[:80] + '...' if len(sanction) > 80 else sanction
            print(f"  제재내용: {sanction_short}")
        else:
            print(f"  제재내용: (추출 실패)")
    
    # 추출 성공률 확인
    success_count = sum(1 for item in data if item.get('제재내용') and item.get('제재내용') != '-')
    print(f"\n제재내용 추출 성공: {success_count}/{len(data)}개 항목")
    
    # OCR 후처리 자동 실행
    print("\n" + "=" * 60)
    print("OCR 후처리 시작...")
    print("=" * 60)
    
    import subprocess
    try:
        result = subprocess.run([sys.executable, 'post_process_ocr.py'], 
                              capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        if result.returncode != 0:
            print(f"후처리 중 오류 발생: {result.stderr}")
    except Exception as e:
        print(f"후처리 실행 실패: {e}")
    
    print("\n완료!")

