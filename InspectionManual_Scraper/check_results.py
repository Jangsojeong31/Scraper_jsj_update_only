import json
import sys

# UTF-8 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

# JSON 파일 읽기
json_filename = 'inspection_results.json'

try:
    with open(json_filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"파일을 찾을 수 없습니다: {json_filename}")
    sys.exit(1)

total_records = len(data)

# 고유한 메뉴얼 수 계산 (번호 기준)
unique_manuals = {}
for record in data:
    number = record.get('번호', '')
    if number not in unique_manuals:
        unique_manuals[number] = {
            '제목': record.get('제목', ''),
            '구분': record.get('구분', ''),
            '등록일': record.get('등록일', ''),
        }

# 항목별 통계
records_with_item = 0
records_without_item = 0
items_with_value = 0
items_without_value = 0

check_items_with_value = 0
check_items_without_value = 0

check_method_with_value = 0
check_method_without_value = 0

# 구분별 통계
category_stats = {}

for record in data:
    # 항목 필드 확인
    item = record.get('항 목', '').strip()
    if item and item != '-':
        records_with_item += 1
        items_with_value += 1
    else:
        items_without_value += 1
        if not item or item == '-':
            records_without_item += 1
    
    # 점검사항 필드 확인
    check_item = record.get('점 검 사 항', '').strip()
    if check_item and check_item != '-':
        check_items_with_value += 1
    else:
        check_items_without_value += 1
    
    # 점검방식 필드 확인
    check_method = record.get('점 검 방 식', '').strip()
    if check_method and check_method != '-':
        check_method_with_value += 1
    else:
        check_method_without_value += 1
    
    # 구분별 통계
    category = record.get('구분', '-')
    if category not in category_stats:
        category_stats[category] = {
            'count': 0,
            'unique_manuals': set()
        }
    category_stats[category]['count'] += 1
    category_stats[category]['unique_manuals'].add(record.get('번호', ''))

# 결과 출력
print("=" * 60)
print("검사업무메뉴얼 스크래핑 결과 통계")
print("=" * 60)

print(f"\n총 레코드 수: {total_records}개")
print(f"고유한 메뉴얼 수: {len(unique_manuals)}개")
print(f"평균 레코드 수/메뉴얼: {total_records/len(unique_manuals):.2f}개" if unique_manuals else "평균 레코드 수/메뉴얼: 0개")

print(f"\n{'='*60}")
print("필드별 통계")
print(f"{'='*60}")

print(f"\n[항 목]")
print(f"  - 값이 있는 레코드: {records_with_item}개 ({records_with_item/total_records*100:.1f}%)")
print(f"  - 값이 없는 레코드: {records_without_item}개 ({records_without_item/total_records*100:.1f}%)")
print(f"  - 총 항목 필드 수: {items_with_value + items_without_value}개")
print(f"  - 값이 있는 항목: {items_with_value}개 ({items_with_value/(items_with_value + items_without_value)*100:.1f}%)" if (items_with_value + items_without_value) > 0 else "  - 값이 있는 항목: 0개")

print(f"\n[점 검 사 항]")
print(f"  - 값이 있는 레코드: {check_items_with_value}개 ({check_items_with_value/total_records*100:.1f}%)")
print(f"  - 값이 없는 레코드: {check_items_without_value}개 ({check_items_without_value/total_records*100:.1f}%)")

print(f"\n[점 검 방 식]")
print(f"  - 값이 있는 레코드: {check_method_with_value}개 ({check_method_with_value/total_records*100:.1f}%)")
print(f"  - 값이 없는 레코드: {check_method_without_value}개 ({check_method_without_value/total_records*100:.1f}%)")

print(f"\n{'='*60}")
print("구분별 통계")
print(f"{'='*60}")

for category, stats in sorted(category_stats.items()):
    unique_count = len(stats['unique_manuals'])
    record_count = stats['count']
    print(f"\n{category}:")
    print(f"  - 고유 메뉴얼 수: {unique_count}개")
    print(f"  - 총 레코드 수: {record_count}개")
    print(f"  - 평균 레코드 수/메뉴얼: {record_count/unique_count:.2f}개" if unique_count > 0 else "  - 평균 레코드 수/메뉴얼: 0개")

print(f"\n{'='*60}")
print("요약")
print(f"{'='*60}")
print(f"  - 총 {len(unique_manuals)}개 메뉴얼에서 {total_records}개 레코드 수집")
print(f"  - 항목 필드 추출률: {items_with_value/(items_with_value + items_without_value)*100:.1f}%" if (items_with_value + items_without_value) > 0 else "  - 항목 필드 추출률: 0%")
print(f"  - 점검사항 필드 추출률: {check_items_with_value/total_records*100:.1f}%")
print(f"  - 점검방식 필드 추출률: {check_method_with_value/total_records*100:.1f}%")
print(f"{'='*60}")

