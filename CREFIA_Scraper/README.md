# 여신금융협회 스크래퍼

여신금융협회의 자율규제 정보를 수집하는 스크래퍼입니다.

## 개요

여신금융협회에서 제공하는 자율규제 현황 및 제·개정 공고 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 CREFIA_Scraper/crefia_scraper.py
```

## 주요 기능

### 1. 자율규제 현황 크롤링

**URL**: https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx

기준일 없이 다운로드만 가능한 자율규제 현황 정보를 수집합니다.

### 2. 자율규제 제·개정 공고 크롤링

자율규제 제·개정 공고 정보를 수집합니다. 개정 예고로, 등재일자 확인이 가능합니다.

## 출력 파일

- `output/crefia_self_regulation.json`: JSON 형식 결과
- `output/crefia_self_regulation.csv`: CSV 형식 결과

## 수집 정보

- 제목
- 등재일자
- 다운로드 링크
- 첨부파일

## 참고사항

- 일부 정보는 기준일 없이 다운로드만 가능합니다.
- 첨부파일은 `output/downloads/` 디렉토리에 저장됩니다.

