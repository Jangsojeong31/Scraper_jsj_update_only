import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('fss_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("제재대상/제재내용이 '-'인 항목:")
print("=" * 80)

empty_items = [i for i in data if i.get('제재대상') == '-' and i.get('제재내용') == '-']

for item in empty_items[:20]:
    print(f"[{item['번호']}번] {item['제재대상기관']}")

print(f"\n총 {len(empty_items)}개 항목")

# 135번 (국민은행)이 포함되어 있는지 확인
has_135 = any(i['번호'] == '135' for i in empty_items)
print(f"\n135번 (국민은행 - 정상 케이스) 포함: {'✓' if has_135 else '✗'}")



