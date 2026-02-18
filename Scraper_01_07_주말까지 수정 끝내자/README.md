# 금융 관련 정보 스크래퍼 통합 프로젝트

금융감독원 및 기타 금융 관련 기관의 공시 정보를 자동으로 수집하는 통합 스크래퍼 프로젝트입니다.

## 📋 프로젝트 구조

### FSS (금융감독원) 스크래퍼
- **FSS_Sanctions_Scraper**: 제재조치 공개 정보 스크래핑
- **FSS_ManagementNotices_Scraper**: 경영유의사항·개선권고 등 공시 스크래핑
- **InspectionManual_Scraper**: 검사업무 메뉴얼 스크래핑

### 기타 금융 기관 스크래퍼
- **Law_Scraper**: 법제처 - 국가법령정보센터 스크래퍼
- **KFB_Scraper**: 은행연합회 스크래퍼 (자율규제, 제정·개정 예고, 규제심의위원회, 법규정보)
- **KOFIA_Scraper**: 금융투자협회 - 법규정보시스템 스크래퍼
- **CREFIA_Scraper**: 여신금융협회 스크래퍼
- **BOK_Scraper**: 한국은행 스크래퍼
- **FSB_Scraper**: 저축은행중앙회 스크래퍼
- **KRX_Scraper**: 한국거래소 스크래퍼

각 스크래퍼 디렉토리에는 상세한 사용법이 담긴 `README.md`가 포함되어 있습니다.

### 공통 모듈
- **common/**: 모든 스크래퍼가 공유하는 기본 클래스 및 유틸리티
  - `base_scraper.py`: BaseScraper 기본 클래스
  - `file_extractor.py`: 파일 다운로드 및 추출 (PDF, HWP, ZIP)

## 🚀 설치 방법

### 1. 필수 패키지 설치

```bash
pip3 install -r requirements.txt
```

### 2. Tesseract-OCR 설치 (FSS 스크래퍼 OCR 기능 사용 시)

**macOS:**
```bash
brew install tesseract
brew install tesseract-lang  # 한글 언어팩
```

**Windows:**
- [Tesseract-OCR 다운로드](https://github.com/UB-Mannheim/tesseract/wiki)
- 설치 시 "Additional language data" > "Korean" 선택
- 또는 `kor.traineddata` 파일을 `C:\Program Files\Tesseract-OCR\tessdata\`에 복사

### 3. ChromeDriver 설치 (Selenium 사용 스크래퍼)

**macOS:**
```bash
brew install chromedriver
```

**기타 OS:**
- [ChromeDriver 공식 사이트](https://chromedriver.chromium.org/)에서 다운로드

## 📖 사용 방법

### FSS 스크래퍼

#### 제재조치 스크래퍼
```bash
cd FSS_Sanctions_Scraper
python3 run_pipeline.py
```

#### 경영유의사항 스크래퍼
```bash
cd FSS_ManagementNotices_Scraper
python3 run_pipeline.py
```

#### 검사업무 메뉴얼 스크래퍼
```bash
cd InspectionManual_Scraper
python3 run_pipeline.py
```

### 기타 스크래퍼

각 스크래퍼는 독립적으로 실행 가능합니다. 프로젝트 루트에서 실행하세요:

```bash
# 법제처 스크래퍼
python3 Law_Scraper/law_scraper.py

# 은행연합회 스크래퍼
python3 KFB_Scraper/kfb_scraper.py
python3 KFB_Notice_Scraper/kfb_notice_scraper.py
python3 KFB_Committee_Scraper/kfb_committee_scraper.py
python3 KFB_Finlaw_Scraper/kfb_finlaw_scraper.py

# 금융투자협회 스크래퍼
python3 KOFIA_Scraper/kofia_scraper.py

# 여신금융협회 스크래퍼
python3 CREFIA_Scraper/crefia_scraper.py

# 한국은행 스크래퍼
python3 BOK_Scraper/bok_scraper.py

# 저축은행중앙회 스크래퍼
python3 FSB_Scraper/fsb_scraper.py

# 한국거래소 스크래퍼
python3 KRX_Scraper/krx_scraper.py
```

각 스크래퍼의 상세한 사용법과 옵션은 해당 디렉토리의 `README.md`를 참고하세요.

## 📁 출력 파일

각 스크래퍼는 `output/` 디렉토리 또는 각 스크래퍼 디렉토리에 결과를 저장합니다:

- **JSON 파일**: `{스크래퍼명}_{데이터타입}.json`
- **CSV 파일**: `{스크래퍼명}_{데이터타입}.csv`
- **다운로드 파일**: `output/downloads/` (HWP, PDF 등)

## 🔧 공통 기능

모든 스크래퍼는 `BaseScraper` 클래스를 상속받아 다음 기능을 공유합니다:

- 웹 페이지 가져오기 (requests/Selenium)
- JSON/CSV 파일 저장
- 에러 처리 및 재시도 로직
- 서버 부하 방지를 위한 딜레이 설정
- SSL 인증서 검증 우회 (필요 시)

## 📝 참고사항

1. **Selenium 사용**: JavaScript로 동적 로드되는 페이지는 Selenium을 사용합니다.
2. **페이지네이션**: 대부분의 스크래퍼는 자동으로 모든 페이지를 스크래핑합니다.
3. **파일 형식**: PDF, HWP, ZIP 파일을 자동으로 처리합니다.
4. **로그인 필요**: 일부 사이트(저축은행중앙회 등)는 로그인이 필요할 수 있습니다.

## 🛠️ 개발 상태

- ✅ 완료: FSS 제재조치, 경영유의사항, 검사업무 메뉴얼
- ✅ 완료: 법제처, 은행연합회
- 🚧 진행 중: 기타 스크래퍼들 (기본 구조 완성, 데이터 추출 로직 구현 필요)

## 📄 라이선스

이 프로젝트는 교육/연구 목적으로 제작되었습니다.
