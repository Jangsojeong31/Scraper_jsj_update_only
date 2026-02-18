# 법제처 - 국가법령정보센터 스크래퍼

법제처 국가법령정보센터에서 법령 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query=

법령명, 법령 종류, 공포일자, 시행일자, 소관부처, 법령 상세 링크, 법령 본문 내용 등을 수집합니다.

## 실행 방법

### 기본 실행 (전체 크롤링)

```bash
# 프로젝트 루트에서 실행
python3 Law_Scraper/law_scraper.py
```

### 옵션 사용

```bash
# 키워드 검색
python3 Law_Scraper/law_scraper.py --query 환경

# 목록 제한 (테스트용)
python3 Law_Scraper/law_scraper.py --limit 10 --details-limit 5
```

## 옵션

- `--query`, `-q`: 검색 키워드 (법령명)
- `--limit`: 검색 목록에서 가져올 개수 제한 (0=전체, 기본값: 0)
- `--details-limit`: 상세 내용 크롤링 개수 제한 (0=전체, 기본값: 0)

## 출력 파일

- `output/law_search_results.json`: JSON 형식 결과
- `output/law_search_results.xlsx`: Excel 형식 결과
  - `data` 시트: 크롤링된 데이터
  - `meta` 시트: 메타 정보 (URL, 크롤링 시간, 총 개수 등)

## 수집 정보

- 법령명
- 법령 종류 (법률, 대통령령, 부령 등)
- 공포일자
- 시행일자
- 소관부처
- 법령 상세 링크
- 법령 본문 내용

## 참고사항

- Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리합니다.
- ChromeDriver가 필요합니다.

