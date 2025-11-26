import json
import re
import csv
import sys

# UTF-8 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

# 한글 음절 분리 패턴 (OCR 오인식 보정용)
split_syllable_pattern = re.compile(r'([가-힣])\s+([가-힣])')

def collapse_split_syllables(text: str) -> str:
    if not text:
        return text
    return split_syllable_pattern.sub(lambda m: m.group(0).replace(' ', ''), text)

def extract_incidents(content):
    """
    경영유의사항 등 공시에서 사건제목과 사건내용 추출
    
    패턴:
    1. "4. 조치대상사실" 또는 "4. 제재대상사실" 찾기
    2. 그 아래 "가. 경영유의사항" 또는 "가. 개선사항" 같은 부제목이 있을 수 있음
    3. 부제목 아래에 "(1) ..." 형태로 시작하는 것이 사건제목
    4. 다음 "(2)" 또는 다음 "가." 등이 나오기 전까지가 사건내용
    """
    if not content or content.startswith('[') or content.startswith('[오류'):
        return []
    
    incidents = []
    
    # "조치대상사실" 또는 "제재대상사실" 섹션 찾기
    section_patterns = [
        r'4\.\s*조\s*치\s*대\s*상\s*사\s*실',
        r'4\.\s*조치대상사실',
        r'4\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'4\.\s*제재대상사실',
        r'Ⅳ\.\s*조\s*치\s*대\s*상\s*사\s*실',
        r'Ⅳ\.\s*조치대상사실',
        r'Ⅳ\.\s*제\s*재\s*대\s*상\s*사\s*실',
        r'Ⅳ\.\s*제재대상사실',
    ]
    
    section_start = -1
    section_text = ""
    
    for pattern in section_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            section_start = match.end()
            # 다음 섹션까지 추출 (5. 또는 다음 주요 섹션)
            next_section_pattern = r'(?:5\.|Ⅴ\.|V\.|5\s*\.|제\s*재\s*조\s*치\s*내\s*용|결\s*론|참\s*고\s*사\s*항|참고사항)'
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
    skip_until_numbered = False  # "가. 개선사항" 같은 부제목을 건너뛰기 위한 플래그
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # 부제목 패턴: "가. 경영유의사항", "가. 개선사항" 등
        subtitle_pattern = r'^[가-하]\.\s*(경\s*영\s*유\s*의\s*사\s*항|경영유의사항|개\s*선\s*사\s*항|개선사항|문\s*책\s*사\s*항|문책사항)(.*)$'
        subtitle_match = re.match(subtitle_pattern, line)
        
        if subtitle_match:
            # 부제목은 건너뛰고, 다음 "(1)" 패턴을 찾기 시작
            skip_until_numbered = True
            i += 1
            continue
        
        # "(1) 사건제목" 패턴 또는 "⑴ 사건제목" 패턴 (전각 괄호 숫자)
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
            skip_until_numbered = False
            if numbered_match.lastindex >= 2:
                current_title = numbered_match.group(2).strip()
            elif numbered_match.lastindex >= 1 and numbered_match.group(1):
                # 숫자만 매칭된 경우, 전체 라인에서 숫자 제거
                title_text = line
                # "(1)" 또는 "⑴" 같은 패턴 제거
                title_text = re.sub(r'^[\(（]?\d+[\)）]?\s*', '', title_text)
                title_text = re.sub(r'^[\u2474-\u247C]\s*', '', title_text)
                current_title = title_text.strip()
            else:
                # 전각 괄호 숫자 제거
                current_title = line.replace('⑴', '').replace('⑵', '').replace('⑶', '').replace('⑷', '').replace('⑸', '').replace('⑹', '').replace('⑺', '').replace('⑻', '').replace('⑼', '').strip()
            
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # 부제목 이후에도 계속 건너뛰기
        if skip_until_numbered:
            i += 1
            continue
        
        # 하위 목차 패턴: "(가)", "(나)", "(다)" 등은 사건내용의 일부
        sub_item_pattern = r'^\([가-하]\)\s*(.+)$'
        sub_item_match = re.match(sub_item_pattern, line)
        
        if sub_item_match:
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
                current_title = None
                current_content = []
                in_incident = False
                # 이 줄은 다음 사건의 시작일 수 있으므로 다시 처리
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
    
    # OCR로 추출된 텍스트는 글자 사이에 공백이 있을 수 있음
    content = collapse_split_syllables(content)
    content_no_space = content.replace(' ', '')

    # 반복적으로 등장하는 OCR 치환 오류 보정
    ocr_replacements = {
        '오 혐 설 계 사': '보험설계사',
        '오혐설계사': '보험설계사',
        '로 혐 설 계 사': '보험설계사',
        '로혐설계사': '보험설계사',
    }
    for wrong, correct in ocr_replacements.items():
        content = content.replace(wrong, correct)
        content_no_space = content_no_space.replace(wrong.replace(' ', ''), correct.replace(' ', ''))

    target_alias_map = {
        '기관': '기관',
        '임원': '임원',
        '직원': '직원',
        '임직원': '임직원',
    }

    # 제재대상과 제재내용 추출 로직
    target = '-'
    sanction = '-'
    
    # "제재조치내용" 또는 "조치내용" 섹션 찾기
    pattern_section = r'3\.\s*(?:제\s*재\s*)?조\s*치\s*내\s*용'
    match_section = re.search(pattern_section, content, re.IGNORECASE)
    
    if match_section:
        section_start = match_section.end()
        # "4." 섹션 전까지 추출
        next_section = re.search(r'4\.', content[section_start:])
        if next_section:
            section_text = content[section_start:section_start + next_section.start()].strip()
        else:
            section_text = content[section_start:].strip()
        
        # 테이블 형태 찾기
        table_pattern = r'(?:제재|조치)\s*대\s*상\s*(?:제재|조치)\s*내\s*용'
        if re.search(table_pattern, section_text, re.IGNORECASE):
            # 테이블 형태 파싱
            lines = section_text.split('\n')
            for line in lines:
                line_no_space = line.replace(' ', '')
                for prefix in ('기관', '임원', '직원', '임직원'):
                    if line_no_space.startswith(prefix):
                        target = prefix
                        remainder = line[len(prefix):].strip()
                        if remainder:
                            sanction = remainder.strip()
                            break
                if target != '-':
                    break
    
    return target, sanction

if __name__ == "__main__":
    # JSON 파일 읽기
    print("JSON 파일 읽는 중...")
    json_filename = 'fss_results.json'
    
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {json_filename}")
        sys.exit(1)
    
    print(f"총 {len(data)}개 항목 로드 완료")
    
    # 각 항목에 사건제목과 사건내용 추가
    print("\n사건제목과 사건내용 추출 중...")
    for idx, item in enumerate(data, 1):
        content = item.get('제재조치내용', '')
        
        # 제재대상과 제재내용 추출 (기존 코드 유지)
        if '제재대상' not in item or not item.get('제재대상') or item.get('제재대상') == '-':
            target, sanction = extract_sanction_info(content)
            item['제재대상'] = target if target else '-'
            item['제재내용'] = sanction if sanction else '-'
        
        # 사건 추출
        incidents = extract_incidents(content)
        item['사건목록'] = incidents
        
        if idx % 10 == 0:
            print(f"  {idx}개 항목 처리 완료...")
    
    # 결과 저장
    print("\n결과 저장 중...")
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("JSON 파일 저장 완료")
    
    # CSV 파일 생성 (사건이 여러 개인 경우 행 확장)
    print("CSV 파일 생성 중...")
    csv_filename = json_filename.replace('.json', '.csv')
    
    base_fieldnames = ['번호', '제재대상기관', '제재조치요구일', '관련부서', '조회수', '문서유형', '상세페이지URL', 
                      '제재조치내용', '제재대상', '제재내용']
    
    csv_rows = []
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
    print("\n처리 결과 샘플 (사건이 추출된 첫 3개 항목):")
    sample_count = 0
    for item in data:
        incidents = item.get('사건목록', [])
        if incidents:
            print(f"\n[{item.get('번호', 'N/A')}] {item.get('제재대상기관', 'N/A')}")
            print(f"  추출된 사건 수: {len(incidents)}개")
            for i, incident in enumerate(incidents[:2], 1):  # 최대 2개만 표시
                title = incident.get('사건제목', '')[:50]
                print(f"  {i}. {title}...")
            sample_count += 1
            if sample_count >= 3:
                break
