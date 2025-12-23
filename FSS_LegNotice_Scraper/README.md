# 금융감독원 업무자료>금융감독법규정보>금융감독법규정보>세칙 제·개정 예고 스크래퍼

금융감독원 업무자료>금융감독법규정보>금융감독법규정보>세칙 제·개정 예고 정보를 수집하는 스크래퍼입니다.

## 개요

**URL**: https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489

금융감독원에서 공개하는 세칙 제·개정 예고 정보를 수집합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 실행
python3 FSS_Notice_ERB_Scraper/fss_notice_erb_scraper.py

# 또는 FSS_Notice_Ber_Scraper 디렉토리에서 실행
cd FSS_Notice_ERB_Scraper
python3 fss_notice_erb_scraper.py
```

## 옵션

- `--limit`: 수집할 최대 건수 지정 (기본 0, 전체)
- `--no-download`: 상세 페이지 첨부 파일 다운로드 생략

## 출력 파일

- `output/fss_notice_erb.json`: JSON 형식 결과
- `output/fss_notice_erb.csv`: CSV 형식 결과

## 수집 정보

- 번호
- 제목
- 개정일
- 첨부파일
- 첨부파일 정보
- 첨부파일 다운로드 (HWP, EXCEL 등)
- 의견&회신

## 참고사항

- Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리합니다.
- 첨부파일은 `output/downloads/` 디렉토리에 저장됩니다.
- ChromeDriver가 필요합니다.

