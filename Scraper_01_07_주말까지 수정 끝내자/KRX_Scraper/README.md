# 한국거래소 스크래퍼

한국거래소 KRX법무포탈에서 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://rule.krx.co.kr/out/index.do

한국거래소 KRX법무포탈에서 법규 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 KRX_Scraper/krx_scraper.py
```

## 주요 기능

- KRX법무포탈 크롤링
- 법규 정보 수집

## 출력 파일

- `output/krx_legal.json`: JSON 형식 결과
- `output/krx_legal.csv`: CSV 형식 결과

## 참고사항

- 웹에서 확인 가능한 정보를 수집합니다.
- Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리할 수 있습니다.

