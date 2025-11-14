import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('fss_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 100)
print("중요 항목 (102, 104, 106, 111번) 검증")
print("=" * 100)

critical_nums = ['102', '104', '106', '111']
expected = {
    '102': ('보험설계사', '등록취소 1명'),
    '104': ('보험설계사', '등록취소 1명'),
    '106': ('보험설계사', '등록취소 1명'),
    '111': ('보험설계사', '보험사기 연루 행위 - 금융위원회 제재 건의')
}

all_ok = True
for num in critical_nums:
    item = [i for i in data if i['번호'] == num][0]
    exp_target, exp_sanction = expected[num]
    
    target = item.get('제재대상', '')
    sanction = item.get('제재내용', '')
    
    target_ok = target == exp_target
    sanction_ok = sanction == exp_sanction or (num == '102' and '등록취소 1명' in sanction)
    
    print(f"\n[{num}번] {item['제재대상기관']}")
    print(f"  제재대상: {target} {'✓' if target_ok else '✗ (예상: ' + exp_target + ')'}")
    print(f"  제재내용: {sanction} {'✓' if sanction_ok else '✗ (예상: ' + exp_sanction + ')'}")
    
    if not (target_ok and sanction_ok):
        all_ok = False

print("\n" + "=" * 100)
if all_ok:
    print("✅ 모든 중요 항목이 정확합니다!")
else:
    print("⚠️ 일부 항목에 문제가 있습니다. 수동 수정이 필요합니다.")
print("=" * 100)



