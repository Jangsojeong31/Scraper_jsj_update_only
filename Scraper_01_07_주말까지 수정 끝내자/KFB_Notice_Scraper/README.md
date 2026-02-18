# 은행연합회 자율규제 제정·개정 예고 스크래퍼

은행연합회의 자율규제 제정·개정 예고 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://www.kfb.or.kr/publicdata/reform_notice.php

은행연합회에서 공개하는 자율규제 제정·개정 예고 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 KFB_Notice_Scraper/kfb_notice_scraper.py

# 또는 KFB_Notice_Scraper 디렉토리에서 실행
cd KFB_Notice_Scraper
python3 kfb_notice_scraper.py
```

## 옵션

- `--limit`: 수집할 최대 건수 지정 (기본 0, 전체)
- `--no-download`: 상세 페이지 첨부 파일 다운로드 생략

## 출력 파일

- `output/kfb_notice.json`: JSON 형식 결과
- `output/kfb_notice.csv`: CSV 형식 결과

## 수집 정보

- 번호
- 제목
- 상세 링크
- 등록일
- 첨부파일 정보
- 첨부파일 다운로드 (HWP, PDF 등)

## 참고사항

- Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리합니다.
- 첨부파일은 `output/downloads/` 디렉토리에 저장됩니다.
- ChromeDriver가 필요합니다.

