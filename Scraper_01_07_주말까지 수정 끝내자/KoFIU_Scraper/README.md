# 금융정보분석원 제재공시 스크래핑 가이드

## 개요
금융정보분석원(KoFIU) 제재공시 페이지([제재공시](https://www.kofiu.go.kr/kor/notification/sanctions.do))를 자동으로 스크래핑하여 PDF를 내려받고 요약 정보를 JSON/CSV로 저장합니다.

## 현재 상태
- **스크랩 대상**: 금융정보분석원 제재공시
- **출력 파일**: `output/kofiu_results.json`, `output/kofiu_results.csv`
- **Archive 파일**: `archive/kofiu_results.json`, `archive/kofiu_results.csv`
- **필드 구성**: 구분(dvcv), 출처(srce), 금융회사명(fnCompNm), 업종(btcd), 제재조치일(snctDt), 제재내용(snctCntn), 파일명(atchFileNm), 제목(tit), 내용(cntn)
- **추가 기능**: 사건제목과 사건내용을 자동으로 추출하여 여러 사건이 있는 경우 행 확장

## 주요 파일

### `kofiu_scraper_v2.py`
- 제재공시 목록 페이지를 순회하며 데이터 수집
- 페이지 끝까지 자동으로 스크래핑
- 상세 페이지에서 PDF 첨부를 찾아 임시 다운로드 후 텍스트 추출 (PDF-OCR 포함)
- OCR 후처리 포함 (스크래퍼 내부에서 처리)
- 사건 추출 (`extract_metadata.py`의 `extract_incidents()` 함수 사용)
- 결과를 `output/kofiu_results.json` / `output/kofiu_results.csv`로 저장

### `extract_metadata.py`
- 제재조치내용(제재공시 문서)에서 사건제목과 사건내용을 추출
- `extract_incidents()`: 4번 항목 또는 재조치 내용 섹션에서 사건 추출
- `extract_metadata_from_content()`: 금융회사명, 제재조치일 추출
- `extract_sanction_details()`: 제재조치내용 추출
- 다양한 문서 패턴 지원 (7가지 타입)

### `post_process_ocr.py`
- OCR 오인식 보정 함수 제공
- `collapse_split_syllables()`: 한글 음절 사이 공백 제거
- `clean_ocr_artifacts()`: OCR 인공물 제거
- `process_ocr_text()`: 전체 OCR 후처리
- 스크래퍼 내부에서 자동으로 호출됨

### `run_pipeline.py`
- 전체 파이프라인 (`kofiu_scraper_v2.py` → archive 병합)을 실행
- `--skip-scrape`, `--stats-only`, `--log-file`, `--sdate`, `--edate`, `--after`, `--no-merge` 옵션 지원

## 실행 방법

```bash
# 전체 파이프라인 실행
python run_pipeline.py

# 기존 스크랩 결과 유지, 추출만 재실행 (skip-scrape 모드에서는 추출 단계가 없으므로 archive 병합만 수행)
python run_pipeline.py --skip-scrape

# 통계만 출력
python run_pipeline.py --stats-only

# 실행 로그를 파일에 저장
python run_pipeline.py --log-file logs/kofiu_pipeline.log

# 검색 기간 지정
python run_pipeline.py --sdate 2025-01-01 --edate 2025-12-31

# 특정 날짜 이후 항목만 수집
python run_pipeline.py --after 2025-11-01

# archive와 병합하지 않고 새 데이터만 저장
python run_pipeline.py --no-merge
```

## 실행 순서

1. **목록 및 PDF 스크래핑** (`kofiu_scraper_v2.py`)
   - 제재공시 목록 페이지 크롤링
   - 상세 페이지에서 PDF 다운로드 및 텍스트 추출
   - OCR 적용 (텍스트 추출 실패 시)
   - OCR 후처리 (스크래퍼 내부에서 자동 처리)
   - 사건 추출 (`extract_metadata.py`의 `extract_incidents()` 사용)
   - 결과를 `output/kofiu_results.json`, `output/kofiu_results.csv`에 저장

2. **Archive 병합** (선택적)
   - 새로 크롤링한 데이터를 `archive/kofiu_results.json`과 병합
   - 중복 제거 (제재조치일 + 금융회사명 기준)
   - 병합된 데이터를 archive에 저장

3. **통계 출력**
   - 사건 추출 현황 통계
   - 업종별 분포 통계

## 내부망(격리망) 환경 준비 사항

외부망이 차단된 환경에서는 아래 항목을 사전 준비해야 합니다.

1. **Python 3.9 이상**: 오프라인 설치 패키지 준비 후 내부망 배포
2. **필수 패키지 wheel**: `requests`, `beautifulsoup4`, `lxml`, `pdfplumber`, `PyPDF2`, `PyMuPDF`, `pytesseract`, `Pillow`, `selenium` 등
3. **Tesseract-OCR + 한글 언어팩**: `tesseract.exe` 및 `kor.traineddata`를 내부망 PC에 설치
4. **ChromeDriver**: Selenium 사용 시 ChromeDriver 필요
5. **폴더 권한**: 임시 다운로드, 로그, 결과 저장을 위한 읽기/쓰기 권한 확보
6. **네트워크 화이트리스트**: `https://www.kofiu.go.kr` 도메인 접근 허용

## 출력 파일

### `output/kofiu_results.json`
- UTF-8 JSON, 전체 원문과 추출 정보를 포함
- 각 항목은 영문 키로 저장됨 (dvcv, srce, fnCompNm, btcd, snctDt, snctCntn, atchFileNm, tit, cntn)
- **사건이 여러 개인 경우 각 사건마다 별도의 항목으로 분리되어 저장됨** (JSON도 CSV와 동일하게 행 확장)
- 예: 하나의 제재건에 3개의 사건이 있으면, JSON에서도 3개의 별도 항목으로 저장됨

### `output/kofiu_results.csv`
- UTF-8-BOM CSV, Excel에서 바로 열 수 있음
- 사건이 여러 개인 경우 각 사건마다 별도의 행으로 확장
- 영문 키 사용 (dvcv, srce, fnCompNm, btcd, snctDt, snctCntn, atchFileNm, tit, cntn)
- JSON과 동일한 구조 (각 사건이 별도 행)

### `archive/kofiu_results.json` / `archive/kofiu_results.csv`
- 병합된 전체 데이터 (새로 크롤링한 데이터 + 기존 archive 데이터)
- 중복 제거된 최종 결과
- 구조는 output 파일과 동일

## 필드 구조

각 항목은 다음 필드를 포함합니다:

```
- dvcv (구분): "제재사례"
- srce (출처): "금융정보분석원"
- fnCompNm (금융회사명): 예) "신한은행", "우리은행"
- btcd (업종): 예) "은행", "보험", "증권", "기타"
- snctDt (제재조치일): "YYYY-MM-DD" 형식
- snctCntn (제재내용): 제재조치내용 요약
- atchFileNm (파일명): PDF 파일명
- tit (제목): 사건제목 (사건이 여러 개인 경우 각 사건이 별도 항목으로 분리됨)
- cntn (내용): 사건내용 (사건이 여러 개인 경우 각 사건이 별도 항목으로 분리됨)
- OCR추출여부: "예" 또는 "아니오"
```

## 사건제목/사건내용 추출

제재조치내용에서 다양한 섹션 제목을 인식하여 사건제목과 사건내용을 자동으로 추출합니다.

**지원하는 섹션 제목 패턴:**
- `4. 제재대상사실` (가장 일반적)
- `4. 조치대상사실`
- `4. 제재조치사유`
- `4. 제재사유`
- `4. 조치사유`
- `4. 위반내용`
- `4. 사유`
- `Ⅲ. 재조치 내용 > 2. 재조치대상사실` (재심 케이스)

**지원하는 사건 추출 패턴:**

**타입 1: 기본 패턴 (가. 나. 다.)**
```
4. 제재대상사실

가. 고객위험평가 관련 절차
   (이 부분이 사건 내용)

나. 고객확인제도 관련 절차
   (이 부분이 사건 내용)
```
→ 각각 별도의 사건으로 추출

**타입 2: 문책사항 패턴 (가. 문책사항 > (1) (2))**
```
4. 제재대상사실

가. 문책사항

(1) 직무 관련 정보의 이용 금지 위반
    (이 부분이 사건 내용)
    
(2) 고객확인제도 위반
    (이 부분이 사건 내용)
```
→ 각 (1), (2)가 별도의 사건으로 추출 (상위 제목 "문책사항"은 접두사로 사용하지 않음)

**타입 3: 통합 사건 모드 (가. 일반제목 > 모든 (1), (2)를 하나로)**
```
4. 제재대상사실

가. 은행 대주주 특수관계인에 대한 신용공여 절차 위반

(1) 이사회 의결 미실시
    (이 부분이 내용)
    
(2) 보고 및 공시 의무 위반
    (이 부분도 같은 사건의 내용)
```
→ 모든 (1), (2)가 하나의 사건 내용으로 통합됨

**타입 4: 중첩 구조 (가. > (1) > (가) (나))**
```
4. 제재대상사실

가. 문책사항

(1) 투자자 보호의무 위반
    (가) 고객 정보 미확인
    (나) 부적합 상품 판매
    
(2) 내부통제 미흡
```
→ (가), (나)는 내용으로 처리, (1), (2)는 각각 별도 사건

**타입 5: 가. 패턴 없이 바로 (1) 시작**
```
4. 제재대상사실

(1) 고객확인의무 위반
    (이 부분이 사건 내용)
    
(2) 거래제한 의무 위반
    (이 부분이 사건 내용)
```
→ 각 (1), (2)가 별도의 사건으로 추출

**타입 6: 사각형/원형 기호 패턴 (가. 패턴이 없을 때)**
```
4. 제재대상사실

□ 고객확인의무 위반
  ◦ 고객 정보 미확인
  ◦ 추가 정보 확인 누락
```
→ "□"로 시작하는 줄은 제목, "◦"로 시작하는 줄은 내용

**타입 7: 재조치 내용 패턴**
```
Ⅲ. 재조치 내용

2. 재조치대상사실

가. 문책사항
(1) 동일인 대출한도 초과 취급
    (이 부분이 사건 내용)
```
→ 재심/재조치 케이스에서 "재조치대상사실" 섹션에서 추출

**상위 제목 지원:**
- 문책사항, 책임사항
- 자율처리 필요사항
- 경영유의, 경영유의사항
- 개선사항
- 주의사항

→ 이 키워드가 포함된 경우 각 (1), (2)를 별도 사건으로 처리하며, 상위 제목은 접두사로 사용하지 않음

**저장 형식:**
- 사건이 여러 개인 경우 **JSON과 CSV 모두에서 각 사건마다 별도의 항목(행)으로 분리**됩니다.
- JSON: 각 사건이 별도의 객체로 저장되며, 각 객체는 `tit`(제목), `cntn`(내용) 필드를 가집니다.
- CSV: 각 사건이 별도의 행으로 저장됩니다.
- 상위 제목이 있는 경우: "상위제목 - 하위제목" 형식으로 저장 (단, 특수 키워드(문책사항, 책임사항 등)는 접두사로 사용하지 않음)

## Archive 기능

`run_pipeline.py`는 새로 크롤링한 데이터를 `archive/kofiu_results.json`과 자동으로 병합합니다.

- **중복 제거 기준**: 제재조치일(snctDt) + 금융회사명(fnCompNm)
- **병합 방식**: 기존 archive 데이터 + 새로 크롤링한 데이터 (중복 제외)
- **출력 위치**: 
  - `output/`: 새로 크롤링한 데이터만 유지
  - `archive/`: 병합된 전체 데이터 저장

`--no-merge` 옵션을 사용하면 archive와 병합하지 않고 새 데이터만 저장합니다.

## 참고

- 금융정보분석원 제재공시: https://www.kofiu.go.kr/kor/notification/sanctions.do
- 야간/비업무 시간대 실행 및 적절한 재시도 간격 유지로 서버 부하를 최소화합니다.
- OCR 추출 시 Tesseract-OCR과 한글 언어팩이 필요합니다.

