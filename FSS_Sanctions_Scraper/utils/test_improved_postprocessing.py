"""개선된 OCR 후처리 테스트"""
import json
from post_process_ocr import clean_ocr_artifacts

with open('fss_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

ocr_items = [item for item in data if item.get('OCR추출여부') == '예']
print(f'=== OCR 항목 후처리 적용 테스트 (총 {len(ocr_items)}개) ===\n')

for i, item in enumerate(ocr_items[:5], 1):
    print(f'{i}. {item.get("금융회사명", "N/A")}')
    before = item.get('제재내용', '')
    after = clean_ocr_artifacts(before)
    print(f'   Before: {before[:150]}')
    print(f'   After:  {after[:150]}')
    print()

