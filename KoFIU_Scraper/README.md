# 금융정보분석원 제재공시 스크래핑 가이드

## 개요
금융정보분석원(KoFIU) 제재공시 페이지([제재공시](https://www.kofiu.go.kr/kor/notification/sanctions.do))를 자동으로 스크래핑하여 PDF를 내려받고 요약 정보를 JSON/CSV로 저장합니다.

## 현재 상태
- **스크랩 대상**: 금융정보분석원 제재공시
- **필드 구성**: 번호, 제목, 제재대상기관, 공시일, 문서유형, 상세페이지URL, 제재조치내용, 사건제목, 사건내용
- **추가 기능**: 사건제목과 사건내용을 자동으로 추출하여 여러 사건이 있는 경우 행 확장

## 주요 파일

### `kofiu_scraper.py`
- 제재공시 목록 페이지를 순회하며 데이터 수집
- 페이지 끝까지 자동으로 스크래핑
- 상세 페이지에서 PDF 첨부를 찾아 임시 다운로드 후 텍스트 추출 (PDF-OCR 포함)
- 결과를 `kofiu_results.json` / `kofiu_results.csv`로 저장

### `extract_incidents.py`
- 제재조치내용(제재공시 문서)에서 사건제목과 사건내용을 추출
- 두 가지 타입의 문서 패턴을 처리:
  1. **첫 번째 타입**: "4. 제 재 대 상 사 실\n가. 고객위험평가 관련 절차" → "고객위험평가 관련 절차"가 사건제목
  2. **두 번째 타입**: "4. 제 재 대 상 사 실\n가. 문 책 사 항\n(1) 직무 관련 정보의 이용 금지 위반" → "직무 관련 정보의 이용 금지 위반"이 사건제목
- OCR 오인식을 보정하고, 다양한 패턴을 처리
- 사건이 여러 개인 경우 CSV에서 행 확장

### `run_pipeline.py`
- 전체 파이프라인 (`kofiu_scraper.py` → `extract_incidents.py`)을 실행
- `--skip-scrape`, `--stats-only`, `--log-file` 옵션을 지원

## 실행 방법

```bash
# 전체 파이프라인 실행
python run_pipeline.py

# 기존 스크랩 결과 유지, 추출만 재실행
python run_pipeline.py --skip-scrape

# 통계만 출력
python run_pipeline.py --stats-only

# 실행 로그를 파일에 저장
python run_pipeline.py --log-file logs/kofiu_pipeline.log
```

## 내부망(격리망) 환경 준비 사항

외부망이 차단된 환경에서는 아래 항목을 사전 준비해야 합니다.

1. **Python 3.9 이상**: 오프라인 설치 패키지 준비 후 내부망 배포
2. **필수 패키지 wheel**: `requests`, `beautifulsoup4`, `lxml`, `pdfplumber`, `PyPDF2`, `PyMuPDF`, `pytesseract`, `Pillow` 등
3. **Tesseract-OCR + 한글 언어팩**: `tesseract.exe` 및 `kor.traineddata`를 내부망 PC에 설치
4. **폴더 권한**: 임시 다운로드, 로그, 결과 저장을 위한 읽기/쓰기 권한 확보
5. **네트워크 화이트리스트**: `https://www.kofiu.go.kr` 도메인 접근 허용

## 출력 파일

### `kofiu_results.json`
- UTF-8 JSON, 전체 원문과 추출 정보를 포함
- 각 항목은 `사건목록` 필드에 사건제목과 사건내용 리스트를 포함

### `kofiu_results.csv`
- UTF-8-BOM CSV, Excel에서 바로 열 수 있음
- 사건이 여러 개인 경우 각 사건마다 별도의 행으로 확장
- 주요 필드만 포함

각 항목은 다음 필드를 포함합니다.

```
- 번호
- 제목
- 제재대상기관
- 공시일
- 문서유형
- 상세페이지URL
- 제재조치내용 (전문)
- 사건제목
- 사건내용
```

## 사건제목/사건내용 추출 패턴

### 첫 번째 타입
```
4. 제 재 대 상 사 실

가. 고객위험평가 관련 절차
   (이 부분이 사건 내용)
   
나. 고객확인제도 관련 절차
   (이 부분이 사건 내용)
```

### 두 번째 타입
```
4. 제 재 대 상 사 실

가. 문 책 사 항

(1) 직무 관련 정보의 이용 금지 위반
    (이 부분이 사건 내용)
    
(2) 고객확인제도 위반
    (이 부분이 사건 내용)
```

## 참고

- 금융정보분석원 제재공시: https://www.kofiu.go.kr/kor/notification/sanctions.do
- 야간/비업무 시간대 실행 및 적절한 재시도 간격 유지로 서버 부하를 최소화합니다.

