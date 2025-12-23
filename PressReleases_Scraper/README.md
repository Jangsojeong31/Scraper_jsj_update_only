# 금융감독원 보도자료 스크래퍼 (FSS Press Releases Scraper)

금융감독원 보도자료 목록에서 첨부파일(HWP, HWPX, PDF)을 다운로드하고, 보도일을 자동으로 추출하여 데이터를 수집하는 스크래퍼입니다.

## 📋 목차

- [주요 기능](#주요-기능)
- [시스템 요구사항](#시스템-요구사항)
- [설치 방법](#설치-방법)
- [사용 방법](#사용-방법)
- [출력 파일 설명](#출력-파일-설명)
- [주요 기능 상세](#주요-기능-상세)
- [인수인계 정보](#인수인계-정보)
- [문제 해결](#문제-해결)

---

## 🎯 주요 기능

1. **보도자료 목록 스크래핑**
   - 금융감독원 보도자료 목록 페이지에서 데이터 자동 수집
   - 다중 페이지 처리 지원 (최대 2010페이지)

2. **첨부파일 처리**
   - HWP, HWPX, PDF 파일 다운로드 및 텍스트 추출
   - 별첨파일 자동 제외
   - 여러 첨부파일 중 보도일 추출 시도

3. **보도일 자동 추출**
   - HWP/HWPX 파일에서 보도일 우선 추출
   - 보도일이 없으면 PDF 파일에서 추출 시도
   - 다양한 날짜 형식 자동 인식 및 정규화
   - 키워드 기반 날짜 검색 (보도일, 배포일, 보도시점 등)

4. **데이터 저장**
   - CSV, Excel, JSON 형식으로 저장
   - 중간 저장 기능 (10개 단위)
   - 이어서 진행 기능 (중복 제거)

5. **필터링 및 검증**
   - 2025년 1월 1일 이후 데이터만 수집
   - 보도일이 없는 항목 자동 필터링
   - 문제가 있는 항목 별도 리스트업

---

## 💻 시스템 요구사항

- Python 3.7 이상
- 인터넷 연결 (금융감독원 웹사이트 접근 필요)
- 충분한 디스크 공간 (첨부파일 다운로드 용량 고려)

---

## 📦 설치 방법

### 1. 저장소 클론 또는 디렉토리 이동

```bash
cd PressReleases_Scraper
```

### 2. 가상 환경 생성 (권장)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 설치되는 주요 패키지

- `requests`: HTTP 요청 처리
- `beautifulsoup4`: HTML 파싱
- `pdfplumber`: PDF 파일 텍스트 추출
- `olefile`: HWP 파일 (OLE2 형식) 처리
- `pandas`: 데이터 처리 및 저장
- `openpyxl`: Excel 파일 생성
- `lxml`: XML 파싱 (HWPX 파일용)

---

## 🚀 사용 방법

### 기본 실행

```bash
python scrape_fss_press_releases.py
```

### 실행 과정

1. **기존 데이터 확인**
   - `results.json` 파일이 있으면 기존 데이터 로드
   - 가장 최신 보도일 이후의 데이터만 신규 수집
   - 없으면 처음부터 2025년 1월 1일 이후 데이터 수집

2. **페이지별 스크래핑**
   - 각 페이지에서 보도자료 목록 추출
   - 첨부파일 다운로드 및 텍스트 추출
   - 보도일 추출 시도

3. **자동 중단 조건**
   - 연속으로 5개 이상의 기준일 이전 데이터 발견 시 중단
   - 더 이상 기준일 이후 데이터가 없을 때 중단

4. **중간 저장**
   - 10개 항목마다 자동 저장 (오류 발생 시 데이터 손실 방지)

5. **최종 저장**
   - 전체 데이터: `results.csv`, `results.json`, `results.xlsx`
   - 신규 데이터만: `recent_result.csv`, `recent_result.json`, `recent_result.xlsx`
   - 문제 항목: `problematic_items.csv`, `problematic_items.json`, `problematic_items.xlsx`

---

## 📁 출력 파일 설명

### 전체 데이터 파일

- **`results.csv`**: 전체 보도자료 데이터 (CSV 형식)
- **`results.json`**: 전체 보도자료 데이터 (JSON 형식)
- **`results.xlsx`**: 전체 보도자료 데이터 (Excel 형식)

**데이터 필드:**
- `번호`: 순번
- `제목`: 보도자료 제목
- `보도일`: 추출된 보도일 (YYYY.M.D 형식)
- `상세페이지URL`: 보도자료 상세 페이지 URL
- `첨부파일`: 첨부파일 목록 (파일명과 URL)
- `담당부서`: 담당 부서명
- `내용`: 상세 페이지 본문 내용
- `첨부파일내용 미리보기`: 첨부파일에서 추출한 텍스트 미리보기 (처음 200자)

### 신규 데이터 파일

- **`recent_result.csv`**: 최근 실행에서 신규로 수집된 데이터만 포함
- **`recent_result.json`**: 최근 실행에서 신규로 수집된 데이터만 포함
- **`recent_result.xlsx`**: 최근 실행에서 신규로 수집된 데이터만 포함

### 문제 항목 파일

- **`problematic_items.csv`**: 문제가 있는 항목 목록
- **`problematic_items.json`**: 문제가 있는 항목 목록
- **`problematic_items.xlsx`**: 문제가 있는 항목 목록

**문제 유형:**
- `보도일 없음`: 보도일을 추출하지 못한 항목
- `보도일 파싱 실패`: 보도일은 찾았지만 날짜 형식을 인식하지 못한 항목
- `보도일이 2025년 이전`: 2025년 1월 1일 이전의 보도일을 가진 항목

---

## 🔍 주요 기능 상세

### 1. 보도일 추출 로직

스크래퍼는 다음 순서로 보도일을 추출합니다:

1. **복합 패턴 처리**
   - "보 도", "보도시점은 배포시", "보도가 배포 시" 등의 특수 패턴 처리

2. **보도일 키워드 검색** (우선순위 1)
   - 키워드: 보도시점, 보도일, 보도 시, 보 도 등
   - 키워드 주변 150자 내에서 날짜 패턴 검색

3. **배포일 키워드 검색** (우선순위 2)
   - 보도일을 찾지 못한 경우만 시도
   - 키워드: 배포시, 배포일, 배포 등

4. **전체 텍스트 검색** (우선순위 3)
   - 키워드 주변에서 못 찾은 경우 전체 텍스트에서 첫 번째 날짜 추출

### 2. 날짜 형식 인식

다음과 같은 다양한 날짜 형식을 자동 인식합니다:

- `2025년 1월 1일`
- `2025.1.1`, `2025. 1. 1`
- `2025-01-01`
- `2025/01/01`
- `20250101` (8자리)
- `25010101` (10자리, 앞 2자리 년도)
- `'25.1.1` (2자리 년도, 자동으로 2000년대 또는 1900년대로 변환)

### 3. 파일 형식별 처리

#### HWP 파일 (OLE2 형식)
- `olefile` 라이브러리 사용
- `PrvText`, `BodyText/Section0` 등의 스트림에서 텍스트 추출
- UTF-16-LE 인코딩 사용

#### HWPX 파일 (ZIP 기반 XML)
- `zipfile` 라이브러리로 압축 해제
- `Contents/section0.xml`, `Contents/section1.xml` 등에서 XML 파싱
- XML 요소에서 텍스트 추출

#### PDF 파일
- `pdfplumber` 라이브러리 사용
- 각 페이지에서 텍스트 추출
- 설치되지 않은 경우 PDF 처리 제한

### 4. 중복 제거 및 이어서 진행

- **중복 확인 기준**: 상세페이지URL
- **기준일 설정**: 기존 데이터에서 가장 최신 보도일 사용
- **자동 이어서 진행**: 같은 날짜 이후의 데이터만 수집하여 중복 방지

### 5. 자동 중단 로직

다음 경우에 자동으로 스크래핑을 중단합니다:

1. 연속으로 5개 이상의 기준일 이전 데이터 발견
2. 페이지에 테이블이 없거나 데이터가 없음
3. 다음 페이지를 찾을 수 없음

---

## 📖 인수인계 정보

### 코드 구조

```
scrape_fss_press_releases.py
├── 텍스트 추출 함수
│   ├── extract_text_from_hwp_bytes()      # HWP 파일 텍스트 추출
│   ├── extract_text_from_hwpx_bytes()     # HWPX 파일 텍스트 추출
│   └── extract_text_from_pdf_bytes()      # PDF 파일 텍스트 추출
├── 날짜 처리 함수
│   ├── extract_first_date()               # 보도일 추출 (메인 로직)
│   ├── extract_date_near_keyword()        # 키워드 주변 날짜 검색
│   ├── normalize_year_format()            # 년도 형식 정규화
│   ├── add_year_if_missing()              # 년도 추가
│   └── parse_date_string()                # 날짜 문자열 파싱
├── 스크래핑 함수
│   ├── scrape_single_page()               # 단일 페이지 처리
│   ├── scrape_press_releases()            # 전체 스크래핑 메인 함수
│   └── has_next_page()                    # 다음 페이지 확인
└── 유틸리티 함수
    ├── load_existing_data()               # 기존 데이터 로드
    ├── save_results()                     # 결과 저장
    └── list_problematic_items()           # 문제 항목 필터링
```

### 주요 설정값

**`main()` 함수 내:**

```python
base_url = "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218&pageIndex=1"
total_pages = 2010  # 최대 페이지 수 (안전장치)
resume = True        # 이어서 진행 여부
```

**`scrape_press_releases()` 함수 내:**

```python
save_interval = 10   # 중간 저장 간격 (항목 개수)
cutoff_date = datetime(2025, 1, 1)  # 기본 기준일
```

**`scrape_single_page()` 함수 내:**

```python
consecutive_old_count >= 5  # 연속된 오래된 데이터 개수 (중단 조건)
```

### 수정이 필요한 경우

#### 1. 기준일 변경

`scrape_press_releases()` 함수에서 `default_cutoff_date` 수정:

```python
default_cutoff_date = datetime(2025, 1, 1)  # 원하는 날짜로 변경
```

#### 2. 중간 저장 간격 변경

`scrape_press_releases()` 함수에서 `save_interval` 수정:

```python
save_interval = 10  # 원하는 간격으로 변경
```

#### 3. 자동 중단 조건 변경

`scrape_single_page()` 함수에서 `consecutive_old_count` 조건 수정:

```python
if consecutive_old_count >= 5:  # 원하는 개수로 변경
```

#### 4. 대상 URL 변경

`main()` 함수에서 `base_url` 수정:

```python
base_url = "원하는_URL"
```

### 웹사이트 구조 변경 시 대응

#### 테이블 구조 변경

`scrape_single_page()` 함수의 테이블 선택 부분 수정:

```python
table = soup.find('table', class_='board_list') or soup.find('table')
```

#### 상세 페이지 구조 변경

`scrape_single_page()` 함수의 본문 추출 부분 수정:

```python
content_div = detail_soup.find('div', class_='dbdata')
```

#### 페이지네이션 구조 변경

`has_next_page()` 함수에서 다음 페이지 확인 로직 수정

---

## ⚠️ 문제 해결

### 1. PDF 파일 처리가 안 되는 경우

**증상**: `⚠️ pdfplumber가 설치되지 않았습니다. PDF 파일 처리가 제한됩니다.`

**해결**:
```bash
pip install pdfplumber
```

### 2. 보도일 추출이 안 되는 경우

**원인**:
- 파일 형식이 지원하지 않는 형식일 수 있음
- 날짜 형식이 인식되지 않는 특수한 형식일 수 있음
- 파일이 손상되었을 수 있음

**대응**:
1. `problematic_items.json` 파일 확인
2. 해당 파일을 직접 열어서 보도일 확인
3. 필요시 `extract_first_date()` 함수의 날짜 패턴 추가

### 3. 스크래핑이 너무 느린 경우

**원인**:
- 네트워크 지연
- 많은 첨부파일 다운로드
- 서버 응답 지연

**대응**:
- `time.sleep()` 값 조정 (현재 0.5초~1초)
- 중간 저장 간격을 줄여서 진행 상황 확인

### 4. 메모리 부족 오류

**원인**:
- 큰 첨부파일 다운로드
- 많은 데이터 메모리 적재

**대응**:
- 중간 저장 간격을 더 자주 실행
- 배치 처리로 나눠서 실행

### 5. 중복 데이터가 저장되는 경우

**원인**:
- 상세페이지URL이 변경되었을 수 있음
- 수동으로 `results.json`을 삭제했을 수 있음

**대응**:
- `results.json` 파일 백업 후 삭제
- 처음부터 다시 스크래핑

### 6. 특정 날짜 이후 데이터만 필요한 경우

**해결 방법**:

1. **코드 수정 방법**:
   ```python
   # scrape_press_releases() 함수 내
   default_cutoff_date = datetime(2025, 3, 1)  # 원하는 날짜로 변경
   ```

2. **필터링 방법** (스크래핑 후):
   - Excel/CSV 파일에서 필터링
   - Python 스크립트로 JSON 필터링

---

## 📝 주의사항

1. **과도한 요청 방지**
   - 스크래퍼는 요청 간 대기 시간을 두고 있습니다 (0.5초~1초)
   - 이 값은 서버 부하를 고려하여 설정되었습니다

2. **데이터 백업**
   - 중요한 실행 전에 `results.json` 파일을 백업하세요
   - 중간 저장 파일들이 생성되므로 정기적으로 정리하세요

3. **네트워크 안정성**
   - 장시간 실행되므로 안정적인 네트워크 연결이 필요합니다
   - 중간에 오류가 발생하면 자동으로 저장된 데이터까지는 보존됩니다

4. **첨부파일 용량**
   - 첨부파일 URL만 저장하고 파일 자체는 저장하지 않습니다
   - 다만 다운로드 과정에서 일시적으로 메모리를 사용합니다

---

## 🔄 업데이트 이력

- **2025년 1월**: 초기 버전
  - HWP, HWPX, PDF 파일 지원
  - 보도일 자동 추출
  - 중복 제거 및 이어서 진행 기능
  - 문제 항목 필터링 기능

---

## 📧 문의 및 지원

코드 수정이나 문제 발생 시:
1. `problematic_items.json` 파일 확인
2. 콘솔 출력 로그 확인
3. 코드 내 주석 참고

---

## 📄 라이선스

이 프로젝트는 내부 사용 목적으로 개발되었습니다.

