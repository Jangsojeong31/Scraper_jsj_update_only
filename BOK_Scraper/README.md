# 한국은행 스크래퍼

한국은행 법규정보에서 규정 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://www.bok.or.kr/portal/singl/law/listSearch.do?menuNo=200200

한국은행 법규정보 - 규정에서 개정일자 확인이 가능한 규정 정보와 PDF 파일을 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 BOK_Scraper/bok_scraper.py
```

## 주요 기능

- 법규정보 - 규정 목록 수집
- 개정일자 확인
- PDF 파일 다운로드
- PDF 텍스트 추출

## 출력 파일

- `output/bok_regulations.json`: JSON 형식 결과
- `output/bok_regulations.csv`: CSV 형식 결과

## 수집 정보

- 규정명
- 개정일자
- PDF 다운로드 링크
- PDF 내용 (텍스트 추출)

## 참고사항

- PDF 파일은 자동으로 다운로드되어 텍스트가 추출됩니다.
- 첨부파일은 `output/downloads/` 디렉토리에 저장됩니다.

