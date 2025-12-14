# FSS_ManagementNotices_Scraper 파일 구조 및 기능 설명

## 현재 파일별 기능

### 1. `run_pipeline.py` - 파이프라인 실행 스크립트
**역할**: 전체 크롤링 및 처리 파이프라인을 순차적으로 실행
- 단계 1: `fss_scraper_v2.py` 실행 (목록 및 PDF 스크래핑)
- 단계 2: `extract_sanctions_v2.py` 실행 (제재내용 보완 및 OCR 후처리)
- 단계 3: `ocr_failed_items.py` 실행 (OCR 실패 항목 재처리, 조건부)

---

### 2. `fss_scraper_v2.py` - 메인 크롤링 스크립트
**역할**: 웹 스크래핑, PDF 다운로드, 텍스트 추출, OCR 처리

**현재 포함된 기능들**:
1. **웹 스크래핑**: 목록 페이지에서 공시 정보 수집
2. **PDF 다운로드**: `FileExtractor.download_file()` 사용
3. **PDF 텍스트 추출**: `FileExtractor.extract_pdf_content()` 사용
   - pdfplumber 우선 시도
   - 실패 시 PyPDF2 시도
4. **OCR 처리** (현재 이 파일에 포함됨):
   - `_initialize_ocr()`: Tesseract OCR 초기화
   - `_ocr_pdf()`: PDF를 이미지로 변환 후 OCR 수행
   - PDF 추출 실패 또는 텍스트가 너무 짧을 때 OCR 시도
5. **메타데이터 추출**: 금융회사명, 제재조치일, 제재내용, 사건 제목/내용
   - OCR 추출 시: `extract_metadata_ocr.py` 함수 사용
   - 일반 추출 시: `extract_metadata.py` 함수 사용
6. **결과 저장**: JSON/CSV 파일로 저장

**문제점**: 
- OCR 로직이 크롤링 스크립트에 직접 포함되어 있음 (기능 분리 안 됨)
- FileExtractor는 PDF 추출만 하고, OCR은 별도로 처리됨

---

### 3. `extract_sanctions_v2.py` - 제재내용 보완 및 OCR 후처리
**역할**: 이미 추출된 데이터를 보완하고 OCR 오류를 수정

**기능**:
1. **제재내용 보완**: `fss_scraper_v2.py`에서 추출 실패한 제재내용 재추출 시도
2. **OCR 후처리**: OCR로 추출된 텍스트의 오류 수정
   - `collapse_split_syllables()`: 한글 음절 사이의 불필요한 공백 제거
   - OCR 추출 여부(`OCR추출여부 == '예'`)를 확인하여 조건부 적용
3. **누락필드 계산**: 제재내용, 제목, 내용이 누락된 경우 표시
4. **CSV 재생성**: 보완된 데이터로 CSV 파일 재생성

**문제점**:
- OCR 후처리 로직이 여기에 포함되어 있지만, `post_process_ocr.py`와 중복될 수 있음

---

### 4. `post_process_ocr.py` - OCR 후처리 (래퍼)
**역할**: `FSS_Sanctions_Scraper/post_process_ocr.py`를 호출하는 래퍼 스크립트

**현재 상태**: 단순히 다른 폴더의 스크립트를 실행만 함

**문제점**:
- ManagementNotices 전용 로직이 없음
- FSS_Sanctions_Scraper의 로직을 그대로 사용

---

### 5. `ocr_failed_items.py` - OCR 실패 항목 재처리 (래퍼)
**역할**: `FSS_Sanctions_Scraper/ocr_failed_items.py`를 호출하는 래퍼 스크립트

**현재 상태**: 단순히 다른 폴더의 스크립트를 실행만 함

**문제점**:
- ManagementNotices 전용 로직이 없음
- FSS_Sanctions_Scraper의 로직을 그대로 사용

---

## 현재 크롤링 순서 (사용자 요구사항)

1. **PDF 파일 추출**: `FileExtractor` 사용
   - 위치: `fss_scraper_v2.py`의 `extract_attachment_content()` 메서드
   - `FileExtractor.extract_pdf_content()` 호출
   - pdfplumber → PyPDF2 순서로 시도

2. **PDF 추출 실패 시 OCR 추출**
   - 위치: `fss_scraper_v2.py`의 `extract_attachment_content()` 메서드
   - `_ocr_pdf()` 메서드 호출
   - PyMuPDF로 PDF를 이미지로 변환
   - Tesseract OCR로 텍스트 추출

3. **OCR 추출 시 후처리**
   - 위치: `extract_sanctions_v2.py`
   - `collapse_split_syllables()` 함수로 OCR 오류 수정
   - OCR 추출 여부를 확인하여 조건부 적용

---

## 기능 분리 문제점

### 문제 1: OCR 로직이 크롤링 스크립트에 포함됨
- `fss_scraper_v2.py`에 `_initialize_ocr()`, `_ocr_pdf()` 메서드가 직접 포함
- FileExtractor는 PDF 추출만 하고, OCR은 별도 처리
- **개선 방안**: OCR 로직을 별도 모듈로 분리

### 문제 2: OCR 후처리가 여러 곳에 분산됨
- `extract_sanctions_v2.py`에 OCR 후처리 로직 포함
- `post_process_ocr.py`도 OCR 후처리 수행 (래퍼지만)
- **개선 방안**: OCR 후처리 로직을 한 곳으로 통합

### 문제 3: FileExtractor와 OCR의 역할 분리 불명확
- FileExtractor: PDF 텍스트 추출만 (pdfplumber, PyPDF2)
- OCR: FileExtractor 실패 시 별도 처리
- **개선 방안**: FileExtractor에 OCR 폴백 기능 추가 또는 별도 OCR 모듈 생성

---

## 권장 개선 방안

### 옵션 1: FileExtractor에 OCR 폴백 추가
```
FileExtractor.extract_pdf_content()
  → pdfplumber 시도
  → 실패 시 PyPDF2 시도
  → 실패 시 OCR 시도 (내부에서 처리)
```

### 옵션 2: 별도 OCR 모듈 생성
```
common/ocr_extractor.py
  - OCR 초기화
  - PDF → 이미지 변환
  - Tesseract OCR 수행
```

### 옵션 3: 현재 구조 유지하되 역할 명확화
- `fss_scraper_v2.py`: 크롤링 + PDF 추출 + OCR (현재 구조 유지)
- `extract_sanctions_v2.py`: 데이터 보완 + OCR 후처리
- `post_process_ocr.py`: 추가 OCR 후처리 (선택적)

