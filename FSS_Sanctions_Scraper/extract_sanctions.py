import json
import re
import csv
import sys

# 연속된 한글 음절 사이에 OCR로 삽입된 공백을 제거하기 위한 패턴
split_syllable_pattern = re.compile(r'((?:[가-힣]\s){2,}[가-힣])')


def collapse_split_syllables(text: str) -> str:
    """한글 음절 사이에 삽입된 불필요한 공백을 제거"""
    if not text:
        return text
    return split_syllable_pattern.sub(lambda m: m.group(0).replace(' ', ''), text)


# UTF-8 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

def extract_incidents(content):
    """
    제재조치내용에서 사건제목과 사건내용 추출
    
    두 가지 타입을 처리:
    1. 첫 번째 타입: "4. 제 재 대 상 사 실\n가. 고객위험평가 관련 절차" -> "고객위험평가 관련 절차"가 사건제목
    2. 두 번째 타입: "4. 제 재 대 상 사 실\n가. 문 책 사 항\n(1) 직무 관련 정보의 이용 금지 위반" -> "직무 관련 정보의 이용 금지 위반"이 사건제목
    """
    if not content or content.startswith('[') or content.startswith('[오류'):
        return []
    
    incidents = []
    
    # "제재대상사실" 또는 "제 재 대 상 사 실" 섹션 찾기
    # 다양한 패턴 지원: "4. 제재대상사실", "4. 제 재 대 상 사 실", "Ⅳ. 제재대상사실" 등
    section_patterns = [
        r'4\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'4\.\s*제재대상사실',
        r'Ⅳ\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'Ⅳ\.\s*제재대상사실',
        r'IV\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'IV\.\s*제재대상사실',
    ]
    
    section_start = -1
    section_text = ""
    
    for pattern in section_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            section_start = match.end()
            # 다음 섹션까지 추출 (5. 또는 다음 주요 섹션)
            next_section_pattern = r'(?:5\.|Ⅴ\.|V\.|5\s*\.|제\s*재\s*조\s*치\s*내\s*용|결\s*론|참\s*고\s*사\s*항)'
            next_match = re.search(next_section_pattern, content[section_start:], re.IGNORECASE)
            if next_match:
                section_text = content[section_start:section_start + next_match.start()].strip()
            else:
                section_text = content[section_start:].strip()
            break
    
    if not section_text:
        return incidents
    
    lines = section_text.split('\n')
    current_title = None
    current_content = []
    in_incident = False
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # 두 번째 타입 체크: "가. 문 책 사 항" 또는 "가. 문책사항" 다음에 "(1) ..." 패턴
        # 이 패턴을 먼저 체크해야 함 (첫 번째 타입보다 우선)
        second_type_header_pattern = r'^[가-하]\.\s*(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항)(.*)$'
        second_header_match = re.match(second_type_header_pattern, line)
        
        if second_header_match:
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 문책사항 헤더는 사건제목이 아니므로 다음 줄을 확인
            current_title = None
            current_content = []
            in_incident = False
            i += 1
            
            # 다음 줄에서 "(1)" 또는 "⑴" 패턴 찾기
            if i < len(lines):
                next_line = lines[i].strip()
                # "(1) 직무 관련 정보의 이용 금지 위반" 또는 "⑴ 직무 관련 정보의 이용 금지 위반" 같은 패턴
                # "⑴"는 전각 괄호 숫자 (U+2474-U+247C)
                numbered_pattern = r'^(?:[\(（](\d+)[\)）]|[\u2474-\u247C])\s*(.+)$'
                numbered_match = re.match(numbered_pattern, next_line)
                
                if numbered_match:
                    # 그룹이 2개일 수 있음: (1) 패턴이면 group(1)이 숫자, group(2)가 제목
                    # ⑴ 패턴이면 group(1)이 None, group(2)가 제목
                    if numbered_match.lastindex >= 2:
                        current_title = numbered_match.group(2).strip()
                    elif numbered_match.lastindex >= 1 and numbered_match.group(1):
                        current_title = numbered_match.group(1).strip()
                    else:
                        # ⑴ 패턴인 경우
                        current_title = next_line.replace('⑴', '').replace('⑵', '').replace('⑶', '').replace('⑷', '').replace('⑸', '').replace('⑹', '').replace('⑺', '').replace('⑻', '').replace('⑼', '').strip()
                    current_content = []
                    in_incident = True
                    i += 1
                    continue
            
            continue
        
        # 첫 번째 타입: "가. 고객위험평가 관련 절차" 같은 패턴
        # 문책사항이 아닌 일반 항목
        first_type_pattern = r'^[가-하]\.\s*(.+)$'
        first_match = re.match(first_type_pattern, line)
        
        if first_match:
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 새 사건 시작
            title_text = first_match.group(1).strip()
            # 문책사항이 아닌 경우에만 사건제목으로 사용
            if not re.match(r'^(?:문\s*책\s*사\s*항|문책사항|책\s*임\s*사\s*항|책임사항)', title_text):
                current_title = title_text
                current_content = []
                in_incident = True
            else:
                # 문책사항인 경우 다음 줄 확인
                current_title = None
                current_content = []
                in_incident = False
            i += 1
            continue
        
        # 두 번째 타입의 번호 패턴: "(1) 직무 관련 정보의 이용 금지 위반" 또는 "⑴ 직무 관련 정보의 이용 금지 위반"
        # "⑴"는 전각 괄호 숫자 (U+2474-U+247C)
        numbered_pattern = r'^(?:[\(（](\d+)[\)）]|[\u2474-\u247C])\s*(.+)$'
        numbered_match = re.match(numbered_pattern, line)
        
        if numbered_match:
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 새 사건 시작
            # 그룹이 2개일 수 있음: (1) 패턴이면 group(1)이 숫자, group(2)가 제목
            # ⑴ 패턴이면 group(1)이 None, group(2)가 제목
            if numbered_match.lastindex >= 2:
                current_title = numbered_match.group(2).strip()
            elif numbered_match.lastindex >= 1 and numbered_match.group(1):
                current_title = numbered_match.group(1).strip()
            else:
                # ⑴ 패턴인 경우 - 전각 숫자 제거
                current_title = line.replace('⑴', '').replace('⑵', '').replace('⑶', '').replace('⑷', '').replace('⑸', '').replace('⑹', '').replace('⑺', '').replace('⑻', '').replace('⑼', '').strip()
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # 하위 목차 패턴: "(가)", "(나)", "(다)" 등은 사건제목이 아니라 사건내용의 일부
        sub_item_pattern = r'^\([가-하]\)\s*(.+)$'
        sub_item_match = re.match(sub_item_pattern, line)
        
        if sub_item_match:
            # 사건내용으로 추가
            if in_incident and current_title:
                current_content.append(line)
            i += 1
            continue
        
        # 사건 내용으로 추가
        if in_incident and current_title:
            # 다음 사건 제목이 나오기 전까지는 모두 내용
            # 다음 "가.", "나." 등이 나오거나 "(1)", "(2)", "⑴", "⑵" 등이 나오면 중단
            if re.match(r'^[가-하]\.\s*', line) or re.match(r'^[\(（]\d+[\)）]\s*', line) or re.match(r'^[\u2474-\u247C]', line):
                # 이전 사건 저장
                if current_title and current_content:
                    incidents.append({
                        '사건제목': current_title,
                        '사건내용': '\n'.join(current_content).strip()
                    })
                # 새 사건 시작은 위에서 처리됨
                continue
            
            current_content.append(line)
        
        i += 1
    
    # 마지막 사건 저장
    if current_title and current_content:
        incidents.append({
            '사건제목': current_title,
            '사건내용': '\n'.join(current_content).strip()
        })
    
    return incidents

def extract_sanction_info(content):
    """제재조치내용에서 제재대상과 제재내용 추출"""
    if not content or content.startswith('[') or content.startswith('[오류'):
        return '', ''
    
    targets = []
    sanctions = []
    
    # OCR로 추출된 텍스트는 글자 사이에 공백이 있을 수 있음 (예: "기 관")
    content = collapse_split_syllables(content)
    # 공백 제거 버전도 확인
    content_no_space = content.replace(' ', '')

    # 반복적으로 등장하는 OCR 치환 오류 보정
    ocr_replacements = {
        '오 혐 설 계 사': '보험설계사',
        '오혐설계사': '보험설계사',
        '로 혐 설 계 사': '보험설계사',
        '로혐설계사': '보험설계사',
        '견 무 정 지': '업무정지',
        '견무정지': '업무정지'
    }
    for wrong, correct in ocr_replacements.items():
        content = content.replace(wrong, correct)
        content_no_space = content_no_space.replace(wrong.replace(' ', ''), correct.replace(' ', ''))
 
    target_alias_map = {
        '기관': '기관',
        '임원': '임원',
        '직원': '직원',
        '임직원': '임직원',
        '임원직원': '임원|직원',
        '임원/직원': '임원|직원',
        '임원·직원': '임원|직원',
        '임원ㆍ직원': '임원|직원',
        '임·직원': '임원|직원',
        '임ㆍ직원': '임원|직원',
        '임원및직원': '임원|직원',
        '임원과직원': '임원|직원',
        '보험설계사': '보험설계사',
        '보험설계사등': '보험설계사 등',
        '보험대리점': '보험대리점',
        '보험중개사': '보험중개사',
        '재심': '재심'
    }

    # "등" 접미사가 붙은 대상을 표준화
    target_alias_map.update({
        '기관등': '기관 등',
        '임원등': '임원 등',
        '직원등': '직원 등'
    })

    def clean_fragment(fragment: str) -> str:
        fragment = fragment.strip()
        fragment = re.sub(r'^[|\-·•◦\.]+\s*', '', fragment)
        fragment = fragment.strip(' ,;')
        fragment = re.sub(r'\s*,\s*', ', ', fragment)
        fragment = re.sub(r'\s+', ' ', fragment)
        return fragment


def truncate_after_subsections(text: str) -> str:
    if not text:
        return text
    markers = ['제재대상사실', '조치대상사실']
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].rstrip(' ,|')
    return text

    def split_sanction(fragment: str):
        fragment = clean_fragment(fragment)
        if not fragment:
            return []
        return [fragment]

    alias_detection = []
    for alias_raw, normalized in target_alias_map.items():
        alias_compact = alias_raw
        alias_compact = alias_compact.replace(' ', '')
        alias_compact = alias_compact.replace('/', '')
        alias_compact = alias_compact.replace('|', '')
        alias_compact = alias_compact.replace('·', '')
        alias_compact = alias_compact.replace('ㆍ', '')
        alias_detection.append((alias_raw, alias_compact, normalized))

    def strip_alias_remainder(line: str, alias_compact: str) -> str:
        consumed = 0
        idx = 0
        while idx < len(line) and consumed < len(alias_compact):
            ch = line[idx]
            if ch in {' ', '/', '|', '·', 'ㆍ'}:
                idx += 1
                continue
            consumed += 1
            idx += 1
        return line[idx:].strip()

    def detect_table_target(line: str):
        if '제재대상' in line and '제재' in line and '내용' in line:
            return None, None, None
        line_compact = line.replace(' ', '').replace('/', '').replace('|', '').replace('·', '').replace('ㆍ', '')
        for alias_raw, alias_compact, normalized in alias_detection:
            if line_compact.startswith(alias_compact):
                remainder = strip_alias_remainder(line, alias_compact)
                inline_sanction = None
                if line.startswith(alias_raw) and len(line) > len(alias_raw):
                    next_char = line[len(alias_raw)]
                    if next_char not in {' ', ',', '·', 'ㆍ', '|', '/', ')', ':'}:
                        remainder_stripped = remainder.strip()
                        inline_sanction = f"{normalized}{remainder_stripped}" if remainder_stripped else normalized
                        remainder = ''
                # 대상 뒤에 단독 "등"이 붙어있는 경우만 대상에 포함 ("등록" 등은 제외)
                if remainder:
                    remainder_stripped = remainder.lstrip()
                    if remainder_stripped.startswith('등'):
                        next_char = remainder_stripped[1] if len(remainder_stripped) > 1 else ''
                        if not next_char or next_char in {',', ' ', '·', 'ㆍ', '|', '/', ')', ':'}:
                            normalized = f"{normalized} 등"
                            remainder = remainder_stripped[1:].lstrip(' ,·ㆍ|/:)')
                return normalized, remainder, inline_sanction
        return None, None, None

    def parse_table_entries(table_content: str):
        lines = table_content.split('\n')
        in_table = False
        table_lines = []

        target_header_keywords = ('제재대상', '제제대상', '조치대상', '조치대상자', '대상', '대상자')
        content_header_keywords = ('제재내용', '제제내용', '조치내용', '조치내역', '내용')

        for line in lines:
            stripped = line.strip()
            if not in_table:
                header_no_space = stripped.replace(' ', '')
                has_target_header = any(keyword in header_no_space for keyword in target_header_keywords)
                has_content_header = any(keyword in header_no_space for keyword in content_header_keywords)
                if has_target_header and has_content_header:
                    in_table = True
                continue
            normalized_line_no_space = stripped.replace(' ', '')
            if (
                stripped.startswith('4.')
                or stripped.startswith('Ⅳ')
                or stripped.startswith('IV')
                or normalized_line_no_space.startswith('제재대상사실')
                or normalized_line_no_space.startswith('조치대상사실')
            ):
                break
            if not stripped:
                continue
            table_lines.append(stripped)

        if not table_lines:
            return []

        current_target = None
        current_sanctions = []
        table_entries = []
        pending_sanctions = []

        for line in table_lines:
            detected_target, remainder, inline_sanction = detect_table_target(line)
            if inline_sanction:
                pending_sanctions.extend(split_sanction(inline_sanction))
            if detected_target:
                if current_target and detected_target == current_target and not remainder:
                    # Same 대상이 반복 표기된 경우 (행 분리용), 무시
                    continue
                if current_target:
                    def should_defer_to_next(target_name: str, sanction_text: str) -> bool:
                        cleaned = clean_fragment(sanction_text)
                        if not cleaned.startswith('퇴직자'):
                            return False
                        if '임원' in target_name and ('견책상당' in cleaned or '견책 상당' in cleaned):
                            return False
                        return True

                    if '기관' in current_target or '임원' in current_target:
                        moved = []
                        while current_sanctions and should_defer_to_next(current_target, current_sanctions[-1]):
                            moved.append(current_sanctions.pop())
                        if moved:
                            pending_sanctions[0:0] = reversed([clean_fragment(m) for m in moved if clean_fragment(m)])
                    cleaned = [clean_fragment(s) for s in current_sanctions if clean_fragment(s)]
                    table_entries.append((current_target, cleaned))
                current_target = detected_target
                current_sanctions = []
                if pending_sanctions:
                    current_sanctions.extend(pending_sanctions)
                    pending_sanctions = []
                if remainder:
                    current_sanctions.extend(split_sanction(remainder))
            else:
                if not current_target:
                    pending_sanctions.extend(split_sanction(line))
                    continue
                if current_target.startswith('기관') and line.startswith('퇴직자'):
                    pending_sanctions.extend(split_sanction(line))
                    continue

                paren_match = re.match(r'^\((\d+)명\)\s*(.*)$', line)
                if paren_match:
                    count = paren_match.group(1)
                    rest = paren_match.group(2).strip()
                    if f"({count}명" not in current_target:
                        current_target = f"{current_target} ({count}명)"
                    if rest:
                        current_sanctions.extend(split_sanction(rest))
                    continue

                # 줄의 선두에 제재내용이 먼저 추출된 경우 (ex. "기관주의")
                current_sanctions.extend(split_sanction(line))

        if current_target:
            cleaned = [clean_fragment(s) for s in current_sanctions if clean_fragment(s)]
            table_entries.append((current_target, cleaned))

        return table_entries

    inline_pattern = re.compile(r'(?:제재대상|대상)\s*(?:제재내용|내용)\s*(기관|임원|직원|임직원)\s*([^\r\n]+)', re.DOTALL)
    simple_inline_match = inline_pattern.search(content)
    if simple_inline_match:
        target_simple = simple_inline_match.group(1)
        sanction_simple = clean_fragment(simple_inline_match.group(2))
        sanction_simple = truncate_after_subsections(sanction_simple)
        if sanction_simple:
            return target_simple, sanction_simple

    lines = content.split('\n')
    for idx, line in enumerate(lines):
        header_no_space = line.replace(' ', '')
        has_target_header = ('제재대상' in header_no_space) or ('대상' in header_no_space)
        has_content_header = ('제재내용' in header_no_space) or ('내용' in header_no_space)
        if has_target_header and has_content_header:
            simple_targets = []
            simple_sanctions = []
            for next_line in lines[idx + 1:]:
                stripped = next_line.strip()
                if not stripped:
                    continue
                normalized_no_space = stripped.replace(' ', '')
                if normalized_no_space.startswith('제재대상사실') or normalized_no_space.startswith('조치대상사실') or re.match(r'^[4-9]\.', normalized_no_space):
                    break
                match = re.match(r'^(기관|임원|직원|임직원)\s+(.+)$', stripped)
                if match:
                    simple_targets.append(match.group(1))
                    simple_sanctions.append(clean_fragment(match.group(2)))
                    continue
                for prefix in ('기관', '임원', '직원', '임직원'):
                    if normalized_no_space.startswith(prefix):
                        remainder = stripped[len(prefix):].strip()
                        if remainder:
                            simple_targets.append(prefix)
                            simple_sanctions.append(clean_fragment(remainder))
                        break
                if simple_targets and len(simple_targets) == len(simple_sanctions):
                    break
            if simple_targets and simple_sanctions:
                target_result = '|'.join(simple_targets)
                sanction_result = ' | '.join(simple_sanctions)
                sanction_result = truncate_after_subsections(sanction_result)
                return target_result, sanction_result
            break

    table_entries = parse_table_entries(content)
    if table_entries:
        for idx, (target_name, sanction_items) in enumerate(table_entries[:-1]):
            if '임원' in target_name and not any('퇴직자' in s for s in sanction_items):
                next_target, next_items = table_entries[idx + 1]
                move_items = [s for s in next_items if '퇴직자' in s and '견책' in s]
                if move_items:
                    sanction_items[:0] = move_items
                    table_entries[idx + 1] = (next_target, [s for s in next_items if s not in move_items])

        unique_targets = []
        sanction_rows = []
        for target, sanction_list in table_entries:
            for component in target.split('|'):
                component = component.strip()
                if not component:
                    continue
                component_key = component.replace(' ', '').replace('|', '').replace('/', '').replace('·', '').replace('ㆍ', '')
                normalized_component = target_alias_map.get(component_key, component)
                if normalized_component.endswith('등') and not normalized_component.endswith(' 등'):
                    normalized_component = normalized_component[:-1] + ' 등'
                if normalized_component not in unique_targets:
                    unique_targets.append(normalized_component)
            row_text = ', '.join([clean_fragment(s) for s in sanction_list if clean_fragment(s)])
            if row_text:
                sanction_rows.append(row_text)

        target_result = '|'.join(unique_targets) if unique_targets else '-'
        sanction_result = ' | '.join(sanction_rows) if sanction_rows else '-'
        sanction_result = truncate_after_subsections(sanction_result)
        return target_result, sanction_result
    
    # 패턴 0-1: "3. 조치내용" 변형 (조치내용, 조치, 제재조치 내용, 제 재 조 치 내 용 등)
    # 예: "3. 조치내용\n대상 내용\n직원 ◦ 자율처리..." 또는 "3. 제 재 조 치 내 용\n대상 내 용..."
    alt_pattern = r'3\.\s*(?:제\s*재\s*)?조\s*치\s*(?:\s*내\s*용)?.*?(?:대\s*상|제재대상|조치대상)\s*(?:내\s*용|제재내용|조치내용)\s*\n(.+?)(?=4\.|$)'
    alt_match = re.search(alt_pattern, content, re.DOTALL)
    
    if alt_match:
        section = alt_match.group(1).strip()
        lines = section.split('\n')
        
        # 제재대상이 독립된 줄로 있는 경우 처리
        current_target = None
        current_sanctions = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 제재대상이 독립된 줄인지 확인
            if re.match(r'^(기\s*관|임\s*원|직\s*원|기관|임원|직원|임·직원)$', line):
                # 이전 제재대상 저장
                if current_target and current_sanctions:
                    targets.append(current_target.replace(' ', ''))
                    sanctions.append('\n'.join(current_sanctions))
                
                # 새로운 제재대상
                current_target = line
                current_sanctions = []
                continue
            
            # 제재대상과 제재내용이 같은 줄에 있는 경우
            # "직원 ◦ 자율처리..." 패턴 또는 "기 관 영 업 일 부..." 패턴
            if re.match(r'^(기관|임원|직원|직\s+원|기\s+관|임\s+원)\s+', line):
                match_target = re.match(r'^(기관|임원|직원|직\s+원|기\s+관|임\s+원)\s+(.+)$', line)
                if match_target:
                    # 이전 것 저장
                    if current_target and current_sanctions:
                        targets.append(current_target.replace(' ', ''))
                        sanctions.append('\n'.join(current_sanctions))
                        current_target = None
                        current_sanctions = []
                    
                    target = match_target.group(1).replace(' ', '')
                    sanction = match_target.group(2).strip()
                    sanction = re.sub(r'^[◦•·▪\s]+', '', sanction)
                    targets.append(target)
                    sanctions.append(sanction)
                continue
            
            # 제재내용으로 보이는 줄
            if line.startswith(('▪', '◦', '·', '-', '•')) or any(kw in line for kw in ['과태료', '견책', '주의', '경고', '감봉', '정지', '취소', '자율처리', '퇴직자', '위법', '기관주의', '기관경고']):
                if current_target:
                    current_sanctions.append(line)
        
        # 마지막 제재대상 저장
        if current_target and current_sanctions:
            targets.append(current_target.replace(' ', ''))
            sanctions.append('\n'.join(current_sanctions))
    
    # 패턴 0-2: "제재대상 제 재 내 용" (공백으로 한 글자씩 나뉜 경우)
    # 예: "제재대상 제 재 내 용\n임원 주의 1명" 또는 "직 원 주의 1명"
    if not targets:
        spaced_pattern = r'3\.\s*제재조치내용\s*\n\s*제재대상\s*제\s+재\s+내\s+용\s*\n(.+?)(?=4\.|$)'
        spaced_match = re.search(spaced_pattern, content, re.DOTALL)
        
        if spaced_match:
            section = spaced_match.group(1).strip()
            lines = section.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # "임원 주의 1명" 또는 "직 원 주의 1명" 패턴
                if re.match(r'^(기관|임원|직원|기\s+관|임\s+원|직\s+원)\s+', line):
                    match_target = re.match(r'^(기관|임원|직원|기\s+관|임\s+원|직\s+원)\s+(.+)$', line)
                    if match_target:
                        target = match_target.group(1).replace(' ', '')
                        targets.append(target)
                        sanctions.append(match_target.group(2).strip())

    # 패턴 0-3: OCR 텍스트 형식 (공백 포함) - "3. 제 재 조 치 내 용"
    # 예: "제 재 대상 제 재 내 용\n기 관 기 관 주 의\n직 원 등 주 의 2 명"
    if not targets:
        ocr_pattern = r'3\.\s*제\s*재\s*조\s*치\s*내\s*용.*?제\s*재\s*대\s*상\s*제\s*재\s*내\s*용\s*\n(.+?)(?=4\.|$)'
        ocr_match = re.search(ocr_pattern, content, re.DOTALL)
    else:
        ocr_match = None
    
    if ocr_match:
        section = ocr_match.group(1).strip()
        lines = section.split('\n')
        
        # OCR 텍스트의 경우 제재대상이 독립된 줄일 수 있음
        # 예: "보 험 설 계 사\n- 등 록 취 소 1 명" 또는 "임 원\n퇴 직 자..."
        current_target = None
        current_sanctions = []
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # 제재대상이 독립된 줄인지 확인 (| 등 특수문자 제거 후, 공백도 유연하게)
            # "기 관", "임 원", "직 원", "보 험 설 계 사", "로 혐 설 계 사" (OCR 오인식), "임·직원" 등
            clean_line = line.replace('|', '').strip()
            # 공백 유연하게 처리 (\s*는 0개 이상)
            if re.match(r'^(기\s*관|임\s*원|직\s*원|보\s+험\s+설\s+계\s+사|로\s+혐\s+설\s+계\s+사|임·직원)$', clean_line):
                # 이전 제재대상이 있으면 저장
                if current_target and current_sanctions:
                    # "로 혐 설 계 사"를 "보험설계사"로 정규화
                    normalized_target = current_target.replace('로 혐', '보 험').replace('|', '').strip() if '로 혐' in current_target else current_target
                    targets.append(normalized_target)
                    sanctions.append('\n'.join(current_sanctions))
                
                # 새로운 제재대상 (특수문자 제거)
                current_target = clean_line
                current_sanctions = []
                continue
            
            # 제재대상이 줄 중간에 있는 경우 (예: "직 원" 앞에 제재내용이 있는 경우)
            # "퇴직자... 1명,\n직 원\n퇴직자..." 패턴
            if re.match(r'^(직\s*원|기\s*관|임\s*원)$', line):
                # 이전 제재대상 저장
                if current_target and current_sanctions:
                    normalized_target = current_target.replace('로 혐', '보 험') if '로 혐' in current_target else current_target
                    targets.append(normalized_target)
                    sanctions.append('\n'.join(current_sanctions))
                
                # 새로운 제재대상
                current_target = line
                current_sanctions = []
                continue
            
            # 제재내용으로 보이는 줄 (제재대상이 설정된 경우에만)
            if current_target and (line.startswith(('-', '·', '◦', '▪')) or any(kw in line for kw in ['과태료', '과 태 료', '견책', '주의', '경고', '감봉', '정지', '취소', '퇴직자', '위법'])):
                current_sanctions.append(line)
                continue
            
            # 제재대상과 제재내용이 같은 줄에 있고 파이프(|)로 구분된 경우
            # 예: "로 혐 설 계 사 | - 결 무 정 지 180 일..."
            if '|' in line:
                parts_pipe = line.split('|', 1)
                if len(parts_pipe) == 2:
                    target_part = parts_pipe[0].strip()
                    sanction_part = parts_pipe[1].strip()
                    
                    # 제재대상 정규화
                    if '로 혐 설 계 사' in target_part or '로혐설계사' in target_part:
                        # 이전 저장
                        if current_target and current_sanctions:
                            normalized_target = current_target.replace('로 혐', '보 험').replace('|', '').strip() if '로 혐' in current_target else current_target.replace('|', '').strip()
                            targets.append(normalized_target)
                            sanctions.append('\n'.join(current_sanctions))
                        
                        targets.append('보험설계사')
                        sanctions.append(sanction_part)
                        current_target = None
                        current_sanctions = []
                        continue
            
            # "기 관", "임 원", "직 원", "보 험 설 계 사" 등 공백으로 구분된 패턴 (제재내용이 같은 줄에)
            # 예: "기 관 기 관 주 의" or "직 원 등 주 의 2 명" or "보 험 설 계 사 등 록 취 소 1 명"
            parts = line.replace('|', '').split()  # 파이프 제거 후 split
            if len(parts) >= 3:
                # 처음 2개가 제재대상, 나머지가 제재내용
                target_parts = []
                content_parts = []
                
                # "기 관", "임 원", "직 원" 패턴 찾기
                i = 0
                while i < len(parts):
                    if parts[i] in ['기', '임', '직'] and i+1 < len(parts) and parts[i+1] in ['관', '원']:
                        target_parts.append(parts[i] + ' ' + parts[i+1])
                        i += 2
                        # 나머지는 제재내용
                        content_parts = parts[i:]
                        break
                    # "보 험 설 계 사" 패턴
                    elif parts[i] == '보' and i+4 < len(parts) and parts[i:i+5] == ['보', '험', '설', '계', '사']:
                        target_parts.append('보험설계사')
                        i += 5
                        # 나머지는 제재내용
                        content_parts = parts[i:]
                        break
                    # "로 혐 설 계 사" 패턴 (OCR 오인식)
                    elif parts[i] == '로' and i+4 < len(parts) and parts[i:i+5] == ['로', '혐', '설', '계', '사']:
                        target_parts.append('보험설계사')  # 정규화
                        i += 5
                        content_parts = parts[i:]
                        break
                    # "보 험 대 리 점" 패턴
                    elif parts[i] == '보' and i+4 < len(parts) and parts[i:i+5] == ['보', '험', '대', '리', '점']:
                        target_parts.append('보험대리점')
                        i += 5
                        content_parts = parts[i:]
                        break
                    i += 1
                
                if target_parts and content_parts:
                    # 이전 저장
                    if current_target and current_sanctions:
                        normalized_target = current_target.replace('로 혐', '보 험').replace('|', '').strip() if '로 혐' in current_target else current_target.replace('|', '').strip()
                        targets.append(normalized_target)
                        sanctions.append('\n'.join(current_sanctions))
                        current_target = None
                        current_sanctions = []
                    
                    targets.append(target_parts[0])
                    sanctions.append(' '.join(content_parts))
        
        # 마지막 제재대상 저장
        if current_target and current_sanctions:
            normalized_target = current_target.replace('로 혐', '보 험').replace('|', '').strip() if '로 혐' in current_target else current_target.replace('|', '').strip()
            targets.append(normalized_target)
            sanctions.append('\n'.join(current_sanctions))
    

    # 패턴 0-4: "_ ｜ -" 또는 "_ | -" 패턴 (표 경계선 오인식) 처리
    # 이 패턴이 있으면 같은 줄이나 다음 줄에서 실제 제재내용 찾기
    if not targets:
        # 전체 줄을 캡처해서 같은 줄에 등록취소가 있는지 확인
        underscore_line_pattern = r'보\s*험\s*설\s*계\s*사\s+[_｜\|]\s*-\s*([^\n]*)'
        underscore_match = re.search(underscore_line_pattern, content)
        
        if underscore_match:
            # 먼저 같은 줄에 제재내용이 있는지 확인
            same_line = underscore_match.group(1)
            
            # 등록취소가 같은 줄에 있는 경우 (102번)
            if re.search(r'등\s*록\s*취\s*소', same_line):
                numbers = re.findall(r'\d+', same_line)
                if numbers:
                    targets.append('보험설계사')
                    sanctions.append(f'등록취소 {numbers[0]}명')
                else:
                    targets.append('보험설계사')
                    sanctions.append('등록취소')
            
            # 같은 줄에 없으면 다음 영역에서 찾기
            else:
                after_underscore = content[underscore_match.end():]
                search_area = after_underscore[:200]
                
                # 등록취소 패턴
                if re.search(r'등\s*록\s*취\s*소', search_area):
                    numbers = re.findall(r'\d+', search_area[:100])
                    if numbers:
                        targets.append('보험설계사')
                        sanctions.append(f'등록취소 {numbers[0]}명')
                
                # 업무정지 패턴
                elif re.search(r'업\s*무\s*정\s*지', search_area):
                    numbers = re.findall(r'\d+', search_area[:100])
                    if numbers:
                        if len(numbers) >= 2:
                            targets.append('보험설계사')
                            sanctions.append(f'업무정지 {numbers[0]}일 ({numbers[1]}명)')
                        else:
                            targets.append('보험설계사')
                            sanctions.append(f'업무정지 {numbers[0]}일')
                
                # 과태료 패턴
                elif re.search(r'과\s*태\s*료', search_area):
                    numbers = re.findall(r'\d+', search_area[:100])
                    if numbers:
                        targets.append('보험설계사')
                        sanctions.append(f'과태료 {numbers[0]}만원')

    
    # 패턴 0-5: "보험설계사 -" + "이0 1 기" 패턴 (106, 111번 같은 케이스)
    # OCR이 완전히 깨져서 표 내용이 "이0 1 기 74 | 표" 같이 나오는 경우
    # 이런 경우는 보험사기대응단이며, 금융위원회에 제재를 건의하는 케이스
    if not targets:
        broken_table_pattern = r'보\s*험\s*설\s*계\s*사\s*-\s*\n\s*이0'
        broken_match = re.search(broken_table_pattern, content)
        
        # 보험설계사 패턴도 정규식으로 검사
        insurance_pattern = re.search(r'보\s*험\s*설\s*계\s*사\s*-', content)
        
        if broken_match or ('이0' in content and insurance_pattern):
            # 보험사기대응단인지 확인 (제재대상사실에서 "보험사기" 키워드)
            if re.search(r'보\s*험\s*사\s*기', content) or '보험사기' in content:
                # 제재대상사실 영역 찾기 (정규식으로 정확하게)
                fact_match = re.search(r'4\.\s*제\s*재\s*대\s*상\s*사\s*실', content)
                if fact_match:
                    fact_section = content[fact_match.end():][:1000]
                else:
                    fact_section = content
                
                # 등록취소 패턴 확인
                if re.search(r'등\s*록\s*취\s*소', fact_section):
                    targets.append('보험설계사')
                    sanctions.append('등록취소 1명')
                
                # 업무정지 패턴 확인
                elif re.search(r'업\s*무\s*정\s*지', fact_section):
                    numbers = re.findall(r'\d+', fact_section[:200])
                    if numbers and len(numbers) >= 1:
                        targets.append('보험설계사')
                        sanctions.append(f'업무정지 {numbers[0]}일')
                    else:
                        targets.append('보험설계사')
                        sanctions.append('업무정지')
                
                # 제재내용이 없는 경우 (보험사기 적발만)
                else:
                    targets.append('보험설계사')
                    sanctions.append('보험사기 연루 행위 - 금융위원회 제재 건의')

        # 패턴 1: "3. 제재조치내용" 섹션에서 "제재대상 제재내용" 표 찾기 (조치대상 조치내용도 포함)
    # 예: "3. 제재조치내용\n제재대상 제재내용\n기 관 과태료 18백만원\n임 원 주의 1명\n직 원 견책 1명"
    # 또는 "조치대상 조치내용\n기 관 기관경고..."
    if not targets:
        pattern1 = r'3\.\s*제재조치내용\s*\n\s*(?:제재대상|조치대상)\s*(?:제재내용|조치내용)\s*\n([^\n]+)'
        match1 = re.search(pattern1, content, re.MULTILINE)
    else:
        match1 = None
    
    if match1:
        # 첫 번째 줄만 추출
        first_line = match1.group(1).strip()
        
        # "기 관", "임 원", "직 원" 패턴 (공백 포함)
        match_blank = re.match(r'^(기|임|직)\s+(원|관)\s+(.+)$', first_line)
        if match_blank:
            target = match_blank.group(1) + ' ' + match_blank.group(2)
            sanction = match_blank.group(3).strip()
            sanction = re.sub(r'^[◦•·\s]+', '', sanction)
            targets.append(target)
            sanctions.append(sanction)
        
        # "기관", "임원", "직원" 패턴 (공백 없음)
        elif re.match(r'^(기관|임원|직원)\s+', first_line):
            match_no_blank = re.match(r'^(기관|임원|직원)\s+(.+)$', first_line)
            if match_no_blank:
                target = match_no_blank.group(1)
                sanction = match_no_blank.group(2).strip()
                targets.append(target)
                sanctions.append(sanction)
        
        # "보험설계사", "대리점" 등 특정 제재대상 패턴
        elif re.match(r'^(보험설계사|보험대리점|보험중개사|투자권유대행인|펀드판매사|자산운용사|신탁업자|여신전문금융회사|저축은행|상호금융|신용협동조합)\s+', first_line):
            match_other = re.match(r'^([가-힣]+)\s+(.+)$', first_line)
            if match_other:
                target = match_other.group(1)
                sanction = match_other.group(2).strip()
                sanction = re.sub(r'^[◦•·\s]+', '', sanction)
                targets.append(target)
                sanctions.append(sanction)
        
        # "甲(개인사업자)" 패턴 - 한자로 시작하는 경우
        elif re.match(r'^[甲乙丙丁]\(', first_line):
            # 예: "甲(개인사업자) 과태료 180만원"
            match_hanja = re.match(r'^([甲乙丙丁])\(([^)]+)\)\s+(.+)$', first_line)
            if match_hanja:
                hanja = match_hanja.group(1)
                desc = match_hanja.group(2)  # 개인사업자, 명칭 등
                sanction = match_hanja.group(3).strip()
                # 제재대상은 "개인사업자" 등으로 표시
                targets.append(desc)
                sanctions.append(sanction)
        
        # 일반적인 패턴: 한글로 시작하고 공백 뒤에 내용이 있는 경우
        elif re.match(r'^[가-힣]+\s+', first_line):
            parts = first_line.split(None, 1)
            if len(parts) >= 2:
                target = parts[0]
                sanction = parts[1]
                sanction = re.sub(r'^[◦•·\s]+', '', sanction)
                targets.append(target)
                sanctions.append(sanction)
        
        # 여러 줄이 있는 경우 (표 형식)를 처리하기 위해 다음 줄들도 확인
        # "제재대상 제재내용" 또는 "조치대상 조치내용" 다음부터 "4."로 시작하는 줄 전까지
        pattern1_multi = r'3\.\s*제재조치내용\s*\n\s*(?:제재대상|조치대상)\s*(?:제재내용|조치내용)\s*\n((?:(?:기|임|직)\s*(?:원|관)\s+[^\n]+\n?)+)'
        match1_multi = re.search(pattern1_multi, content, re.MULTILINE)
        if match1_multi:
            section = match1_multi.group(1)
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            # 이미 첫 줄을 추출했다면 스킵, 아니면 다시 추출
            if not targets:
                for line in lines:
                    if len(line) < 3:
                        continue
                    if re.match(r'^[기임직]\s+[원관]', line):
                        parts = line.split(None, 2)
                        if len(parts) >= 3:
                            target = parts[0] + ' ' + parts[1]
                            sanction = parts[2]
                            sanction = re.sub(r'^[◦•·\s]+', '', sanction)
                            targets.append(target)
                            sanctions.append(sanction)
            else:
                # 이미 첫 줄 추출했지만 추가 줄이 있는지 확인
                for line in lines[1:]:  # 첫 줄은 이미 처리했으므로 스킵
                    if len(line) < 3:
                        continue
                    if re.match(r'^[기임직]\s+[원관]', line):
                        parts = line.split(None, 2)
                        if len(parts) >= 3:
                            target = parts[0] + ' ' + parts[1]
                            sanction = parts[2]
                            sanction = re.sub(r'^[◦•·\s]+', '', sanction)
                            targets.append(target)
                            sanctions.append(sanction)
    
    # 패턴 1.5: 여러 줄로 구성된 패턴 (제재대상이 중간에 있는 경우)
    # 예: "· 퇴직자 위법...\n(6백만원) 1명\n임직원\n· 퇴직자..."
    if not targets:
        # "3. 제재조치내용" 섹션 전체 추출
        pattern1_5 = r'3\.\s*제재조치내용.*?제재대상\s*제재내용\s*\n(.+?)(?=4\.|$)'
        match1_5 = re.search(pattern1_5, content, re.DOTALL)
        
        if match1_5:
            section = match1_5.group(1).strip()
            lines = section.split('\n')
            
            # 제재대상과 제재내용을 찾기 위한 임시 변수
            current_target = None
            current_sanctions = []
            pending_sanctions = []  # 제재대상이 나오기 전의 제재내용
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 제재대상 키워드 확인 (독립된 줄에 있는 경우)
                # "기관", "임원", "직원", "직 원", "기 관", "임 원", "임직원", "보험대리점", "보험설계사" 등
                if re.match(r'^(기관|임원|직원|기\s+관|임\s+원|직\s+원|임직원|직\s+원\s+등|보험대리점|보험설계사|보험중개사)$', line):
                    # 이전 제재대상이 있으면 저장
                    if current_target and current_sanctions:
                        targets.append(current_target)
                        sanctions.append('\n'.join(current_sanctions))
                    
                    # 새로운 제재대상 시작
                    current_target = line
                    # pending_sanctions이 있으면 현재 제재대상의 것으로 간주
                    current_sanctions = pending_sanctions.copy()
                    pending_sanctions = []
                
                # 제재내용으로 보이는 줄 (◦, ·로 시작하거나 "과태료", "견책" 등 키워드 포함)
                elif line.startswith(('◦', '·', '-')) or any(keyword in line for keyword in ['과태료', '견책', '주의', '경고', '감봉', '조치', '퇴직자', '위법', '백만원']):
                    if current_target:
                        current_sanctions.append(line)
                    else:
                        # 아직 제재대상이 안 나왔으면 pending에 저장
                        pending_sanctions.append(line)
            
            # 마지막 제재대상 저장
            if current_target and current_sanctions:
                targets.append(current_target)
                sanctions.append('\n'.join(current_sanctions))
    
    # 패턴 2: "제재조치내용" 섹션에서 직접 찾기 (다른 형식)
    if not targets:
        # "제재대상 제재내용" 헤더 다음 줄들 찾기
        pattern2 = r'제재대상\s*제재내용\s*\n((?:[기임직]\s*[원관]\s+[^\n]+\n?)+)'
        match2 = re.search(pattern2, content, re.MULTILINE)
        if match2:
            section = match2.group(1)
            lines = section.split('\n')
            for line in lines:
                line = line.strip()
                if re.match(r'^[기임직]\s*[원관]', line):
                    parts = re.split(r'\s+', line, 2)
                    if len(parts) >= 3:
                        target = parts[0] + ' ' + parts[1]
                        sanction = parts[2]
                        targets.append(target)
                        sanctions.append(sanction)
    
    # 패턴 3: "조치내용" 섹션에서 추출 (재심 등 특수 케이스)
    if not targets:
        # "2. 조치내용" 섹션에서 제재대상과 제재내용 추출
        # 예: "2. 조치내용\n□ 고객자산본부장 ◎◎◎은 ... 견책으로 조치"
        pattern3 = r'2\.\s*조치내용[^\n]*\n\s*□\s*([^\n]+(?:견책|주의|과태료|경고|자율처리)[^\n]*)'
        matches = re.finditer(pattern3, content, re.MULTILINE | re.DOTALL)
        for match in matches:
            text = match.group(1).strip()
            # 제재대상 추출
            if '◎◎◎' in text or '甲' in text or '乙' in text:
                # 직책명 찾기
                if '본부장' in text or '임원' in text:
                    target = '임원'
                elif '직원' in text:
                    target = '직원'
                else:
                    target = '임원/직원'
                
                # 제재내용 추출 - 전체 문장 추출
                sanction_keywords = ['견책', '주의', '과태료', '경고', '자율처리']
                for keyword in sanction_keywords:
                    if keyword in text:
                        # 키워드가 포함된 전체 문장 추출
                        # 문장의 시작부터 끝까지
                        sentences = re.split(r'[\.\n]', text)
                        for sentence in sentences:
                            if keyword in sentence:
                                sanction = sentence.strip()
                                # 앞뒤 문맥 추가
                                idx = text.find(sentence)
                                if idx > 0:
                                    context_start = max(0, idx - 30)
                                    context = text[context_start:idx + len(sentence)].strip()
                                    if len(context) > len(sanction):
                                        sanction = context
                                targets.append(target)
                                sanctions.append(sanction)
                                break
                        if targets:  # 이미 추가했으면 중단
                            break
    
    # 패턴 4: "재조치내용" 섹션에서 추출
    if not targets:
        pattern4 = r'재조치내용[^\n]*\n\s*□\s*([^\n]+)'
        matches = re.finditer(pattern4, content, re.MULTILINE)
        for match in matches:
            text = match.group(1).strip()
            if any(keyword in text for keyword in ['취소', '견책', '주의']):
                if '◎◎◎' in text:
                    target = '임원/직원'
                    targets.append(target)
                    sanctions.append(text)

    # 패턴 5: 줄 전체에 제재대상과 제재내용이 섞여 있는 OCR 문자열 처리
    if not targets:
        section_text = content
        idx_4 = content.find('4.')
        if idx_4 != -1:
            section_text = content[:idx_4]
 
        target_patterns = [
            ('보험설계사', r'보\s*험\s*설\s*계\s*사'),
            ('보험설계사', r'오\s*혐\s*설\s*계\s*사'),
            ('보험대리점', r'보\s*험\s*대\s*리\s*점'),
            ('보험중개사', r'보\s*험\s*중\s*개\s*사'),
            ('기관', r'기\s*관'),
            ('임원', r'임\s*원'),
            ('직원', r'직\s*원'),
            ('임직원', r'임\s*직\s*원')
        ]
        sanction_keywords = ['과태료', '주의', '경고', '견책', '정지', '취소', '생략', '조치', '감봉']
 
        lines = section_text.split('\n')
        for raw_line in lines:
            line = raw_line.strip()
            if not line or len(line) < 2:
                continue
            if re.search(r'제\s*재\s*대\s*상', line) or re.search(r'제재대상', line):
                continue
 
            normalized_line = line.replace('|', ' ').replace('‧', ' ').strip()
            normalized_line = re.sub(r'^[\-\.·:•◦\s]+', '', normalized_line)
            if not normalized_line:
                continue
            if '금융' in normalized_line and '명' in normalized_line:
                continue
            if '금 융' in normalized_line and '명' in normalized_line:
                continue

            matched_target = None
            for target_name, pattern in target_patterns:
                match = re.search(pattern, normalized_line)
                if match:
                    matched_target = target_name
                    remainder = normalized_line[match.end():].strip()
                    remainder = re.sub(r'^[\s\-–~·:·\.,]+', '', remainder)
                    remainder = re.sub(r'\s+', ' ', remainder)
                    if not remainder:
                        matched_target = None
                        break
                    remainder_compact = remainder.replace(' ', '')
                    if not any(keyword.replace(' ', '') in remainder_compact for keyword in sanction_keywords) and not re.search(r'\d', remainder_compact):
                        matched_target = None
                        break
                    if matched_target == '보험설계사':
                        matched_target = '보험설계사'
                    if matched_target:
                        targets.append(matched_target)
                        sanctions.append(remainder)
                    break
            else:
                stripped = normalized_line.lstrip('-·◦• ')
                if targets and stripped and raw_line.lstrip().startswith(('-', '·', '◦', '•')):
                    sanctions[-1] = sanctions[-1] + ' ' + re.sub(r'\s+', ' ', stripped)
 
    # 결과 정리
    if targets and sanctions:
        # 각 제재대상과 제재내용을 매칭해서 콤마로 구분
        # 같은 인덱스끼리 매칭
        pairs = []
        max_len = max(len(targets), len(sanctions))
        
        for i in range(max_len):
            target = targets[i] if i < len(targets) else ''
            sanction = sanctions[i] if i < len(sanctions) else ''
            if target and sanction:
                # 제재내용이 단순히 "-" 또는 "_"만 있는 경우는 "OCR 오류" 표시
                if sanction.strip() in ['-', '_']:
                    sanction = 'OCR 오류로 추출 실패'
                pairs.append((target, sanction))
        
        if pairs:
            unique_targets = []
            for target_value, _ in pairs:
                for component in target_value.split('|'):
                    component = component.strip()
                    if not component:
                        continue
                    component_key = component.replace(' ', '').replace('|', '').replace('/', '').replace('·', '').replace('ㆍ', '')
                    normalized_component = target_alias_map.get(component_key, component)
                    if normalized_component.endswith('등') and not normalized_component.endswith(' 등'):
                        normalized_component = normalized_component[:-1] + ' 등'
                    if normalized_component not in unique_targets:
                        unique_targets.append(normalized_component)

            sanction_rows = []
            for _, sanction_value in pairs:
                cleaned_sanction = clean_fragment(sanction_value)
                if cleaned_sanction:
                    sanction_rows.append(cleaned_sanction)

            target_result = '|'.join(unique_targets) if unique_targets else '-'
            sanction_result = ' | '.join(sanction_rows) if sanction_rows else '-'
            sanction_result = truncate_after_subsections(sanction_result)
            if (('재심' in content and '재조치 내용' in content) or '재심 처리안' in content) and '제재대상 제재내용' not in content:
                return '재심', '재조치 내용 참조'
            return target_result, sanction_result
        elif targets and sanctions:
            unique_targets = []
            for target_value in targets:
                for component in target_value.split('|'):
                    component = component.strip()
                    if not component:
                        continue
                    component_key = component.replace(' ', '').replace('|', '').replace('/', '').replace('·', '').replace('ㆍ', '')
                    normalized_component = target_alias_map.get(component_key, component)
                    if normalized_component.endswith('등') and not normalized_component.endswith(' 등'):
                        normalized_component = normalized_component[:-1] + ' 등'
                    if normalized_component not in unique_targets:
                        unique_targets.append(normalized_component)
 
            target_str = '|'.join(unique_targets) if unique_targets else '-'
            sanction_values = [clean_fragment(s) for s in sanctions if clean_fragment(s)]
            sanction_str = ' | '.join(sanction_values) if sanction_values else '-'
            sanction_str = truncate_after_subsections(sanction_str)
            if (('재심' in content and '재조치 내용' in content) or '재심 처리안' in content) and '제재대상 제재내용' not in content:
                return '재심', '재조치 내용 참조'
            return target_str, sanction_str

    if (('재심' in content and '재조치 내용' in content) or '재심 처리안' in content) and '제재대상 제재내용' not in content:
        return '재심', '재조치 내용 참조'
 
    return '-', '-'

if __name__ == "__main__":
    # JSON 파일 읽기
    print("JSON 파일 읽는 중...")
    with open('fss_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"총 {len(data)}개 항목 로드 완료")

    # 각 항목에 제재대상과 제재내용 추가
    print("\n제재대상과 제재내용 추출 중...")
    for idx, item in enumerate(data, 1):
        content = item.get('제재조치내용', '')
        result = extract_sanction_info(content)
        if not isinstance(result, tuple) or len(result) != 2:
            target, sanction = '-', '-'
        else:
            target, sanction = result

        if target == '-' and sanction == '-':
            collapsed_content = collapse_split_syllables(content)
            inline_pattern = re.compile(r'(?:제재대상|대상)\s*(?:제재내용|내용)\s*(기관|임원|직원|임직원)\s*([^\r\n]+)', re.DOTALL)
            simple_match = inline_pattern.search(collapsed_content)
            if simple_match:
                target = simple_match.group(1)
                sanction = simple_match.group(2).strip()
                sanction = re.sub(r'\s+', ' ', sanction)
            else:
                collapsed_lines = [line.strip() for line in collapsed_content.splitlines()]
                for i, line in enumerate(collapsed_lines):
                    header = line.replace(' ', '')
                    if ('대상' in header or '제재대상' in header) and ('내용' in header or '제재내용' in header):
                        if i + 1 < len(collapsed_lines):
                            candidate = collapsed_lines[i + 1]
                            candidate_no_space = candidate.replace(' ', '')
                            for prefix in ('기관', '임원', '직원', '임직원'):
                                if candidate_no_space.startswith(prefix):
                                    remainder = candidate[len(prefix):].strip()
                                    if remainder:
                                        target = prefix
                                        sanction = re.sub(r'\s+', ' ', remainder)
                                    break
                        if target != '-' or sanction != '-':
                            break

        item['제재대상'] = target if target and str(target).strip() else '-'
        item['제재내용'] = sanction if sanction and str(sanction).strip() else '-'
        
        # 사건제목과 사건내용 추출
        incidents = extract_incidents(content)
        item['사건목록'] = incidents
        
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

    # CSV 파일 생성 (사건이 여러 개인 경우 행 확장)
    csv_rows = []
    base_fieldnames = ['번호', '제재대상기관', '제재조치요구일', '관련부서', '조회수', '문서유형', '상세페이지URL', 
                      '제재조치내용', '제재대상', '제재내용']
    
    for item in data:
        incidents = item.get('사건목록', [])
        
        if not incidents:
            # 사건이 없으면 기본 정보만
            row = {}
            for field in base_fieldnames:
                row[field] = item.get(field, '')
            row['사건제목'] = ''
            row['사건내용'] = ''
            csv_rows.append(row)
        else:
            # 사건이 있으면 각 사건마다 행 생성
            for incident in incidents:
                row = {}
                for field in base_fieldnames:
                    row[field] = item.get(field, '')
                row['사건제목'] = incident.get('사건제목', '')
                row['사건내용'] = incident.get('사건내용', '')
                csv_rows.append(row)
    
    fieldnames = base_fieldnames + ['사건제목', '사건내용']
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
        target = item.get('제재대상', '')
        sanction = item.get('제재내용', '')
        print(f"\n[{i+1}] {item['제재대상기관']}")
        print(f"  제재대상: {target if target else '(추출 실패)'}")
        if sanction:
            sanction_short = sanction[:80] + '...' if len(sanction) > 80 else sanction
            print(f"  제재내용: {sanction_short}")
        else:
            print(f"  제재내용: (추출 실패)")

    # 추출 성공률 확인
    success_count = sum(1 for item in data if item.get('제재대상') and item.get('제재내용'))
    print(f"\n추출 성공: {success_count}/{len(data)}개 항목")

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

