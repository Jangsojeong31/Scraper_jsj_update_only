# 저축은행중앙회 스크래퍼

저축은행중앙회 SBLAW 포탈에서 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://www.fsb.or.kr/coslegianno_0200.act?ETC_YN=Y

저축은행중앙회 SBLAW 표준규정·약관 연혁관리시스템에서 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 FSB_Scraper/fsb_scraper.py
```

## 주요 기능

- SBLAW 포탈 크롤링
- 표준규정·약관 정보 수집

## 주의사항

⚠️ **로그인 필요**: 이 사이트는 사용자 로그인이 필요한 사이트입니다. 추가 구현이 필요할 수 있습니다.

## 출력 파일

- `output/fsb_sblaw.json`: JSON 형식 결과
- `output/fsb_sblaw.csv`: CSV 형식 결과

## 참고사항

- 로그인 처리가 구현되어 있지 않을 수 있습니다.
- 로그인 기능이 필요한 경우 추가 개발이 필요합니다.

