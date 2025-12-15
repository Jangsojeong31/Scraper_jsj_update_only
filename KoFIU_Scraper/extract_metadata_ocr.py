"""
OCR로 추출한 PDF 내용에서 메타데이터(금융회사명, 제재조치일, 제재내용) 추출 모듈
- OCR 텍스트의 한글 글자 사이 공백을 자동으로 제거하여 처리
"""
import re
import sys
import os

# 기존 extract_metadata 모듈 import
sys.path.insert(0, os.path.dirname(__file__))
from extract_metadata import (
    remove_page_numbers,
    extract_sanction_details as _extract_sanction_details_base,
    extract_metadata_from_content as _extract_metadata_from_content_base
)

# 연속된 한글 음절 사이에 OCR로 삽입된 공백을 제거하기 위한 패턴
split_syllable_pattern = re.compile(r'((?:[가-힣]\s){2,}[가-힣])')


def collapse_split_syllables(text):
    """
    한글 음절 사이에 삽입된 불필요한 공백을 제거 (OCR 텍스트 전처리)
    
    Args:
        text: 원본 텍스트
        
    Returns:
        str: 공백이 제거된 텍스트
    """
    if not text:
        return text
    return split_syllable_pattern.sub(lambda m: m.group(0).replace(' ', ''), text)


def preprocess_ocr_text(text):
    """
    OCR 텍스트 전처리 (공백 정리)
    
    Args:
        text: OCR로 추출한 원본 텍스트
        
    Returns:
        str: 전처리된 텍스트
    """
    if not text:
        return text
    
    # 한글 글자 사이의 공백 제거
    text = collapse_split_syllables(text)
    
    # 연속된 공백 정리
    text = re.sub(r' +', ' ', text)
    
    # 줄바꿈 정리
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    return text.strip()


def extract_metadata_from_content(content):
    """
    OCR 텍스트에서 금융회사명과 제재조치일 추출
    
    Args:
        content: OCR로 추출한 텍스트 내용
        
    Returns:
        tuple: (금융회사명, 제재조치일)
    """
    if not content or content.startswith('['):
        return "", ""
    
    # OCR 텍스트 전처리
    content = preprocess_ocr_text(content)
    
    # 기존 함수 사용
    return _extract_metadata_from_content_base(content)


def extract_sanction_details(content):
    """
    OCR 텍스트에서 제재조치내용 표 데이터 추출
    
    Args:
        content: OCR로 추출한 텍스트 내용
        
    Returns:
        str: 제재내용
    """
    if not content or content.startswith('['):
        return ""
    
    # OCR 텍스트 전처리
    content = preprocess_ocr_text(content)
    
    # 기존 함수 사용
    return _extract_sanction_details_base(content)


def extract_incidents(content):
    """
    OCR 텍스트에서 4번 항목의 사건 제목/내용 추출
    (extract_sanctions.py의 줄 단위 처리 방식 참고)
    
    지원하는 형식:
    1. 가. 제목1 / 내용1, 나. 제목2 / 내용2 형태
    2. 가. 문책사항 (1) 제목1 / 내용1 (2) 제목2 / 내용2 형태
    3. 가. (1) 제목 (가) 내용 (나) 내용 형태 -> (가), (나)는 내용으로 처리
    
    Args:
        content: OCR로 추출한 텍스트 내용
        
    Returns:
        dict: {'제목1': '...', '내용1': '...', '제목2': '...', ...}
    """
    if not content or content.startswith('['):
        return {}
    
    # OCR 텍스트 전처리
    content = preprocess_ocr_text(content)
    
    # 4번 항목 제목 패턴 (OCR 텍스트를 위해 공백 허용)
    section4_patterns = [
        # "4. 제재대상사실" 형식 (OCR: "4 . 제 재 대 상 사 실")
        r'4\s*\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'4\s*\.\s*제재대상사실',
        r'4\s*\.\s*제재대상\s*사실',
        # "4. 조치대상사실" 형식
        r'4\s*\.\s*조\s*치\s*대\s*상\s*사\s*실',
        r'4\s*\.\s*조치대상사실',
        r'4\s*\.\s*조치대상\s*사실',
        # "4. 제재조치사유" 형식
        r'4\s*\.\s*제\s*재\s*조\s*치\s*사\s*유',
        r'4\s*\.\s*제재조치사유',
        r'4\s*\.\s*제재조치\s*사유',
        # "4. 제재사유" 형식
        r'4\s*\.\s*제\s*재\s*사\s*유',
        r'4\s*\.\s*제재사유',
        r'4\s*\.\s*제재\s*사유',
        # "4. 조치사유" 형식
        r'4\s*\.\s*조\s*치\s*사\s*유',
        r'4\s*\.\s*조치사유',
        r'4\s*\.\s*조치\s*사유',
        # "4. 위반내용" 형식
        r'4\s*\.\s*위\s*반\s*내\s*용',
        r'4\s*\.\s*위반내용',
        r'4\s*\.\s*위반\s*내용',
        # "4. 사유" 형식
        r'4\s*\.\s*사\s*유',
        r'4\s*\.\s*사유',
    ]
    
    start_pos = None
    for pattern in section4_patterns:
        match = re.search(pattern, content)
        if match:
            start_pos = match.end()
            break
    
    if start_pos is None:
        return {}
    
    # 다음 항목(5. 로 시작) 또는 문서 끝까지의 내용 추출
    remaining_content = content[start_pos:]
    
    # 다음 번호 항목(5., 6. 등) 찾기
    next_section_match = re.search(r'\n\s*[5-9]\s*\.\s*[가-힣]', remaining_content)
    if next_section_match:
        section_text = remaining_content[:next_section_match.start()]
    else:
        section_text = remaining_content
    
    # 줄 단위로 처리
    lines = section_text.split('\n')
    
    incidents = {}
    incident_num = 1
    
    current_title = None
    current_content = []
    in_incident = False
    parent_title = ""  # 상위 제목 (가. 문책사항 등)
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # "가. 문책사항" 또는 "가 . 문 책 사 항" 패턴 체크 (상위 제목)
        # OCR 텍스트를 위해 점 앞뒤 공백 허용
        header_pattern = r'^[가-하]\s*\.\s*(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항|자율처리\s*필요사항)(.*)$'
        header_match = re.match(header_pattern, line)
        
        if header_match:
            # 이전 사건 저장
            if current_title and current_content:
                content_text = '\n'.join(current_content).strip()
                content_text = remove_page_numbers(content_text)
                incidents[f'제목{incident_num}'] = current_title
                incidents[f'내용{incident_num}'] = content_text
                incident_num += 1
            
            # 상위 제목 저장 (문책사항, 자율처리 필요사항 등)
            parent_title = line.split('.', 1)[1].strip() if '.' in line else line
            # "문책사항" 등에서 추가 텍스트 제거
            parent_title = re.sub(r'\s*[\(（].*', '', parent_title).strip()
            
            current_title = None
            current_content = []
            in_incident = False
            i += 1
            continue
        
        # "가. 일반제목" 또는 "가 . 일반제목" 패턴 (문책사항이 아닌 직접 제목)
        # OCR 텍스트를 위해 점 앞뒤 공백 허용
        first_type_pattern = r'^[가-하]\s*\.\s*(.+)$'
        first_match = re.match(first_type_pattern, line)
        
        if first_match:
            title_text = first_match.group(1).strip()
            
            # 문책사항/자율처리 등이 아닌 경우에만 사건제목으로 사용
            if not re.match(r'^(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항|자율처리)', title_text):
                # 이전 사건 저장
                if current_title and current_content:
                    content_text = '\n'.join(current_content).strip()
                    content_text = remove_page_numbers(content_text)
                    incidents[f'제목{incident_num}'] = current_title
                    incidents[f'내용{incident_num}'] = content_text
                    incident_num += 1
                
                # 새 사건 시작
                current_title = title_text
                current_content = []
                in_incident = True
                parent_title = ""  # 상위 제목 초기화
            i += 1
            continue
        
        # "(1) 제목" 패턴 (줄 시작에서만 매칭!)
        # "(1)", "⑴" 등 전각 괄호 숫자도 지원
        numbered_pattern = r'^(?:[\(（](\d+)[\)）]|[\u2474-\u247C])\s*(.+)$'
        numbered_match = re.match(numbered_pattern, line)
        
        if numbered_match:
            # 이전 사건 저장
            if current_title and current_content:
                content_text = '\n'.join(current_content).strip()
                content_text = remove_page_numbers(content_text)
                incidents[f'제목{incident_num}'] = current_title
                incidents[f'내용{incident_num}'] = content_text
                incident_num += 1
            
            # 새 사건 시작
            if numbered_match.lastindex >= 2 and numbered_match.group(2):
                sub_title = numbered_match.group(2).strip()
            else:
                # ⑴ 패턴인 경우
                sub_title = re.sub(r'^[\u2474-\u247C]\s*', '', line).strip()
            
            # 상위 제목이 있으면 조합
            if parent_title:
                current_title = f"{parent_title} - {sub_title}"
            else:
                current_title = sub_title
            
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # "(가)", "(나)" 등 하위 목차 패턴 - 사건내용으로 처리 (제목이 아님!)
        sub_item_pattern = r'^[\(（]([가나다라마바사아자차카타파하])[\)）]\s*(.*)$'
        sub_item_match = re.match(sub_item_pattern, line)
        
        if sub_item_match:
            # 사건내용으로 추가
            if in_incident and current_title:
                current_content.append(line)
            i += 1
            continue
        
        # 사건 내용으로 추가
        if in_incident and current_title:
            # 다음 "가.", "나." 등이 나오면 중단 (새 사건)
            # OCR 텍스트를 위해 점 앞뒤 공백 허용
            if re.match(r'^[가-하]\s*\.\s*', line):
                i += 1
                continue  # 위에서 처리됨
            # "(1)", "(2)" 등이 줄 시작에 나오면 중단 (새 사건)
            if re.match(r'^[\(（]\d+[\)）]\s*', line) or re.match(r'^[\u2474-\u247C]', line):
                i += 1
                continue  # 위에서 처리됨
            
            current_content.append(line)
        
        i += 1
    
    # 마지막 사건 저장
    if current_title and current_content:
        content_text = '\n'.join(current_content).strip()
        content_text = remove_page_numbers(content_text)
        incidents[f'제목{incident_num}'] = current_title
        incidents[f'내용{incident_num}'] = content_text
    
    return incidents


if __name__ == "__main__":
    # 테스트용
    test_content = """
제 재 내 용 공 개 안

1. 금 융 회 사 명 : 와 이 케 이 자 산 운 용
2. 제 재 조 치 일 : 2025. 12. 3.

3. 제 재 조 치 내 용

제 재 대상 제 재 내 용
기 관 기 관 주 의 및 과 태 료 60 백 만 원

4. 제 재 대 상 사 실
가 . 위 험 관 리 기 준 마 련 의 무 위 반
[」 「 자 본 시 장과 금 융 투 자 업 에 관 한 법 률 ...
나 . 집 합 투 자 규 약 을 위 반 한 불 건 전 한 집 합 투 자 재 산 운 용
[」 ' 자 본 시 장 법 」 제 85 조 등에 의 하 면 ...
다 . 집 합 투 자 재 산 평 가 부 적 정
[| 「 자 본 시 장 법 』 제 238 조 등에 의 하 면 ...
"""
    
    print("=" * 60)
    print("OCR 텍스트 메타데이터 추출 테스트")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content)
    print(f"\n제재내용: {sanction_details[:100]}...")
    
    incidents = extract_incidents(test_content)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:80]}..." if len(value) > 80 else f"  {key}: {value}")

