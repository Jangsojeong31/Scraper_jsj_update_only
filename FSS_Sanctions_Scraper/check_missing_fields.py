import json
import sys

# UTF-8 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

# JSON 파일 읽기
json_filename = 'fss_results.json'

try:
    with open(json_filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"파일을 찾을 수 없습니다: {json_filename}")
    sys.exit(1)

total_announcements = len(data)
announcements_without_incidents = 0
total_incidents = 0
incidents_without_title = 0
incidents_without_content = 0
incidents_without_both = 0

# 각 공시 항목 확인
for item in data:
    incidents = item.get('사건목록', [])
    
    # 사건이 없는 공시
    if not incidents or len(incidents) == 0:
        announcements_without_incidents += 1
        continue
    
    # 각 사건 확인
    for incident in incidents:
        total_incidents += 1
        title = incident.get('사건제목', '').strip()
        content = incident.get('사건내용', '').strip()
        
        has_title = bool(title)
        has_content = bool(content)
        
        if not has_title:
            incidents_without_title += 1
        if not has_content:
            incidents_without_content += 1
        if not has_title and not has_content:
            incidents_without_both += 1

# 결과 출력
print("=" * 60)
print("금융감독원 제재조치 스크래핑 통계")
print("=" * 60)
print(f"\n총 공시 개수: {total_announcements}개")
print(f"사건이 없는 공시: {announcements_without_incidents}개 ({announcements_without_incidents/total_announcements*100:.1f}%)" if total_announcements > 0 else "사건이 없는 공시: 0개")
print(f"사건이 있는 공시: {total_announcements - announcements_without_incidents}개")

print(f"\n총 사건 개수: {total_incidents}개")
if total_incidents > 0:
    print(f"\n사건제목이 없는 사건: {incidents_without_title}개 ({incidents_without_title/total_incidents*100:.1f}%)")
    print(f"사건내용이 없는 사건: {incidents_without_content}개 ({incidents_without_content/total_incidents*100:.1f}%)")
    print(f"사건제목과 사건내용 모두 없는 사건: {incidents_without_both}개")
else:
    print("\n추출된 사건이 없습니다.")

print(f"\n{'='*60}")
print(f"요약:")
print(f"  - 총 {total_announcements}개 공시 중")
print(f"  - 사건제목이 없는 사건: {incidents_without_title}개/{total_incidents}개")
print(f"  - 사건내용이 없는 사건: {incidents_without_content}개/{total_incidents}개")
print(f"{'='*60}")

