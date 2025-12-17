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
    (줄 단위 처리 방식 사용)
    
    지원하는 형식:
    1. 가. 제목1 / 내용1, 나. 제목2 / 내용2 형태
    2. 가. 문책사항 (1) 제목1 / 내용1 (2) 제목2 / 내용2 형태
    3. 가. (1) 제목 (가) 내용 (나) 내용 형태 -> (가), (나)는 내용으로 처리
    
    Args:
        content: PDF에서 추출한 텍스트 내용
        
    Returns:
        dict: {'제목1': '...', '내용1': '...', '제목2': '...', ...}
    """
    if not content or content.startswith('['):
        return {}
    
    # 일반 텍스트 추출용이므로 collapse_split_syllables() 호출 제거
    # (OCR 텍스트는 V3 post_process_ocr.py에서 후처리됨)
    # content = collapse_split_syllables(content)  # 제거됨
    
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
    
    # 줄 단위로 처리
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
                
                # 상위 제목으로 저장하고, 사건도 시작
                # 다음에 "(1)"이 나오면 parent_title과 조합하여 새 사건 시작
                # "(1)"이 없으면 그냥 "제목1"이 사건 제목이 됨
                parent_title = title_text
                current_title = title_text  # 사건 시작 (나중에 "(1)"이 나오면 덮어씀)
                current_content = []
                in_incident = True  # 사건 시작
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
            
            # 상위 제목(parent_title)이 있고, 현재 제목이 parent_title과 같으면
            # 이전 사건을 저장하지 않고 제목만 덮어씀 (같은 "가." 항목의 하위 "(1)" 항목)
            if parent_title and current_title == parent_title:
                # 같은 "가." 항목의 하위 "(1)" 항목이므로 이전 사건 저장하지 않음
                # 하지만 새로운 하위 항목이므로 내용은 초기화
                current_title = f"{parent_title} - {sub_title}"
                current_content = []
            else:
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
            # "(1)", "(2)" 등이 줄 시작에 나오면 중단 (새 사건)
            if re.match(r'^[\(（]\d+[\)）]\s*', line) or re.match(r'^[\u2474-\u247C]', line):
                i += 1
                continue  # 위에서 처리됨
            # "□" 패턴이 나오면 중단 (새 사건) - "가." 패턴이 없을 때만
            if not has_ga_pattern:
                if re.match(r'^[□■▣▢]\s*', line):
                    i += 1
                    continue  # 위에서 처리됨
            
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
    
    # 금융회사명 추출 패턴 (숫자 포함만)
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
    
    # 제재조치일 추출 패턴 (숫자 포함만)
    # 주의: 더 구체적인 패턴(일자)을 먼저 검사해야 함
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

