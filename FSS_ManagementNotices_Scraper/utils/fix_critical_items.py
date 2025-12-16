import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('fss_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 100)
print("102, 104, 106, 111번 강제 수정")
print("=" * 100)

fixes = {
    '102': ('보험설계사', '등록취소 1명'),
    '104': ('보험설계사', '등록취소 1명'),
    '106': ('보험설계사', '등록취소 1명'),
    '111': ('보험설계사', '보험사기 연루 행위 - 금융위원회 제재 건의')
}

for item in data:
    num = item['번호']
    if num in fixes:
        target, sanction = fixes[num]
        old_target = item.get('제재대상', '')
        old_sanction = item.get('제재내용', '')
        
        item['제재대상'] = target
        item['제재내용'] = sanction
        
        print(f"\n[{num}번] {item['제재대상기관']}")
        print(f"  제재대상: {old_target} → {target}")
        print(f"  제재내용: {old_sanction} → {sanction}")

# 저장
with open('fss_results.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# CSV 재생성
import csv
with open('fss_results.csv', 'w', newline='', encoding='utf-8-sig') as f:
    if data:
        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

print("\n" + "=" * 100)
print("✓ JSON 및 CSV 파일 저장 완료")
print("=" * 100)



