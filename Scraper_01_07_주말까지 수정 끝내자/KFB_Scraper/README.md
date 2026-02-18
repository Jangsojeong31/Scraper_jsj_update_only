# 은행연합회 스크래퍼

은행연합회의 자율규제 정보를 수집하는 스크래퍼 모음입니다.

## 개요

은행연합회에서 제공하는 다양한 자율규제 정보를 수집합니다.

## 스크래퍼 목록

### 1. kfb_scraper.py - 자율규제 현황

**URL**: https://www.kfb.or.kr/publicdata/reform_info.php

자율규제 정보를 수집합니다 (HWP 파일, 기준일 없음).

**실행 방법:**
```bash
# 프로젝트 루트에서 실행
python3 KFB_Scraper/kfb_scraper.py
```

**옵션:**
- `--limit`: 가져올 개수 제한 (0=전체, 기본값: 0)

### 2. KFB_Notice_Scraper - 자율규제 제정·개정 예고

**URL**: https://www.kfb.or.kr/publicdata/reform_notice.php

자율규제 제정·개정 예고 정보를 수집합니다.

**실행 방법:**
```bash
# 프로젝트 루트에서 실행
python3 KFB_Notice_Scraper/kfb_notice_scraper.py
```

**옵션:**
- `--limit`: 수집할 최대 건수 지정 (기본 0, 전체)
- `--no-download`: 상세 페이지 첨부 파일 다운로드 생략

**출력 파일:**
- `output/kfb_notice.json`
- `output/kfb_notice.csv`

상세한 사용법은 [KFB_Notice_Scraper/README.md](../KFB_Notice_Scraper/README.md)를 참고하세요.

### 3. KFB_Committee_Scraper - 규제심의위원회 결과

**URL**: https://www.kfb.or.kr/publicdata/reform_result.php

규제심의위원회 결과로 의사록 파일 등을 수집합니다.

**실행 방법:**
```bash
# 프로젝트 루트에서 실행
python3 KFB_Committee_Scraper/kfb_committee_scraper.py
```

**옵션:**
- `--limit`: 수집할 최대 건수 지정 (기본 0, 전체)
- `--no-download`: 상세 페이지 첨부 파일 다운로드 생략

**출력 파일:**
- `output/kfb_committee.json`
- `output/kfb_committee.csv`

상세한 사용법은 [KFB_Committee_Scraper/README.md](../KFB_Committee_Scraper/README.md)를 참고하세요.

### 4. KFB_Finlaw_Scraper - 금융관련법규

**URL**: https://www.kfb.or.kr/publicdata/data_finlaw.php

은행연합회 금융관련법규 정보를 수집합니다.

**실행 방법:**
```bash
# 프로젝트 루트에서 실행
python3 KFB_Finlaw_Scraper/kfb_finlaw_scraper.py
```

**옵션:**
- `--limit`: 수집할 최대 건수 지정 (기본 0, 전체)
- `--no-download`: 상세 페이지 첨부 파일 다운로드 생략

**출력 파일:**
- `output/kfb_finlaw.json`
- `output/kfb_finlaw.csv`

상세한 사용법은 [KFB_Finlaw_Scraper/README.md](../KFB_Finlaw_Scraper/README.md)를 참고하세요.

## 수집 정보

- 번호
- 제목
- 상세 링크
- 다운로드 링크
- 첨부파일 (HWP, PDF 등)

## 파일 처리

- HWP 파일 자동 다운로드 및 텍스트 추출
- ZIP 파일 내부 파일 자동 추출
- PDF 파일 텍스트 추출

## 참고사항

- 일부 사이트는 Selenium을 사용하여 JavaScript로 동적 로드되는 페이지를 처리합니다.
- 첨부파일은 `output/downloads/` 디렉토리에 저장됩니다.
- ChromeDriver가 필요합니다.
