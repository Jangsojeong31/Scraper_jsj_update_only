"""
누락 필드 표시 컬럼 추가 스크립트
- JSON과 CSV 파일에 '누락필드' 컬럼 추가
- 제재내용, 제목, 내용의 누락 여부를 표시
"""
import json
import csv
from pathlib import Path

def has_value(value):
    """값이 있는지 확인 (None, 빈 문자열, '-', 공백만 있는 경우 False)"""
    if not value:
        return False
    value_str = str(value).strip()
    return bool(value_str and value_str != '-')

def get_missing_fields(item):
    """누락된 필드 목록 반환"""
    missing = []
    
    if not has_value(item.get('제재내용', '')):
        missing.append('제재내용')
    
    if not has_value(item.get('제목', '')):
        missing.append('제목')
    
    if not has_value(item.get('내용', '')):
        missing.append('내용')
    
    return missing

def add_missing_field_column():
    """JSON과 CSV 파일에 누락 필드 컬럼 추가"""
    json_path = Path('fss_results.json')
    csv_path = Path('fss_results.csv')
    
    if not json_path.exists():
        print(f"❌ JSON 파일을 찾을 수 없습니다: {json_path}")
        return
    
    print("=" * 100)
    print("누락 필드 표시 컬럼 추가")
    print("=" * 100)
    
    # JSON 파일 로드
    with json_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\n총 {len(data)}개 레코드 처리 중...")
    
    # 누락 필드 통계
    stats = {
        '완전': 0,
        '제재내용누락': 0,
        '제목누락': 0,
        '내용누락': 0,
        '제목내용누락': 0,
        '제재내용제목누락': 0,
        '제재내용내용누락': 0,
        '전체누락': 0
    }
    
    # 각 레코드에 누락 필드 컬럼 추가
    for item in data:
        missing = get_missing_fields(item)
        
        if not missing:
            item['누락필드'] = ''
            stats['완전'] += 1
        elif missing == ['제재내용']:
            item['누락필드'] = '제재내용'
            stats['제재내용누락'] += 1
        elif missing == ['제목']:
            item['누락필드'] = '제목'
            stats['제목누락'] += 1
        elif missing == ['내용']:
            item['누락필드'] = '내용'
            stats['내용누락'] += 1
        elif missing == ['제목', '내용']:
            item['누락필드'] = '제목,내용'
            stats['제목내용누락'] += 1
        elif missing == ['제재내용', '제목']:
            item['누락필드'] = '제재내용,제목'
            stats['제재내용제목누락'] += 1
        elif missing == ['제재내용', '내용']:
            item['누락필드'] = '제재내용,내용'
            stats['제재내용내용누락'] += 1
        elif missing == ['제재내용', '제목', '내용']:
            item['누락필드'] = '제재내용,제목,내용'
            stats['전체누락'] += 1
        else:
            # 기타 조합
            item['누락필드'] = ','.join(missing)
    
    # JSON 파일 저장
    print("\nJSON 파일 저장 중...")
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ JSON 파일 저장 완료: {json_path}")
    
    # CSV 파일 업데이트
    if csv_path.exists():
        print("\nCSV 파일 업데이트 중...")
        
        # CSV 읽기
        csv_rows = []
        with csv_path.open('r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                # 해당 레코드 찾기 (URL로 매칭)
                url = row.get('상세페이지URL', '')
                matching_item = next((item for item in data if item.get('상세페이지URL', '') == url), None)
                
                if matching_item:
                    row['누락필드'] = matching_item.get('누락필드', '')
                else:
                    # URL로 매칭 안되면 직접 계산
                    missing = get_missing_fields(row)
                    row['누락필드'] = ','.join(missing) if missing else ''
                
                csv_rows.append(row)
        
        # CSV 쓰기
        new_fieldnames = list(fieldnames) + ['누락필드'] if '누락필드' not in fieldnames else fieldnames
        with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(csv_rows)
        
        print(f"✓ CSV 파일 저장 완료: {csv_path}")
    else:
        print(f"\n⚠️ CSV 파일이 없습니다: {csv_path}")
        print("   JSON에서 CSV를 새로 생성합니다...")
        
        # CSV 생성
        if data:
            fieldnames = list(data[0].keys())
            with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(data)
            print(f"✓ CSV 파일 생성 완료: {csv_path}")
    
    # 통계 출력
    print("\n" + "=" * 100)
    print("누락 필드 통계")
    print("=" * 100)
    total = len(data)
    for status, count in stats.items():
        if count > 0:
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {status}: {count:,}개 ({pct:.1f}%)")
    
    complete_pct = (stats['완전'] / total * 100) if total > 0 else 0
    print(f"\n  전체 완전성: {stats['완전']:,}/{total:,} ({complete_pct:.1f}%)")
    print("=" * 100)
    print("완료!")

if __name__ == '__main__':
    add_missing_field_column()

