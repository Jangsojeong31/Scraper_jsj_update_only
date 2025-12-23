"""
PDF 내용에서 메타데이터(금융회사명, 제재조치일, 제재내용) 추출 모듈
"""
import re

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


def remove_page_numbers(text):
    """
    텍스트에서 페이지 번호 패턴 제거
    예: "- 1 -", "- 2 -", "- 10 -" 등
    
    Args:
        text: 원본 텍스트
        
    Returns:
        str: 페이지 번호가 제거된 텍스트
    """
    if not text:
        return text
    
    # 페이지 번호 패턴: "- 숫자 -" (앞뒤 공백 포함)
    # 줄 전체가 페이지 번호인 경우 해당 줄 제거
    text = re.sub(r'\n\s*-\s*\d+\s*-\s*\n', '\n', text)
    # 문장 중간에 있는 페이지 번호도 제거
    text = re.sub(r'\s*-\s*\d+\s*-\s*', ' ', text)
    
    return text.strip()


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
    
    # 먼저 "Ⅲ. 재조치 내용" 패턴 체크 (재조치 패턴 우선)
    rejaechae_section_patterns = [
        r'[Ⅲ3]\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'[Ⅲ3]\s*[\.．]\s*재조치\s*내용',
        r'[Ⅲ3]\s*[\.．]\s*재조치내용',
        r'Ⅲ\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'Ⅲ\s*[\.．]\s*재조치\s*내용',
    ]
    
    rejaechae_section_start = None
    for pattern in rejaechae_section_patterns:
        match = re.search(pattern, content)
        if match:
            rejaechae_section_start = match.start()
            break
    
    # "Ⅲ. 재조치 내용" 섹션이 있으면 그 안에서 "재조치 대상자 및 제재종류" 찾기
    if rejaechae_section_start is not None:
        # "Ⅲ. 재조치 내용" 섹션의 끝 찾기 (다음 로마숫자 섹션 또는 문서 끝)
        remaining_after_rejaechae = content[rejaechae_section_start:]
        next_section_match = re.search(r'\n\s*[Ⅳ4]\s*[\.．]\s*[가-힣]', remaining_after_rejaechae)
        if next_section_match:
            rejaechae_section = remaining_after_rejaechae[:next_section_match.start()]
        else:
            rejaechae_section = remaining_after_rejaechae
        
        # "재조치 대상자 및 제재종류", "대상자 및 재조치내용", "재조치내용" 패턴 찾기
        rejaechae_sanction_patterns = [
            r'재\s*조\s*치\s*대\s*상\s*자\s*및\s*제\s*재\s*종\s*류',
            r'재조치\s*대상자\s*및\s*제재종류',
            r'대\s*상\s*자\s*및\s*재\s*조\s*치\s*내\s*용',
            r'대상자\s*및\s*재조치내용',
            r'대상자\s*및\s*재\s*조\s*치\s*내\s*용',
            r'2\.\s*재\s*조\s*치\s*내\s*용',
            r'2\.\s*재조치\s*내용',
            r'2\.\s*재조치내용',
            r'재\s*조\s*치\s*내\s*용',
            r'재조치\s*내용',
            r'재조치내용',
        ]
        
        sanction_start_pos = None
        for pattern in rejaechae_sanction_patterns:
            match = re.search(pattern, rejaechae_section)
            if match:
                sanction_start_pos = match.end()
                break
        
        if sanction_start_pos is not None:
            # "재조치 대상자 및 제재종류" 또는 "대상자 및 재조치내용" 이후 내용 추출
            remaining_after_sanction = rejaechae_section[sanction_start_pos:]
            
            # 다음 항목(2. 재조치대상사실 등) 또는 문서 끝까지의 내용 추출
            next_section_match = re.search(r'\n\s*[2-9]\.\s*[가-힣]', remaining_after_sanction)
            if next_section_match:
                sanction_content = remaining_after_sanction[:next_section_match.start()]
            else:
                sanction_content = remaining_after_sanction
            
            # "◦", "○", "□", "※" 등으로 시작하는 줄 추출
            lines = sanction_content.split('\n')
            sanction_lines = []
            for line in lines:
                line = line.strip()
                if line and (line.startswith('◦') or line.startswith('○') or line.startswith('●') or line.startswith('◯')):
                    # 기호 제거하고 내용만 추출
                    line = re.sub(r'^[◦○●◯]\s*', '', line)
                    sanction_lines.append(line)
                elif line and (line.startswith('□') or line.startswith('■') or line.startswith('▣') or line.startswith('▢')):
                    # "□"로 시작하는 줄도 추출 (대상자 및 재조치내용 패턴)
                    line = re.sub(r'^[□■▣▢]\s*', '', line)
                    sanction_lines.append(line)
                elif line and line.startswith('※'):
                    # "※"로 시작하는 줄도 추출 (재조치내용 패턴)
                    line = re.sub(r'^※\s*', '', line)
                    sanction_lines.append(line)
                elif line and not re.match(r'^[가-힣]\s*[\.．]', line) and not re.match(r'^[1-9]\.', line):  # "가.", "2." 같은 패턴이 아니면
                    sanction_lines.append(line)
            
            if sanction_lines:
                result = '\n'.join(sanction_lines)
                result = remove_page_numbers(result)
                return result.strip()
        
        # 패턴이 없으면 빈 문자열 반환 (재조치 섹션이지만 제재종류가 없는 경우)
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
        # 숫자 없이 "제재조치내용"만 있는 형식
        r'^제\s*재\s*조\s*치\s*내\s*용\s*[:：]?',
        r'^제재조치내용\s*[:：]?',
        r'\n제\s*재\s*조\s*치\s*내\s*용\s*[:：]?',
        r'\n제재조치내용\s*[:：]?',
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
    # * 또는 숫자로 시작하는 "조치사유", "제재사유", "제재대상사실" 앞까지만 추출
    reason_patterns = [
        r'\*?\s*조\s*치\s*사\s*유',
        r'\*?\s*제\s*재\s*사\s*유',
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


def extract_incidents(content):
    """
    PDF 내용에서 4번 항목의 사건 제목/내용 추출
    (extract_sanctions.py의 줄 단위 처리 방식 참고)
    
    지원하는 형식:
    1. 가. 제목1 / 내용1, 나. 제목2 / 내용2 형태
    2. 가. 문책사항 (1) 제목1 / 내용1 (2) 제목2 / 내용2 형태
    3. 가. (1) 제목 (가) 내용 (나) 내용 형태 -> (가), (나)는 내용으로 처리
    4. Ⅲ. 재조치 내용 > 2. 재조치대상사실 패턴
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        dict: {'제목1': '...', '내용1': '...', '제목2': '...', ...}
    """
    if not content or content.startswith('['):
        return {}
    
    # 먼저 "Ⅲ. 재조치 내용" 패턴 체크 (재조치 패턴 우선)
    rejaechae_section_patterns = [
        r'[Ⅲ3]\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'[Ⅲ3]\s*[\.．]\s*재조치\s*내용',
        r'[Ⅲ3]\s*[\.．]\s*재조치내용',
        r'Ⅲ\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'Ⅲ\s*[\.．]\s*재조치\s*내용',
    ]
    
    rejaechae_section_start = None
    for pattern in rejaechae_section_patterns:
        match = re.search(pattern, content)
        if match:
            rejaechae_section_start = match.start()
            break
    
    # "Ⅲ. 재조치 내용" 섹션이 있으면 그 안에서 "재조치대상사실" 찾기
    if rejaechae_section_start is not None:
        # "Ⅲ. 재조치 내용" 섹션의 끝 찾기 (다음 로마숫자 섹션 또는 문서 끝)
        remaining_after_rejaechae = content[rejaechae_section_start:]
        next_section_match = re.search(r'\n\s*[Ⅳ4]\s*[\.．]\s*[가-힣]', remaining_after_rejaechae)
        if next_section_match:
            rejaechae_section = remaining_after_rejaechae[:next_section_match.start()]
        else:
            rejaechae_section = remaining_after_rejaechae
        
        # "재조치대상사실" 패턴 찾기
        rejaechae_incident_patterns = [
            r'2\.\s*재\s*조\s*치\s*대\s*상\s*사\s*실',
            r'2\.\s*재조치대상사실',
            r'2\.\s*재조치대상\s*사실',
            r'재\s*조\s*치\s*대\s*상\s*사\s*실',
            r'재조치대상사실',
            r'재조치대상\s*사실',
        ]
        
        start_pos = None
        for pattern in rejaechae_incident_patterns:
            match = re.search(pattern, rejaechae_section)
            if match:
                start_pos = match.end()
                break
        
        if start_pos is not None:
            # "재조치대상사실" 이후 내용 추출
            remaining_content = rejaechae_section[start_pos:]
            
            # 다음 번호 항목(3., 4. 등) 또는 문서 끝까지의 내용 추출
            next_section_match = re.search(r'\n\s*[3-9]\.\s*[가-힣]', remaining_content)
            if next_section_match:
                section_text = remaining_content[:next_section_match.start()]
            else:
                section_text = remaining_content
            
            # 기존 extract_incidents 로직 재사용
            return _extract_incidents_from_section(section_text)
    
    # 4번 항목 제목 패턴 (다양한 형태 지원)
    section4_patterns = [
        # "4. 제재대상사실" 형식 (실제 PDF에서 사용)
        r'4\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'4\.\s*제재대상사실',
        r'4\.\s*제재대상\s*사실',
        # "4. 조치대상사실" 형식
        r'4\.\s*조\s*치\s*대\s*상\s*사\s*실',
        r'4\.\s*조치대상사실',
        r'4\.\s*조치대상\s*사실',
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
        # 숫자 없이 "제재대상사실"만 있는 형식 (앞뒤 공백 허용, OCR 변형 고려)
        # re.search()를 사용하므로 어디서든 매칭 가능하도록 유연한 패턴 사용
        r'(?:^|\n|\s+)제\s*재\s*대\s*상\s*사\s*실\s*[:：]?(?:\s*\n|$)',
        r'(?:^|\n|\s+)제재대상사실\s*[:：]?(?:\s*\n|$)',
        # 줄바꿈 뒤에 오는 경우 (더 명확한 패턴)
        r'\n\s*제\s*재\s*대\s*상\s*사\s*실\s*[:：]?\s*\n',
        r'\n\s*제재대상사실\s*[:：]?\s*\n',
        # 줄 시작에서 오는 경우
        r'^제\s*재\s*대\s*상\s*사\s*실\s*[:：]?',
        r'^제재대상사실\s*[:：]?',
    ]
    
    start_pos = None
    for pattern in section4_patterns:
        match = re.search(pattern, content)
        if match:
            start_pos = match.end()
            break
    
    # 숫자 패턴이 없으면 로마숫자 패턴 체크 (Ⅳ. 제재대상사실 등)
    if start_pos is None:
        # 로마숫자 패턴 (Ⅳ, 4 등)
        roman_section4_patterns = [
            # "Ⅳ. 제재대상사실" 형식
            r'[Ⅳ4]\s*[\.．]\s*제\s*재\s*대\s*상\s*사\s*실',
            r'[Ⅳ4]\s*[\.．]\s*제재대상사실',
            r'[Ⅳ4]\s*[\.．]\s*제재대상\s*사실',
            # "Ⅳ. 조치대상사실" 형식
            r'[Ⅳ4]\s*[\.．]\s*조\s*치\s*대\s*상\s*사\s*실',
            r'[Ⅳ4]\s*[\.．]\s*조치대상사실',
            r'[Ⅳ4]\s*[\.．]\s*조치대상\s*사실',
            # "Ⅳ. 제재조치사유" 형식
            r'[Ⅳ4]\s*[\.．]\s*제\s*재\s*조\s*치\s*사\s*유',
            r'[Ⅳ4]\s*[\.．]\s*제재조치사유',
            r'[Ⅳ4]\s*[\.．]\s*제재조치\s*사유',
            # "Ⅳ. 제재사유" 형식
            r'[Ⅳ4]\s*[\.．]\s*제\s*재\s*사\s*유',
            r'[Ⅳ4]\s*[\.．]\s*제재사유',
            r'[Ⅳ4]\s*[\.．]\s*제재\s*사유',
            # "Ⅳ. 조치사유" 형식
            r'[Ⅳ4]\s*[\.．]\s*조\s*치\s*사\s*유',
            r'[Ⅳ4]\s*[\.．]\s*조치사유',
            r'[Ⅳ4]\s*[\.．]\s*조치\s*사유',
            # "Ⅳ. 위반내용" 형식
            r'[Ⅳ4]\s*[\.．]\s*위\s*반\s*내\s*용',
            r'[Ⅳ4]\s*[\.．]\s*위반내용',
            r'[Ⅳ4]\s*[\.．]\s*위반\s*내용',
            # "Ⅳ. 사유" 형식
            r'[Ⅳ4]\s*[\.．]\s*사\s*유',
            r'[Ⅳ4]\s*[\.．]\s*사유',
        ]
        
        for pattern in roman_section4_patterns:
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
        section_text = remaining_content[:next_section_match.start()]
    else:
        section_text = remaining_content
    
    # 기존 extract_incidents 로직 재사용
    return _extract_incidents_from_section(section_text)


def _extract_incidents_from_section(section_text):
    """
    섹션 텍스트에서 사건 제목/내용 추출 (공통 로직)
    
    Args:
        section_text: 추출할 섹션 텍스트
        
    Returns:
        dict: {'제목1': '...', '내용1': '...', '제목2': '...', ...}
    """
    # 줄 단위로 처리 (extract_sanctions.py 방식)
    lines = section_text.split('\n')
    
    # "가." 패턴이 있는지 먼저 확인
    has_ga_pattern = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[가]\s*[._]\s*', stripped):
            has_ga_pattern = True
            break
    
    incidents = {}
    incident_num = 1
    
    current_title = None
    current_content = []
    in_incident = False
    parent_title = ""  # 상위 제목 (가. 문책사항 등)
    is_unified_incident = False  # 통합 사건 모드 (가. 일반제목 -> 모든 (1), (2)를 하나의 사건으로)
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # "가. 문책사항" 또는 "가 . 문 책 사 항" 패턴 체크 (상위 제목)
        # OCR 텍스트를 위해 점 앞뒤 공백 허용, 또한 "가_" 같은 패턴도 허용
        header_pattern = r'^[가-하]\s*[._]\s*(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항|자율처리\s*필요사항)(.*)$'
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
        # OCR 텍스트를 위해 점 앞뒤 공백 허용, 또한 "가_" 같은 패턴도 허용
        first_type_pattern = r'^[가-하]\s*[._]\s*(.+)$'
        first_match = re.match(first_type_pattern, line)
        
        if first_match:
            title_text = first_match.group(1).strip()
            
            # 문책사항/자율처리 등이 아닌 경우
            if not re.match(r'^(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항|자율처리)', title_text):
                # 이전 사건 저장
                if current_title and current_content:
                    content_text = '\n'.join(current_content).strip()
                    content_text = remove_page_numbers(content_text)
                    incidents[f'제목{incident_num}'] = current_title
                    incidents[f'내용{incident_num}'] = content_text
                    incident_num += 1
                elif current_title:  # 제목만 있고 내용이 없는 경우도 저장
                    incidents[f'제목{incident_num}'] = current_title
                    incidents[f'내용{incident_num}'] = ''
                    incident_num += 1
                
                # "문책", "책임", "자율처리", "주의" 같은 특정 키워드가 있으면 기존 패턴 (각 (1), (2)를 별도 사건)
                # 그렇지 않으면 새로운 패턴 (모든 (1), (2)를 하나의 사건으로)
                has_special_keyword = re.search(r'(문책|책임|자율처리|주의)', title_text)
                
                if has_special_keyword:
                    # 기존 패턴: "나. 주의사항" -> 각 (1), (2)를 별도 사건으로
                    parent_title = title_text
                    current_title = None  # "(1)"이 나올 때까지 제목 없음
                    current_content = []
                    in_incident = False
                    is_unified_incident = False
                else:
                    # 새로운 패턴: "가. 일반제목" -> 모든 (1), (2)를 하나의 사건으로
                    parent_title = title_text
                    current_title = title_text  # 즉시 사건 시작
                    current_content = []
                    in_incident = True
                    is_unified_incident = True
            i += 1
            continue
        
        # "1) 내용" 패턴 체크 (숫자 뒤에 바로 괄호, 내용으로 처리)
        # "(1) 제목" 패턴과 구분하기 위해 먼저 체크
        numbered_content_pattern = r'^(\d+)\s*[\)）]\s*(.+)$'
        numbered_content_match = re.match(numbered_content_pattern, line)
        
        if numbered_content_match and not re.match(r'^[\(（]', line):
            # 괄호가 앞에 없고 숫자 뒤에 바로 괄호가 있는 경우 내용으로 처리
            if in_incident and current_title:
                current_content.append(line)
            i += 1
            continue
        
        # "(1) 제목" 패턴 (줄 시작에서만 매칭!)
        # "(1)", "⑴" 등 전각 괄호 숫자도 지원
        # 괄호가 앞에 있어야 함
        numbered_pattern = r'^(?:[\(（](\d+)[\)）]|[\u2474-\u247C])\s*(.+)$'
        numbered_match = re.match(numbered_pattern, line)
        
        if numbered_match:
            # 하위 제목 추출
            if numbered_match.lastindex >= 2 and numbered_match.group(2):
                sub_title = numbered_match.group(2).strip()
            else:
                # ⑴ 패턴인 경우
                sub_title = re.sub(r'^[\u2474-\u247C]\s*', '', line).strip()
            
            # 통합 사건 모드인 경우: "(1)", "(2)" 등을 모두 내용으로 처리
            if is_unified_incident and current_title == parent_title:
                # 현재 사건이 통합 사건 모드이고, 제목이 parent_title과 같으면
                # "(1)", "(2)" 등을 모두 내용으로 추가
                current_content.append(line)
                i += 1
                continue
            
            # 기존 패턴: 각 "(1)", "(2)"를 별도 사건으로 처리
            # 이전 사건 저장
            if current_title and current_content:
                content_text = '\n'.join(current_content).strip()
                content_text = remove_page_numbers(content_text)
                incidents[f'제목{incident_num}'] = current_title
                incidents[f'내용{incident_num}'] = content_text
                incident_num += 1
            elif current_title:  # 제목만 있고 내용이 없는 경우도 저장
                incidents[f'제목{incident_num}'] = current_title
                incidents[f'내용{incident_num}'] = ''
                incident_num += 1
            
            # 새 사건 시작
            # parent_title이 있으면 "상위제목 - 하위제목" 형식으로, 없으면 하위제목만
            if parent_title:
                current_title = f"{parent_title} - {sub_title}"
            else:
                current_title = sub_title
            current_content = []
            
            in_incident = True
            is_unified_incident = False  # 하위 항목은 통합 모드 해제
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
        
        # "□ 제목" 패턴 체크 (사각형 기호로 시작하는 사건 제목)
        # "가." 패턴이 없을 때만 체크 (서로 다른 문서 형식)
        # OCR 텍스트를 위해 다양한 사각형 기호 지원 (□, ■, ▣ 등)
        if not has_ga_pattern:
            square_pattern = r'^[□■▣▢]\s*(.+)$'
            square_match = re.match(square_pattern, line)
            
            if square_match:
                # 이전 사건 저장
                if current_title and current_content:
                    content_text = '\n'.join(current_content).strip()
                    content_text = remove_page_numbers(content_text)
                    incidents[f'제목{incident_num}'] = current_title
                    incidents[f'내용{incident_num}'] = content_text
                    incident_num += 1
                
                # 새 사건 시작
                current_title = square_match.group(1).strip()
                current_content = []
                in_incident = True
                i += 1
                continue
            
            # "◦ 내용" 또는 "○ 내용" 패턴 체크 (원형 기호로 시작하는 사건 내용)
            # "가." 패턴이 없을 때만 체크
            # OCR 텍스트를 위해 다양한 원형 기호 지원 (◦, ○, ●, ◯ 등)
            circle_pattern = r'^[◦○●◯]\s*(.+)$'
            circle_match = re.match(circle_pattern, line)
            
            if circle_match:
                # 사건 내용으로 추가
                if in_incident and current_title:
                    current_content.append(line)
                i += 1
                continue
            
            # "<관련법규>" 섹션 체크 - 사건 내용에 포함시키고, 이후 새로운 사건이 나오면 종료
            if re.match(r'^<관련법규>', line) or re.match(r'^<관련\s*법규>', line):
                # "<관련법규>" 섹션도 사건 내용에 포함
                if in_incident and current_title:
                    current_content.append(line)
                    # "<관련법규>" 섹션 이후의 내용도 계속 수집 (다음 "□" 또는 "가." 패턴이 나올 때까지)
                    i += 1
                    continue
                else:
                    # 사건이 시작되지 않은 상태에서 "<관련법규>"가 나오면 건너뛰기
                    i += 1
                    continue
        
        # 사건 내용으로 추가
        if in_incident and current_title:
            # 다음 "가.", "나." 등이 나오면 중단 (새 사건)
            # OCR 텍스트를 위해 점 앞뒤 공백 허용, 또한 "가_" 같은 패턴도 허용
            if re.match(r'^[가-하]\s*[._]\s*', line):
                i += 1
                continue  # 위에서 처리됨
            # "(1)", "(2)" 등이 줄 시작에 나오면 중단 (새 사건) - 통합 사건 모드가 아닐 때만
            if not is_unified_incident:
                if re.match(r'^[\(（]\d+[\)）]\s*', line) or re.match(r'^[\u2474-\u247C]', line):
                    i += 1
                    continue  # 위에서 처리됨
            # "□" 패턴은 내용으로 포함 (모든 경우)
            
            current_content.append(line)
        
        i += 1
    
    # 마지막 사건 저장
    if current_title:
        if current_content:
            content_text = '\n'.join(current_content).strip()
            content_text = remove_page_numbers(content_text)
            incidents[f'제목{incident_num}'] = current_title
            incidents[f'내용{incident_num}'] = content_text
        else:
            # 제목만 있고 내용이 없는 경우도 저장
            incidents[f'제목{incident_num}'] = current_title
            incidents[f'내용{incident_num}'] = ''
    
    return incidents


def format_date_to_iso(date_str):
    """
    날짜 문자열을 YYYY-MM-DD 형식으로 변환
    
    Args:
        date_str: 다양한 형식의 날짜 문자열 (예: "2024. 5. 15.", "2025-10-20", "2024년 5월 15일")
        
    Returns:
        str: YYYY-MM-DD 형식의 날짜 문자열 (변환 실패 시 원본 반환)
    """
    if not date_str:
        return date_str
    
    # 숫자만 추출 (년, 월, 일)
    numbers = re.findall(r'\d+', date_str)
    
    if len(numbers) >= 3:
        year = numbers[0]
        month = numbers[1].zfill(2)  # 한 자리 월은 0으로 패딩
        day = numbers[2].zfill(2)     # 한 자리 일은 0으로 패딩
        
        # 유효성 검사
        try:
            year_int = int(year)
            month_int = int(month)
            day_int = int(day)
            
            # 기본적인 유효성 검사
            if 1900 <= year_int <= 2100 and 1 <= month_int <= 12 and 1 <= day_int <= 31:
                return f"{year}-{month}-{day}"
        except ValueError:
            pass
    
    # 변환 실패 시 원본 반환
    return date_str


def extract_metadata_from_content(content):
    """
    PDF 내용에서 금융회사명과 제재조치일 추출
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        tuple: (금융회사명, 제재조치일)
    """
    institution = ""
    sanction_date = ""
    
    if not content or content.startswith('['):
        return institution, sanction_date
    
    # 금융회사명 추출 패턴
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
        # 숫자 없이 "기관명"만 있는 형식
        r'^기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
        r'^기관명\s*[:：]?\s*([^\n\r]+)',
        r'\n기\s*관\s*명\s*[:：]?\s*([^\n\r]+)',
        r'\n기관명\s*[:：]?\s*([^\n\r]+)',
    ]
    
    for pattern in institution_patterns:
        match = re.search(pattern, content)
        if match:
            institution = match.group(1).strip()
            institution = institution.split('\n')[0].strip()
            institution = re.sub(r'^[:\-\.\s]+', '', institution)
            institution = re.sub(r'[\-\.\s]+$', '', institution)
            # 마지막 '*', '@' 제거
            institution = institution.rstrip('*@')
            if institution:
                break
    
    # 제재조치일 추출 패턴
    # 먼저 "Ⅲ. 재조치 내용" 패턴 체크 (재조치 패턴 우선)
    rejaechae_section_patterns = [
        r'[Ⅲ3]\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'[Ⅲ3]\s*[\.．]\s*재조치\s*내용',
        r'[Ⅲ3]\s*[\.．]\s*재조치내용',
        r'Ⅲ\s*[\.．]\s*재\s*조\s*치\s*내\s*용',
        r'Ⅲ\s*[\.．]\s*재조치\s*내용',
    ]
    
    rejaechae_section_start = None
    for pattern in rejaechae_section_patterns:
        match = re.search(pattern, content)
        if match:
            rejaechae_section_start = match.start()
            break
    
    # "Ⅲ. 재조치 내용" 섹션이 있으면 그 안에서 "재조치 일자" 찾기
    if rejaechae_section_start is not None:
        # "Ⅲ. 재조치 내용" 섹션의 끝 찾기 (다음 로마숫자 섹션 또는 문서 끝)
        remaining_after_rejaechae = content[rejaechae_section_start:]
        next_section_match = re.search(r'\n\s*[Ⅳ4]\s*[\.．]\s*[가-힣]', remaining_after_rejaechae)
        if next_section_match:
            rejaechae_section = remaining_after_rejaechae[:next_section_match.start()]
        else:
            rejaechae_section = remaining_after_rejaechae
        
        # "재조치 일자" 또는 "재조치일자" 패턴 찾기
        rejaechae_date_patterns = [
            r'재\s*조\s*치\s*일\s*자\s*[:：]?\s*([^\n\r]+)',
            r'재조치\s*일\s*자\s*[:：]?\s*([^\n\r]+)',
            r'재조치\s*일자\s*[:：]?\s*([^\n\r]+)',
            r'재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
            r'재조치일\s*[:：]?\s*([^\n\r]+)',
            r'재\s*조\s*치\s*일자\s*[:：]?\s*([^\n\r]+)',
            r'재조치일자\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*재\s*조\s*치\s*일\s*자\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*재조치\s*일\s*자\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*재조치\s*일자\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*재조치일\s*[:：]?\s*([^\n\r]+)',
            r'1\.\s*재조치일자\s*[:：]?\s*([^\n\r]+)',
        ]
        
        for pattern in rejaechae_date_patterns:
            match = re.search(pattern, rejaechae_section)
            if match:
                sanction_date = match.group(1).strip()
                sanction_date = sanction_date.split('\n')[0].strip()
                sanction_date = re.sub(r'^[:\-\.\s]+', '', sanction_date)
                sanction_date = re.sub(r'[\-\.\s]+$', '', sanction_date)
                if sanction_date:
                    # 날짜 포맷을 YYYY-MM-DD 형식으로 변환
                    sanction_date = format_date_to_iso(sanction_date)
                    break
        
        if sanction_date:
            return institution, sanction_date
    
    # 기존 패턴 (일반 제재조치일 패턴)
    date_patterns = [
        # "2. 제재조치 일자 :" 형식 (다양한 공백 패턴) - 먼저 검사
        r'2\.\s*제\s*재\s*조\s*치\s+일\s*자\s*[:：]?\s*([^\n\r]+)',
        r'2\.\s*제재조치\s+일\s*자\s*[:：]?\s*([^\n\r]+)',
        r'2\.\s*제재조치\s*일자\s*[:：]?\s*([^\n\r]+)',
        # "2. 제재조치일" 형식
        r'2\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        r'2\.\s*제재조치일\s*[:：]?\s*([^\n\r]+)',
        r'2\s*\.\s*제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        # "2. 조치일 :" 형식
        r'2\.\s*조\s*치\s*일\s*[:：]\s*([^\n\r]+)',
        # 숫자 없이 "제재조치일"만 있는 형식
        r'^제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        r'^제재조치일\s*[:：]?\s*([^\n\r]+)',
        r'\n제\s*재\s*조\s*치\s*일\s*[:：]?\s*([^\n\r]+)',
        r'\n제재조치일\s*[:：]?\s*([^\n\r]+)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, content)
        if match:
            sanction_date = match.group(1).strip()
            sanction_date = sanction_date.split('\n')[0].strip()
            sanction_date = re.sub(r'^[:\-\.\s]+', '', sanction_date)
            sanction_date = re.sub(r'[\-\.\s]+$', '', sanction_date)
            if sanction_date:
                # 날짜 포맷을 YYYY-MM-DD 형식으로 변환
                sanction_date = format_date_to_iso(sanction_date)
                break
    
    return institution, sanction_date


if __name__ == "__main__":
    # 테스트용 예시 1: 기본 형태 (가. 나. 다.)
    test_content1 = """
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
    
    # 테스트용 예시 2: 중첩 형태 (가. (1) (2) 나. (1) (2))
    test_content2 = """
    1. 금융기관명: 현대차증권
    2. 제재조치일: 2025. 10.15.
    3. 제재조치내용
    기 관 과태료 220,200,000 원 부과
    4. 제재대상사실
    가. 고객확인 의무 위반
    (1) 국적 및 실제 소유자 미확인
    □ 금융회사등은 계좌를 신규 개설하는 경우 외국인 고객에 대하여는 국적을 확인하여야 함에도
    ㅇ 현대차증권은 외국인 고객 1명의 국적을 확인하지 않았음
    (2) 고위험 고객에 대한 추가정보 미확인
    □ 금융회사등은 고객이 자금세탁행위를 할 우려가 있는 경우 거래자금의 원천 등을 확인하여야 함에도
    ㅇ 현대차증권은 11건의 계좌개설에 대해 추가적인 정보를 확인하지 않았음
    나. 고액 현금거래 보고의무 위반
    □ 금융회사등은 1천만원 이상의 현금을 지급하거나 영수한 경우 30일 이내에 보고하여야 함에도
    ㅇ 현대차증권은 고액 현금거래 총 4건을 보고기한 내에 보고하지 아니하였음
    <관련법규>
    특정금융정보법 제4조의 2
    5. 기타사항: 없음
    """
    
    # 테스트용 예시 3: 3단계 중첩 형태 (가. (1) (가) (나) (2) (가) (나))
    test_content3 = """
    1. 금융기관명: 삼성증권
    2. 제재조치일: 2025. 10.20.
    3. 제재조치내용
    기 관 과태료 500,000,000 원 부과
    4. 제재대상사실
    가. 문책사항
    (1) 투자자 보호의무 위반
    (가) 고객 정보 미확인
    □ 금융회사는 고객의 투자성향을 반드시 확인해야 함에도
    ㅇ 삼성증권은 100명의 고객 정보를 확인하지 않았음
    < 관련법규 >
    1. 자본시장법 제47조
    (나) 부적합 상품 판매
    □ 금융회사는 고객 투자성향에 맞는 상품만 판매해야 함에도
    ㅇ 삼성증권은 50건의 부적합 상품을 판매하였음
    < 관련법규 >
    1. 자본시장법 제46조
    (2) 내부통제 미흡
    (가) 준법감시 체계 부실
    □ 금융회사는 적절한 준법감시 체계를 갖추어야 함에도
    ㅇ 삼성증권은 준법감시 인력이 부족하였음
    (나) 위험관리 체계 미비
    □ 금융회사는 위험관리 체계를 구축해야 함에도
    ㅇ 삼성증권은 위험관리 시스템이 미비하였음
    나. 주의사항
    단순 절차 위반으로 주의 조치함
    5. 기타사항: 없음
    """
    
    print("=" * 60)
    print("테스트 1: 기본 형태 (가. 나. 다.)")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content1)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content1)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content1)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:50]}..." if len(value) > 50 else f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("테스트 2: 중첩 형태 (가. (1) (2) 나.)")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content2)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content2)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content2)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:80]}..." if len(value) > 80 else f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("테스트 3: 3단계 중첩 형태 (가. (1) (가) (나) (2) (가) (나))")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content3)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content3)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content3)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:100]}..." if len(value) > 100 else f"  {key}: {value}")
    
    # 테스트용 예시 4: 재조치 내용 패턴
    test_content4 = """
    Ⅰ. 재심취지
    
    □ (대구)해성신용협동조합 前임원 甲이 '동일인 대출한도 초과 취급 등' 관련'개선(改選)' 처분에 불복하여 제기(2022.6.23.)한 행정소송에서
    ◦ 법원이 조치양정의 재량권 일탈‧남용 등을 이유로 동 처분을 취소함에 따라법원판결의 취지를 감안하여 前임원 甲에 대한 양정을 조정한 후 재조치하려는것임
    
    Ⅱ. 당초 조치내용
    
    1. 조치개요
    □ 제재일자 : 2020. 7. 24.
    □ 제재대상자 및 제재종류
    ◦ 임원 甲[개선(改選)]
    
    2. 조치대상사실
    가. 문책사항
    (1) 동일인 대출한도 초과 취급
    □ 관련 내용...
    
    Ⅲ. 재조치 내용
    
    1. 조치개요
    □ 재조치 일자 : 2024. 12. 26.
    □ 재조치 대상자 및 제재종류
    ◦ 前임원 甲[개선(改選)] → 퇴직자 위법·부당사항(직무정지3월 상당)
    
    2. 재조치대상사실
    가. 문책사항
    (1) 동일인 대출한도 초과 취급
    □ ｢신용협동조합법｣ 제42조 및 ｢동법 시행령｣ 제16조의4 등에 의하면 조합은 동일인에대하여 자기자본의 100분의 20 또는 자산총액의 100분의 1 중 큰 금액의범위에서 금융위원회가 정하는 한도를 초과하여 대출을 할 수 없으며, 본인의계산으로 다른 사람의 명의에 의하여 하는 대출등은 이를 그 본인의 대출등으로보아야 하는데도
    (대구)해성신용협동조합은 2005.3.30.～2018.7.2. 기간 중 乙 등 8명의 차주에대하여본인 또는 제3자 명의를 이용하는 방법으로 보통대출금 등 95건, 151억 25백만원을취급하여 2014.12.31. 현재 동일인 대출한도(5억원)를 최고 21억 34백만원(총자산의3.8%) 초과한 사실이 있음
    
    < 관련규정 >
    1. ｢신용협동조합법｣ 제42조, 제84조
    2. ｢신용협동조합법시행령｣ 제16조의4
    3. ｢상호금융업감독규정｣ 제6조
    
    나. 주의사항
    (1) 직원대출 취급 불철저
    □ ｢신용협동조합법｣ 제39조, ｢상호금융업감독규정｣ 제4조, ｢신용협동조합여수신업무방법기준｣ 제14조에 의하면 조합은 임직원에 대하여 생활안정자금, 주택관련자금, 사고금정리자금 및 임직원 소유 주택담보대출등 제한된 범위내에서취급하여야 하고, 임직원 본인 소유 주택 이외에는 다른 부동산 등을담보로하는 대출을 취급할 수 없는데도
    (대구)해성신용협동조합은 2009.11.27., 2018.7.24. ○○(직급) 丙 등 2명의직원에대하여 제3자 명의(모친, 배우자)를 이용하는 방법으로 토지를 담보로 보통대출금2건, 50백만원(검사착수일 현재 대출잔액 40백만원)의 대출을 부당하게취급한사실이 있음
    
    < 관련규정 >
    1. ｢신용협동조합법｣ 제39조, 제84조
    2. ｢상호금융업감독규정｣ 제4조
    
    (2) 예금잔액증명서 발급 불철저
    □ ｢신용협동조합법｣ 제39조, ｢상호금융업감독규정｣ 제4조 및 ｢신용협동조합수신업무방법서｣ 제1편 제3장 제1절 등에 의하면 조합 임직원은 변칙적·비정상적인업무처리를 통해 거래처의 자금력 위장 등에 직·간접적으로 관여하여서는아니되고, 예금주에게 예금잔액증명서 발급시 잔액증명대상예금에 관련 대출이있을경우 그 내용을 표시하여 발급하여야 하는데도
    (대구)해성신용협동조합 前임원 甲, ○○(직급) 丙, ◎◎(직급) 丁은 2012.1.26.∼2017.2.3. 기간 중 제3자에게 담보로 제공되어 질권설정계약이 체결되어있는A㈜ 등 4개 거래처의 정기예금에 대하여 거래처(예금주)의 요청에 따라 질권설정등 예금인출제한 내용 기재를 누락하여 총 13건(36억원)의 예금잔액증명서를부당 발급한 사실이 있음
    
    < 관련규정 >
    1. ｢신용협동조합법｣ 제39조, 제84조
    2. ｢상호금융업감독규정｣ 제4조
    """
    
    print("\n" + "=" * 60)
    print("테스트 4: 재조치 내용 패턴 (Ⅲ. 재조치 내용)")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content4)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content4)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content4)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:100]}..." if len(value) > 100 else f"  {key}: {value}")
    
    # 테스트용 예시 5: 재조치 내용 패턴 (대상자 및 재조치내용)
    test_content5 = """
    Ⅲ. 재조치 내용
    
    1. 재조치 일자: 2025.2.26.(수)
    
    2. 대상자 및 재조치내용
    
    □ 하나은행에 대한 조치사유 변경
    
    □ 전･현직 임직원 ⊗⊗⊗, 甲甲甲, 乙乙乙, 丙丙丙, ◕◕◕, ◒◒◒, ◧◧◧,
    ♣♣♣에 대한 조치를 취소하고, "자율처리 필요사항"으로 통보한 조치대상자중'신상품 도입 관련 내부통제기준 준수여부 점검을 위한 내부통제기준 미마련 관련'
    보조자에 대한 통보 취소
    
    □ 前 은행장 ◍◍◍에 대한 '퇴직자 위법･부당사항(문책경고 상당)' 조치를'퇴직자 위법･부당사항(주의적경고 상당)'으로 조치
    
    □ 前 부행장 ◯◯◯에 대한 '퇴직자 위법･부당사항(정직3월 상당)' 조치를'퇴직자 위법･부당사항(감봉 3월 상당)'으로 조치
    
    □ 前 부장 甲甲甲에 대한 '퇴직자 위법･부당사항(정직1월 상당)' 조치를'퇴직자 위법･부당사항(감봉 3월 상당)'으로 조치 변경
    
    □ 전･현직 임직원 ●●●, ◉◉◉, 甲甲甲, ◎◎◎, ◪◪◪, ◓◓◓에 대한조치사유 변경
    
    ※ 차장 甲甲甲의 경우, 법원이 기존 조치사유를 모두 인정함에 따라 변경사항 없음
    """
    
    print("\n" + "=" * 60)
    print("테스트 5: 재조치 내용 패턴 (대상자 및 재조치내용)")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content5)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content5)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content5)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:100]}..." if len(value) > 100 else f"  {key}: {value}")
    
    # 테스트용 예시 6: 재조치 내용 패턴 (재조치일자, 재조치내용)
    test_content6 = """
    Ⅲ. 재조치 내용
    
    1. 재조치일자 : 2025.10.23.(목)
    
    2. 재조치내용
    
    □ ◎◎◎에 대한 조치사유 중 일부( 펀드 환매주문 취소에 따른 전자적 침해행위금지 위반 등'과 관련한 감독책임)를 취소*하고, 자율처리 필요사항으로 통보한조치대상자 중 '펀드 환매주문 취소에 따른 전자적 침해행위 금지 위반 등'과관련한 직원에 대한 통보를 취소
    
     ※ ◎◎◎은 재심사유 외에 '설명자료 작성 부적정'에 대한 감독책임(견책)도 있으므로 직권재심을 하더라도 최종 제재조치에는 변동 없음
    """
    
    print("\n" + "=" * 60)
    print("테스트 6: 재조치 내용 패턴 (재조치일자, 재조치내용)")
    print("=" * 60)
    
    institution, sanction_date = extract_metadata_from_content(test_content6)
    print(f"금융회사명: {institution}")
    print(f"제재조치일: {sanction_date}")
    
    sanction_details = extract_sanction_details(test_content6)
    print(f"\n제재내용:\n{sanction_details}")
    
    incidents = extract_incidents(test_content6)
    print(f"\n사건 추출 결과 ({len([k for k in incidents if k.startswith('제목')])}건):")
    for key, value in sorted(incidents.items()):
        print(f"  {key}: {value[:100]}..." if len(value) > 100 else f"  {key}: {value}")

