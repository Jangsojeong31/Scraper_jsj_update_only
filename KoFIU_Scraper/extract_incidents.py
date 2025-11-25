import json
import re
import csv
import sys

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
        
        # 첫 번째 타입: "가. 고객위험평가 관련 절차" 같은 패턴
        # 한글 목차 패턴: 가, 나, 다, 라, 마, 바, 사, 아, 자, 차, 카, 타, 파, 하
        # 또는 숫자 목차: (1), (2), (3) 등
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
            current_title = first_match.group(1).strip()
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # 두 번째 타입: "가. 문 책 사 항" 또는 "가. 문책사항" 다음에 "(1) 직무 관련 정보의 이용 금지 위반" 같은 패턴
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
            
            # 다음 줄에서 "(1) ..." 패턴 찾기
            if i < len(lines):
                next_line = lines[i].strip()
                # "(1) 직무 관련 정보의 이용 금지 위반" 같은 패턴
                numbered_pattern = r'^\((\d+)\)\s*(.+)$'
                numbered_match = re.match(numbered_pattern, next_line)
                
                if numbered_match:
                    current_title = numbered_match.group(2).strip()
                    current_content = []
                    in_incident = True
                    i += 1
                    continue
            
            continue
        
        # 두 번째 타입의 번호 패턴: "(1) 직무 관련 정보의 이용 금지 위반"
        numbered_pattern = r'^\((\d+)\)\s*(.+)$'
        numbered_match = re.match(numbered_pattern, line)
        
        if numbered_match:
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 새 사건 시작
            current_title = numbered_match.group(2).strip()
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # 하위 목차 패턴: "(가)", "(나)", "(다)" 등
        sub_item_pattern = r'^\([가-하]\)\s*(.+)$'
        sub_item_match = re.match(sub_item_pattern, line)
        
        if sub_item_match:
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 새 사건 시작
            current_title = sub_item_match.group(1).strip()
            current_content = []
            in_incident = True
            i += 1
            continue
        
        # 다음 주요 항목이 시작되는지 확인 (다음 "가.", "나." 등)
        if re.match(r'^[가-하]\.\s*', line):
            # 이전 사건 저장
            if current_title and current_content:
                incidents.append({
                    '사건제목': current_title,
                    '사건내용': '\n'.join(current_content).strip()
                })
            
            # 새 항목 시작 (제목 추출)
            first_type_match = re.match(r'^[가-하]\.\s*(.+)$', line)
            if first_type_match:
                current_title = first_type_match.group(1).strip()
                current_content = []
                in_incident = True
            else:
                current_title = None
                current_content = []
                in_incident = False
            i += 1
            continue
        
        # 사건 내용으로 추가
        if in_incident and current_title:
            # 다음 사건 제목이 나오기 전까지는 모두 내용
            # 다음 "가.", "나." 등이 나오거나 "(1)", "(2)" 등이 나오면 중단
            if re.match(r'^[가-하]\.\s*', line) or re.match(r'^\(\d+\)\s*', line):
                # 이전 사건 저장
                if current_title and current_content:
                    incidents.append({
                        '사건제목': current_title,
                        '사건내용': '\n'.join(current_content).strip()
                    })
                # 새 사건 시작 (위에서 처리)
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


if __name__ == "__main__":
    # JSON 파일 읽기
    print("JSON 파일 읽는 중...")
    json_filename = 'kofiu_results.json'
    
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
        incidents = extract_incidents(content)
        
        # 사건이 여러 개일 수 있으므로 리스트로 저장
        # CSV에서는 여러 행으로 확장하거나 구분자로 연결
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
    
    # 기본 필드명
    base_fieldnames = ['번호', '제목', '제재대상기관', '제재조치요구일', '공시일', '조회수', '문서유형', '상세페이지URL', '제재조치내용']
    
    # CSV 행 생성 (사건이 여러 개인 경우 여러 행으로 확장)
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
    
    # CSV 저장
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
                csv_row[field] = str(value)
            writer.writerow(csv_row)
    
    print(f"CSV 파일 저장 완료: {csv_filename}")
    
    # 샘플 확인
    print("\n처리 결과 샘플 (첫 3개 항목):")
    for i in range(min(3, len(data))):
        item = data[i]
        incidents = item.get('사건목록', [])
        print(f"\n[{i+1}] {item.get('제목', 'N/A')}")
        print(f"  사건 개수: {len(incidents)}")
        for j, incident in enumerate(incidents[:2], 1):  # 최대 2개만 표시
            title = incident.get('사건제목', '')
            content = incident.get('사건내용', '')
            print(f"  사건 {j}: {title[:50]}..." if len(title) > 50 else f"  사건 {j}: {title}")
            if content:
                content_short = content[:80] + '...' if len(content) > 80 else content
                print(f"    내용: {content_short}")
    
    # 추출 통계
    total_incidents = sum(len(item.get('사건목록', [])) for item in data)
    items_with_incidents = sum(1 for item in data if item.get('사건목록', []))
    print(f"\n추출 통계:")
    print(f"  총 항목 수: {len(data)}")
    print(f"  사건이 있는 항목: {items_with_incidents}")
    print(f"  총 사건 수: {total_incidents}")
    print(f"  평균 사건 수: {total_incidents / len(data) if data else 0:.2f}")
    
    print("\n완료!")

