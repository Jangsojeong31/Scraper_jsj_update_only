# 금융투자협회 스크래퍼

금융투자협회 법규정보시스템에서 법규 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: http://law.kofia.or.kr/service/law/lawCurrentMain.do

금융투자협회 법규정보시스템의 법규 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 KOFIA_Scraper/kofia_scraper.py
```

## 주요 기능

- 왼쪽 트리 구조에서 모든 규정 링크 추출
- 각 규정의 상세 정보 수집
- iframe 구조 처리
- JavaScript 동적 로드 페이지 처리

## 출력 파일

- `output/kofia_law.json`: JSON 형식 결과
- `output/kofia_law.csv`: CSV 형식 결과

## 수집 정보

- 규정명
- 규정 유형
- 제정/개정 일자
- 상세 내용
- 관련 링크

## 참고사항

- Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리합니다.
- iframe 구조를 포함한 복잡한 페이지 구조를 처리합니다.
- ChromeDriver가 필요합니다.

