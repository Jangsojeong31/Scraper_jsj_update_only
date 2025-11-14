# 금융회사 경영유의사항 등 공시 스크래핑 가이드

## 개요
금융감독원 경영유의사항·개선권고 등 공시 페이지([openInfoImpr](https://www.fss.or.kr/fss/job/openInfoImpr/list.do?menuNo=200483))를 자동으로 스크래핑하여 PDF를 내려받고 요약 정보를 JSON/CSV로 저장합니다.

## 현재 상태
- **스크랩 대상**: 경영유의사항/개선권고 등 공시
- **필드 구성**: 번호, 제재대상기관, 제재조치요구일, 관련부서, 문서유형, 상세페이지URL, 제재조치내용
- **추가 필드**: 조회수가 제공되지 않아 CSV/JSON에서는 `"-"`로 고정합니다.

## 주요 파일

### `fss_scraper.py`
- `openInfoImpr` 목록 페이지를 순회하며 데이터 수집
- 상세 페이지에서 PDF 첨부를 찾아 임시 다운로드 후 텍스트 추출 (PDF-OCR 포함)
- 결과를 `fss_results.json` / `fss_results.csv`로 저장

### `extract_sanctions.py`
- 제재조치내용(경영유의사항 문서)에서 테이블 구조를 인식해 제재대상·제재내용을 추출
- OCR 오인식을 보정하고, 다양한 패턴을 처리

### `post_process_ocr.py`
- OCR 후처리 및 품질 검증 자동화
- 반복적으로 발생하는 OCR 인공물 제거 및 결과 저장

### `run_pipeline.py`
- 전체 파이프라인 (`fss_scraper.py` → `extract_sanctions.py` → `post_process_ocr.py`)을 실행
- `--skip-scrape`, `--skip-ocr-retry`, `--stats-only`, `--log-file` 옵션을 지원

## 실행 방법

```bash
# 전체 파이프라인 실행
python run_pipeline.py

# 기존 스크랩 결과 유지, 추출만 재실행
python run_pipeline.py --skip-scrape

# 통계만 출력
python run_pipeline.py --stats-only

# 실행 로그를 파일에 저장
python run_pipeline.py --log-file logs/impr_pipeline.log
```

## 내부망(격리망) 환경 준비 사항

외부망이 차단된 환경에서는 아래 항목을 사전 준비해야 합니다.

1. **Python 3.9 이상**: 오프라인 설치 패키지 준비 후 내부망 배포
2. **필수 패키지 wheel**: `requests`, `beautifulsoup4`, `lxml`, `pdfplumber`, `PyPDF2`, `PyMuPDF`, `pytesseract`, `Pillow` 등
3. **Tesseract-OCR + 한글 언어팩**: `tesseract.exe` 및 `kor.traineddata`를 내부망 PC에 설치
4. **폴더 권한**: 임시 다운로드, 로그, 결과 저장을 위한 읽기/쓰기 권한 확보
5. **네트워크 화이트리스트**: `https://www.fss.or.kr` 도메인 접근 허용

## 출력 파일

- `fss_results.json`: UTF-8 JSON, 전체 원문과 추출 정보를 포함
- `fss_results.csv`: UTF-8-BOM CSV, Excel에서 바로 열 수 있음

각 항목은 다음 필드를 포함합니다.

```
- 번호
- 제재대상기관
- 제재조치요구일
- 관련부서
- 조회수 (항상 "-")
- 문서유형
- 상세페이지URL
- 제재조치내용 (전문)
- 제재대상
- 제재내용
```

## 참고

- 금융감독원 경영유의사항 공시: https://www.fss.or.kr/fss/job/openInfoImpr/list.do?menuNo=200483
- 야간/비업무 시간대 실행 및 적절한 재시도 간격 유지로 서버 부하를 최소화합니다.

