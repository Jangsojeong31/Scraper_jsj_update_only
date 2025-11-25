import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

def clean_ocr_artifacts(text):
    """OCR 인공물 제거"""
    if not text:
        return text
    
    # "_ ｜ -" 패턴 제거
    text = re.sub(r'_\s*[｜\|]\s*-\s*', '', text)
    
    # 과도한 공백 정리
    text = re.sub(r'\s+', ' ', text)

    # 앞쪽 불필요한 하이픈 제거
    text = text.lstrip('- ').lstrip('·').lstrip('- ')
    text = text.lstrip('. ')

    # 한글 사이의 공백 제거
    text = re.sub(r'(?<=[가-힣])\s+(?=[가-힣])', '', text)

    # 숫자-한글 사이 공백 제거
    text = re.sub(r'(?<=\d)\s+(?=[가-힣])', '', text)

    # 한글 글자 사이 공백 제거 (예: "등 록 취 소" → "등록취소")
    text = re.sub(r'등\s+록\s+취\s+소', '등록취소', text)
    text = re.sub(r'업\s+무\s+정\s+지', '업무정지', text)
    text = re.sub(r'과\s+태\s+료', '과태료', text)
    text = re.sub(r'견\s+책', '견책', text)
    text = re.sub(r'감\s+봉', '감봉', text)

    # 고립된 ㅣ, ` 등 제거
    text = re.sub(r'\bㅣ\b', '', text)
    text = text.replace('`', '')

    return text.strip()

def fix_known_ocr_patterns(data):
    """알려진 OCR 오류 패턴 자동 수정"""
    fixed_count = 0
    
    # 알려진 문제 항목 (OCR이 완전히 실패하는 케이스)
    known_fixes = {
        '102': ('보험설계사', '등록취소 1명'),
        '104': ('보험설계사', '등록취소 1명'),
        '106': ('보험설계사', '등록취소 1명'),
        '111': ('보험설계사', '보험사기 연루 행위 - 금융위원회 제재 건의')
    }
    
    for item in data:
        num = item['번호']
        content = item['제재조치내용']
        target = item.get('제재대상', '')
        sanction = item.get('제재내용', '')
        doc_type = item.get('문서유형', '')
        
        # 알려진 문제 항목 강제 수정
        if num in known_fixes and (not target or target == '-' or not sanction or sanction == '-'):
            fix_target, fix_sanction = known_fixes[num]
            item['제재대상'] = fix_target
            item['제재내용'] = fix_sanction
            item['문서유형'] = 'PDF-OCR'
            fixed_count += 1
            print(f"[{num}번] 알려진 문제 항목 수정: - → {fix_target} / {fix_sanction}")
        
        # 패턴 1: "_ ｜ -" 패턴이 제재내용에 남아있는 경우
        if '_ ｜ -' in sanction or '_ | -' in sanction:
            original_sanction = sanction
            sanction = clean_ocr_artifacts(sanction)
            
            if sanction != original_sanction:
                item['제재내용'] = sanction
                if doc_type == 'PDF-OCR필요':
                    item['문서유형'] = 'PDF-OCR'
                fixed_count += 1
                print(f"[{num}번] OCR 인공물 제거: {original_sanction[:50]} → {sanction[:50]}")
        
        # 패턴 2: "보험설계사 _ ｜ -" 패턴 (102, 104번 유형)
        if target == '보험설계사' and (sanction in ['_ ｜ -', '_ | -', '-'] or not sanction or sanction == 'OCR 오류로 추출 실패'):
            # 제재조치내용에서 재추출
            section_match = re.search(r'3\.\s*제\s*재\s*조\s*치\s*내\s*용.*?\n(.{200})', content, re.DOTALL)
            if section_match:
                section = section_match.group(1)
                
                # "보 험 설 계 사 _ ｜ - 등 록 취 소 1 명" 패턴
                line_match = re.search(r'보\s*험\s*설\s*계\s*사\s+[_｜\|]\s*-\s*([^\n]+)', section)
                if line_match:
                    extracted = line_match.group(1).strip()
                    
                    # 등록취소 패턴
                    if re.search(r'등\s*록\s*취\s*소', extracted):
                        numbers = re.findall(r'\d+', extracted)
                        if numbers:
                            item['제재내용'] = f'등록취소 {numbers[0]}명'
                            item['문서유형'] = 'PDF-OCR'
                            fixed_count += 1
                            print(f"[{num}번] 패턴 2 수정: {sanction} → 등록취소 {numbers[0]}명")
        
        # 패턴 3: "이0" 패턴 (106, 111번 유형 - 보험사기대응단)
        if target == '보험설계사' and (sanction == 'OCR 오류로 추출 실패' or not sanction or sanction == '-'):
            if '이0' in content and re.search(r'보\s*험\s*설\s*계\s*사\s*-', content):
                # 보험사기 키워드 확인
                if re.search(r'보\s*험\s*사\s*기', content):
                    # 제재대상사실에서 등록취소 확인
                    fact_match = re.search(r'4\.\s*제\s*재\s*대\s*상\s*사\s*실', content)
                    if fact_match:
                        fact_section = content[fact_match.end():][:1000]
                        
                        if re.search(r'등\s*록\s*취\s*소', fact_section):
                            item['제재내용'] = '등록취소 1명'
                            item['문서유형'] = 'PDF-OCR'
                            fixed_count += 1
                            print(f"[{num}번] 패턴 3 수정 (등록취소): {sanction} → 등록취소 1명")
                        elif not re.search(r'등\s*록\s*취\s*소', content) and not re.search(r'업\s*무\s*정\s*지', content):
                            # 제재 내용이 없으면 금융위원회 건의
                            item['제재내용'] = '보험사기 연루 행위 - 금융위원회 제재 건의'
                            item['문서유형'] = 'PDF-OCR'
                            fixed_count += 1
                            print(f"[{num}번] 패턴 3 수정 (금융위 건의): {sanction} → 금융위원회 제재 건의")
        
        # 패턴 4: "OCR 오류로 추출 실패" 문구가 다른 내용과 혼재된 경우
        if 'OCR 오류로 추출 실패' in sanction and len(sanction) > 30:
            # 다른 내용이 있으면 OCR 오류 문구만 제거
            cleaned = re.sub(r',?\s*OCR 오류로 추출 실패,?\s*', ', ', sanction)
            cleaned = re.sub(r',\s*,', ',', cleaned).strip(', ')
            
            if cleaned != sanction:
                item['제재내용'] = cleaned
                fixed_count += 1
                print(f"[{num}번] OCR 오류 문구 제거")
    
    return fixed_count

def validate_and_report(data):
    """품질 검증 및 리포트"""
    issues = []
    
    for item in data:
        num = item['번호']
        target = item.get('제재대상', '')
        sanction = item.get('제재내용', '')
        
        # 제재대상/제재내용이 비어있거나 '-'인 경우
        if not target or target == '-':
            if not sanction or sanction == '-':
                # 135번(국민은행) 같은 제재대상 없음 케이스는 정상
                continue
        
        # "OCR 오류로 추출 실패"가 단독으로 있는 경우
        if sanction == 'OCR 오류로 추출 실패':
            issues.append({
                'num': num,
                'name': item['제재대상기관'],
                'issue': 'OCR 오류로 추출 실패 (재처리 필요)'
            })
        
        # 제재내용이 비정상적으로 짧은 경우 (5자 이하)
        elif sanction and len(sanction) <= 5 and sanction not in ['-', '조치생략']:
            issues.append({
                'num': num,
                'name': item['제재대상기관'],
                'issue': f'제재내용이 너무 짧음: {sanction}'
            })
    
    return issues

def main():
    print("=" * 100)
    print("OCR 후처리 및 품질 검증")
    print("=" * 100)
    
    # JSON 파일 로드
    with open('fss_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\n총 {len(data)}개 항목 로드")
    
    # 알려진 패턴 자동 수정
    print("\n1. 알려진 OCR 오류 패턴 자동 수정 중...")
    fixed_count = fix_known_ocr_patterns(data)
    print(f"   → {fixed_count}개 항목 자동 수정 완료")
    
    # 품질 검증
    print("\n2. 품질 검증 중...")
    issues = validate_and_report(data)
    
    if issues:
        print(f"   ⚠️ {len(issues)}개 항목에 문제 발견:")
        for issue in issues[:10]:  # 처음 10개만 출력
            print(f"      [{issue['num']}번] {issue['name']}: {issue['issue']}")
        if len(issues) > 10:
            print(f"      ... 외 {len(issues) - 10}개 항목")
    else:
        print("   ✓ 모든 항목 정상")
    
    # 저장
    if fixed_count > 0:
        print("\n3. 수정된 결과 저장 중...")

        for row in data:
            target = row.get('\uC81C\uC7AC\uB300\uC0C1')
            sanction = row.get('\uC81C\uC7AC\uB0B4\uC6A9')
            if target:
                row['\uC81C\uC7AC\uB300\uC0C1'] = target.strip()
            if sanction:
                row['\uC81C\uC7AC\uB0B4\uC6A9'] = clean_ocr_artifacts(sanction)

        with open('fss_results.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
 
        # CSV도 재생성 (사건이 여러 개인 경우 행 확장)
        import csv
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
        with open('fss_results.csv', 'w', newline='', encoding='utf-8-sig') as f:
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
 
        print("   ✓ JSON 및 CSV 파일 저장 완료")
    
    print("\n" + "=" * 100)
    print(f"완료! (자동 수정: {fixed_count}개, 검토 필요: {len(issues)}개)")
    print("=" * 100)

if __name__ == '__main__':
    main()

