# 금융감독원 제재조치 스크래핑 가이드

## 개요
금융감독원 제재조치 공개 정보를 자동으로 스크래핑하여 JSON 및 CSV 파일로 저장하는 프로젝트입니다.

## 현재 상태
- **전체 항목**: 260개
- **성공률**: 100% (일반 제재/재심/제재대상 없음 전체 성공)
- **문서유형 구분**: PDF-텍스트 / PDF-OCR / 기타 / 첨부없음 / URL없음 / 오류

## 주요 파일

### 1. `fss_scraper.py`
- 기본 스크래핑 스크립트
- 모든 페이지를 순회하며 데이터 수집
- PDF 다운로드 및 텍스트 추출 (OCR 포함)
- 결과를 JSON 및 CSV로 저장

### 2. `extract_sanctions.py`
- 제재조치내용에서 제재대상과 제재내용 추출
- 다양한 문서 패턴 인식 (일반, OCR, 재심 등)
- OCR 결과에서 한글 음절 사이가 공백으로 분절된 문자열을 자동으로 결합
- `"오 혐 설 계 사" → "보험설계사"`, `"견 무 정 지" → "업무정지"` 등 반복되는 오인식을 표준화
- 추출된 데이터로 JSON/CSV 업데이트

### 3. `post_process_ocr.py`
- OCR 후처리 및 품질 검증 스크립트
- `extract_sanctions.py`에서 자동으로 호출됨
- OCR 인공물 제거, 알려진 문제 자동 수정
- 문서유형(`문서유형` 필드) 업데이트 및 품질 검증 리포트 출력

### 4. `ocr_failed_items.py`
- OCR 실패 항목 재처리 스크립트 (필요시 수동 실행)
- Tesseract-OCR 한글 언어팩 사용 (`-l kor`)
- 이미지 기반 PDF 처리

### 5. `run_pipeline.py`
- 전체 파이프라인 자동 실행 스크립트
- 순서대로 `fss_scraper.py` → `extract_sanctions.py` (내부에서 `post_process_ocr.py` 자동 호출) → `ocr_failed_items.py`를 실행
- 실행 후 `fss_results.json`을 기반으로 제재대상/제재내용 추출 통계를 출력
- 주요 옵션
  - `--skip-scrape`: 기존 스크래핑 결과를 유지하고 추출 단계부터 실행
  - `--skip-ocr-retry`: `ocr_failed_items.py` 실행 생략
  - `--stats-only`: 현존하는 결과 파일에 대한 통계만 출력 (스크립트 실행 없음)

## 신규 항목 (257번 이후) 스크래핑 방법

### 자동 스크래핑 (권장)

```bash
# 전체 파이프라인 실행 + 통계 출력
python run_pipeline.py

# 기존 스크래핑 결과로 패턴 추출만 다시 실행하고 싶을 때
python run_pipeline.py --skip-scrape

# 통계만 확인하고 싶을 때
python run_pipeline.py --stats-only

# 실행 로그를 파일에 남기고 싶을 때
python run_pipeline.py --log-file logs/pipeline.log
```

## 내부망(격리망) 환경에서의 준비 사항

외부망이 차단된 환경에서 본 스크립트를 운용할 때는 아래 항목을 사전에 준비해주세요. 단, 금융감독원 제재조치 사이트(`https://www.fss.or.kr`)에 대한 접근만 허용되어 있다고 가정합니다.

1. **Python 런타임**
   - 버전: Python 3.9 이상 권장 (현재 개발은 3.11 기준)
   - 오프라인 설치 파일을 미리 다운로드 후 내부망에 배포하거나, 이미 설치된 레퍼런스를 활용합니다.

2. **필수 패키지 (오프라인 설치 용도)**
   - `requests`, `beautifulsoup4`, `lxml`
   - `pdfplumber`, `PyPDF2`
   - `PyMuPDF`(모듈명 `fitz`), `pytesseract`, `Pillow`
   - 오프라인 환경에서는 위 패키지의 wheel 파일(`*.whl`)을 미리 받아두고, 내부망에서 `pip install --no-index --find-links <wheel_디렉토리>` 방식으로 설치합니다.
   - 다른 내부 자동화 스크립트를 별도로 운용할 계획이라면, 해당 도구가 요구하는 의존성도 오프라인으로 함께 준비해 주세요.

3. **Tesseract-OCR (한글 언어 지원)**
   - 내부망 PC에 Tesseract 실행파일을 설치합니다. (예: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
   - 한글 언어팩(`kor.traineddata`)을 해당 설치 경로의 `tessdata` 디렉토리에 복사합니다.
   - 경로가 표준 위치가 아닐 경우, `extract_sanctions.py`에서 Tesseract 경로를 수정하거나, `pytesseract.pytesseract.tesseract_cmd` 를 환경에 맞게 설정해줍니다.

4. **PDF 처리 관련 라이브러리**
   - `PyPDF2`, `pdfplumber`, `PyMuPDF`은 네트워크가 없어도 PDF 텍스트 추출에 활용됩니다. 오프라인 설치만 해두면 추가적인 인터넷 접근이 필요 없습니다.

5. **스크립트 실행 계정과 권한**
   - 스크립트가 실행될 위치에 대해 읽기/쓰기 권한이 필요합니다. (PDF 임시 저장, JSON/CSV 결과 저장 등)
   - 로그 파일을 별도 디렉터리에 저장할 경우 그 위치에 대한 접근권한도 확인해 주세요.

6. **네트워크 화이트리스트 확인**
   - 금융감독원 제재조치 공개 사이트(`https://www.fss.or.kr/fss/job/openInfo/...`)에 대한 접근이 가능한지 보안팀과 협의합니다.
   - 추가로 PDF 다운로드를 위해 사용하는 `download` 경로 역시 금융감독원 도메인을 사용하므로 동일하게 허용되어야 합니다.

7. **배포 / 업데이트 전략**
   - 내부망으로 코드 업데이트가 어려운 경우, Git 리포지토리의 패키징 버전을 주기적으로 외부에서 받아 USB 등으로 반입합니다.
   - 새로운 패턴 대응 코드를 도입할 때는 해당 모듈(`extract_sanctions.py`)과 테스트 데이터(JSON) 등을 함께 반입하여 검증합니다.

8. **옵션 기반 실행**
   - 크론/작업 스케줄러를 사용할 경우, 외부 접근이 차단된 환경에서도 `python run_pipeline.py --log-file logs/pipeline.log` 방식으로 실행 로그를 남길 수 있습니다.
   - 네트워크 부하를 최소화하기 위해 야간이나 업무 외 시간에 실행하는 것을 권장합니다.

**자동 처리 과정:**
1. `fss_scraper.py`: 전체 페이지 스크래핑, PDF 다운로드 및 텍스트 추출 (OCR 포함)
2. `extract_sanctions.py`: 제재대상/제재내용 추출 (패턴 인식)
3. `post_process_ocr.py` (자동 실행): OCR 오류 자동 수정 및 품질 검증
4. `ocr_failed_items.py` (선택): 이미지 PDF 등 추가 재처리
5. `run_pipeline.py`: 위 단계를 순서대로 실행하고 추출 성공률 통계를 출력

### 방법 2: URL 수정하여 특정 기간만 스크래핑

`fss_scraper.py` 파일에서 `base_url` 수정:

```python
# 예: 2025년 1월 1일부터 오늘까지
base_url = "https://www.fss.or.kr/fss/job/openInfo/list.do?menuNo=200476&pageIndex={page}&sdate=2025-01-01&edate=2025-12-31&searchCnd=4&searchWrd="
```

## 지원하는 문서 패턴

### 1. 일반 제재 문서
```
3. 제재조치내용
제재대상 제재내용
기관     과태료 18백만원
임원     주의 1명
직원     견책 1명
```

### 2. OCR 텍스트 (공백 포함)
```
3. 제 재 조 치 내 용
제 재 대상   제 재 내 용
기 관       기 관 주 의
직 원       주 의 1 명
```

### 3. 조치내용 변형
```
3. 조치내용
대상    내용
기관    과태료
직원    자율처리필요사항 1건
```

### 4. 재심 케이스
```
Ⅰ. 재심 취지
...
Ⅲ. 재조치 내용
...
```
→ 제재대상: "재심", 제재내용: "재조치 내용 참조"

### 5. 제재대상 없음
```
3. 제재조치내용
- -
(*) 퇴직자 위법사실 통지 제외
```
→ 제재대상: "-", 제재내용: "-"

## 처리 가능한 특수 패턴

### OCR 오인식 정규화
- "로 혐 설 계 사" → "보험설계사"
- "기 관" (공백 있음) → "기관"
- 파이프(|) 구분자 처리

### 다양한 제재대상
- 기관, 임원, 직원, 직원등
- 보험설계사, 보험대리점, 보험중개사
- 개인사업자 (甲, 乙 등 한자 표기)

### 복합 패턴
- 여러 줄에 걸친 제재대상/제재내용
- 제재대상이 중간에 나타나는 경우
- 표 형식이 아닌 서술형

## 필수 요구사항

### Python 패키지
```bash
pip install requests beautifulsoup4 lxml pdfplumber PyPDF2 PyMuPDF pytesseract Pillow
```

### Tesseract-OCR 설치
1. [Tesseract-OCR 다운로드](https://github.com/UB-Mannheim/tesseract/wiki)
2. 설치 시 "Additional language data" > "Korean" 선택
3. 또는 수동으로 `kor.traineddata` 파일을 `C:\Program Files\Tesseract-OCR\tessdata\`에 복사

## 성능 최적화

### OCR 성능 개선
- **해상도**: 300-400 DPI 권장
- **PSM 모드**: 
  - `--psm 6`: 단일 텍스트 블록 (일반 문서)
  - `--psm 4`: 단일 컬럼 (표 형식)
- **한글 언어팩**: `-l kor` 필수

### 처리 속도
- 평균: 약 5-10초/항목
- 총 256개 처리: 약 20-40분
- 서버 부하 방지를 위해 각 요청 사이 1초 대기

## 출력 파일

### `fss_results.json`
- UTF-8 인코딩
- 전체 제재조치내용 포함
- 프로그래밍 용도에 최적

### `fss_results.csv`
- UTF-8-BOM 인코딩 (Excel 한글 호환)
- 주요 필드만 포함
- 엑셀에서 바로 열기 가능

### 필드 구조
```
- 번호
- 제재대상기관
- 제재조치요구일
- 관련부서
- 조회수
- 상세페이지URL
- 제재대상
- 제재내용
- 제재조치내용 (전문)
- 사건제목 (CSV에서 사건이 여러 개인 경우 행 확장)
- 사건내용 (CSV에서 사건이 여러 개인 경우 행 확장)
```

### 사건제목/사건내용 추출

제재조치내용에서 "4. 제재대상사실" 섹션의 사건제목과 사건내용을 자동으로 추출합니다.

**첫 번째 타입:**
```
4. 제 재 대 상 사 실

가. 고객위험평가 관련 절차
   (이 부분이 사건 내용)
```

**두 번째 타입:**
```
4. 제 재 대 상 사 실

가. 문 책 사 항

(1) 직무 관련 정보의 이용 금지 위반
    (이 부분이 사건 내용)
```

- 사건이 여러 개인 경우 CSV에서 각 사건마다 별도의 행으로 확장됩니다.
- JSON에서는 각 항목의 `사건목록` 필드에 배열로 저장됩니다.

## 문제 해결

### OCR 오류
```bash
# 1. Tesseract 설치 확인
tesseract --version

# 2. 한글 언어팩 확인
tesseract --list-langs

# 3. OCR 실패 항목 재처리
python ocr_failed_items.py
```

### 인코딩 오류
- Windows: `sys.stdout.reconfigure(encoding='utf-8')`
- CSV: `encoding='utf-8-sig'` 사용 (BOM 포함)

### 패턴 인식 실패
1. `extract_sanctions.py`에 새로운 패턴 추가
2. 정규표현식 수정
3. 테스트 후 전체 재실행

## 유지보수 체크리스트

### 신규 항목 추가 시
- [ ] `fss_scraper.py` 실행
- [ ] `extract_sanctions.py` 실행
- [ ] 결과 CSV 파일 확인
- [ ] 특이 케이스 수동 검토

### 패턴 업데이트 시
- [ ] 새로운 패턴 확인
- [ ] `extract_sanctions.py`에 패턴 추가
- [ ] 테스트 항목으로 검증
- [ ] 전체 데이터 재추출

## 참고사항

### 금융감독원 웹사이트
- URL: https://www.fss.or.kr/fss/job/openInfo/list.do
- 메뉴: 업무안내 > 공시 > 제재조치내용 공개

### 데이터 업데이트 주기
- 금융감독원은 부정기적으로 제재조치를 공개
- 주기적으로 스크래핑하여 신규 항목 확인 필요

---

## 완료 체크

- [x] 260개 항목 스크래핑 및 후처리 완료 (100%)
- [x] 일반 제재 패턴 인식
- [x] OCR 텍스트 처리
- [x] 재심 케이스 처리
- [x] 제재대상 없음 처리
- [x] JSON/CSV 출력
- [x] 한글 인코딩 최적화

**모든 패턴이 구현되어 257번 이후 신규 항목도 자동 처리 가능합니다!**

