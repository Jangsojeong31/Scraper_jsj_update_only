"""
PDF 내용에서 메타데이터(제재대상기관, 제재조치요구일, 제재내용) 추출 모듈
"""
import re


def extract_sanction_details(content):
    """
    PDF 내용에서 제재조치내용 표 데이터 추출 (제목행 제외)
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        str: 제재내용 (표의 데이터 행들, 제목행 제외)
    """
    if not content or content.startswith('['):
        return ""
    
    # 3번 항목 제목 패턴 (다양한 형태 지원)
    sanction_patterns = [
        # "3. 제재조치내용" 형식
        r'3\.\s*제\s*재\s*조\s*치\s*내\s*용',
        r'3\.\s*제재조치내용',
        r'3\.\s*제재조치\s*내용',
        r'3\s*\.\s*제\s*재\s*조\s*치\s*내\s*용',
        # "3. 제재내용" 형식
        r'3\.\s*제\s*재\s*내\s*용',
        r'3\.\s*제재내용',
        r'3\.\s*제재\s*내용',
        # "3. 조치내용" 형식
        r'3\.\s*조\s*치\s*내\s*용',
        r'3\.\s*조치내용',
        r'3\.\s*조치\s*내용',
        # "3. 처분내용" 형식
        r'3\.\s*처\s*분\s*내\s*용',
        r'3\.\s*처분내용',
        r'3\.\s*처분\s*내용',
        # "3. 제재조치 세부내용" 형식
        r'3\.\s*제재조치\s*세부\s*내용',
        r'3\.\s*제재\s*조치\s*세부\s*내용',
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
    
    return result.strip()


def extract_incidents(content):
    """
    PDF 내용에서 4번 항목의 사건 제목/내용 추출
    가. 사건제목1 / 사건내용1, 나. 사건제목2 / 사건내용2 형태
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        dict: {'사건제목1': '...', '사건내용1': '...', '사건제목2': '...', ...}
    """
    if not content or content.startswith('['):
        return {}
    
    # 4번 항목 제목 패턴 (다양한 형태 지원)
    section4_patterns = [
        # "4. 제재조치사유" 형식
        r'4\.\s*제\s*재\s*조\s*치\s*사\s*유',
        r'4\.\s*제재조치사유',
        r'4\.\s*제재조치\s*사유',
        # "4. 제재사유" 형식
        r'4\.\s*제\s*재\s*사\s*유',
        r'4\.\s*제재사유',
        r'4\.\s*제재\s*사유',
        # "4. 조치사유" 형식
        r'4\.\s*조\s*치\s*사\s*유',
        r'4\.\s*조치사유',
        r'4\.\s*조치\s*사유',
        # "4. 위반내용" 형식
        r'4\.\s*위\s*반\s*내\s*용',
        r'4\.\s*위반내용',
        r'4\.\s*위반\s*내용',
        # "4. 사유" 형식
        r'4\.\s*사\s*유',
        r'4\.\s*사유',
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
    next_section_match = re.search(r'\n\s*[5-9]\.\s*[가-힣]', remaining_content)
    if next_section_match:
        section_content = remaining_content[:next_section_match.start()]
    else:
        section_content = remaining_content
    
    # 한글 번호 패턴 (가, 나, 다, 라, 마, 바, 사, 아, 자, 차, 카, 타, 파, 하)
    korean_markers = ['가', '나', '다', '라', '마', '바', '사', '아', '자', '차', '카', '타', '파', '하']
    
    # 가. 나. 다. 등으로 시작하는 항목 찾기
    incident_pattern = r'([가나다라마바사아자차카타파하])\.\s*'
    
    # 모든 한글 번호 위치 찾기
    matches = list(re.finditer(incident_pattern, section_content))
    
    if not matches:
        return {}
    
    incidents = {}
    incident_num = 1
    
    for i, match in enumerate(matches):
        # 현재 항목의 시작 위치
        start = match.end()
        
        # 다음 항목의 시작 위치 또는 끝
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(section_content)
        
        # 해당 항목의 내용
        item_content = section_content[start:end].strip()
        
        if not item_content:
            continue
        
        # 첫 번째 줄을 제목으로, 나머지를 내용으로
        lines = item_content.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        if lines:
            title = lines[0]
            content_text = '\n'.join(lines[1:]) if len(lines) > 1 else ""
            
            incidents[f'사건제목{incident_num}'] = title
            incidents[f'사건내용{incident_num}'] = content_text
            incident_num += 1
    
    return incidents


def extract_metadata_from_content(content):
    """
    PDF 내용에서 제재대상기관과 제재조치요구일 추출
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        tuple: (제재대상기관, 제재조치요구일)
    """
    institution = ""
    sanction_date = ""
    
    if not content or content.startswith('['):
        return institution, sanction_date
    
    # 제재대상기관 추출 패턴 (숫자 포함만)
    institution_patterns = [
        # "1. 금융기관명" 형식
        r'1\.\s*금\s*융\s*기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
        r'1\.\s*금융기관명\s*[:：]?\s*([^\n\r]+)',
        r'1\s*\.\s*금\s*융\s*기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
        # "1. 금융회사등 명 :" 형식
        r'1\.\s*금\s*융\s*회\s*사\s*등\s*명\s*[:：]\s*([^\n\r]+)',
        r'1\.\s*금융회사등\s*명\s*[:：]\s*([^\n\r]+)',
        # "1. 기관명 :" 형식
        r'1\.\s*기\s*관\s*명\s*[:：]\s*([^\n\r]+)',
    ]
    
    for pattern in institution_patterns:
        match = re.search(pattern, content)
        if match:
            institution = match.group(1).strip()
            institution = institution.split('\n')[0].strip()
            institution = re.sub(r'^[:\-\.\s]+', '', institution)
            institution = re.sub(r'[\-\.\s]+$', '', institution)
            if institution:
                break
    
    # 제재조치요구일 추출 패턴 (숫자 포함만)
    date_patterns = [
        # "2. 제재조치일" 형식
        r'2\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        r'2\.\s*제재조치일\s*[:：]?\s*([^\n\r]+)',
        r'2\s*\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        # "2. 제재조치 일자 :" 형식
        r'2\.\s*제\s*재\s*조\s*치\s*일\s*자\s*[:：]\s*([^\n\r]+)',
        r'2\.\s*제재조치\s*일자\s*[:：]\s*([^\n\r]+)',
        # "2. 조치일 :" 형식
        r'2\.\s*조\s*치\s*일\s*[:：]\s*([^\n\r]+)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, content)
        if match:
            sanction_date = match.group(1).strip()
            sanction_date = sanction_date.split('\n')[0].strip()
            sanction_date = re.sub(r'^[:\-\.\s]+', '', sanction_date)
            sanction_date = re.sub(r'[\-\.\s]+$', '', sanction_date)
            if sanction_date:
                break
    
    return institution, sanction_date


if __name__ == "__main__":
    # 테스트용 예시
    test_content = """
    1. 금융기관명: 테스트은행
    2. 제재조치일: 2024. 5. 15.
    3. 제재조치내용
    대상자    조치내용    근거법령
    홍길동    경고    자금세탁방지법 제5조
    김철수    주의    자금세탁방지법 제7조
    4. 제재조치사유
    가. 자금세탁방지의무 위반
    고객확인의무를 이행하지 않고 거래를 진행함
    나. 의심거래보고의무 위반
    의심거래를 보고하지 않음
    다. 내부통제 미흡
    내부통제시스템을 제대로 운영하지 않음
    5. 기타사항: 없음
    """
    
    institution, sanction_date = extract_metadata_from_content(test_content)
    print(f"제재대상기관: {institution}")
    print(f"제재조치요구일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content)
    print(f"\n사건 추출 결과:")
    for key, value in incidents.items():
        print(f"  {key}: {value[:50]}..." if len(value) > 50 else f"  {key}: {value}")

