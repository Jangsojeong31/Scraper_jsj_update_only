# 폐쇄망 환경 빠른 시작 가이드

## 설치 방법 선택

### 방법 1: 자동 설치 스크립트 사용 (권장)

#### Windows
```powershell
cd offline_packages
.\install_whl_one_by_one.bat
```

#### Linux/macOS
```bash
cd offline_packages
chmod +x install_whl_one_by_one.sh
./install_whl_one_by_one.sh
```

### 방법 2: 수동으로 하나씩 설치

의존성 순서를 고려하여 하나씩 설치합니다.

#### 기본 명령어 형식
```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\<패키지명>.whl

# Linux/macOS
pip install --no-index --find-links ./source_packages ./source_packages/<패키지명>.whl
```

#### 설치 순서 (간단 버전)

1. **기본 유틸리티** (six, packaging, attrs, idna, certifi 등)
2. **암호화** (pycparser, cffi, cryptography)
3. **HTTP 클라이언트** (urllib3, PySocks, requests)
4. **파싱** (lxml, soupsieve, beautifulsoup4)
5. **데이터 처리** (numpy, pandas)
6. **파일 처리** (et_xmlfile, openpyxl, olefile, pyhwp)
7. **PDF 처리** (pdfminer_six, pdfplumber, pypdf2, pymupdf, pypdfium2)
8. **이미지 처리** (pillow, pytesseract)
9. **웹 자동화** (trio, trio_websocket, selenium)

자세한 내용은 `INSTALL_WHL_MANUAL.md`를 참고하세요.

## 설치 확인

```powershell
pip list
```

## 문제 해결

### 설치 실패 시
1. 오류 메시지 확인
2. 누락된 의존성 패키지 먼저 설치
3. `--force-reinstall` 옵션으로 재시도

### Python 버전 확인
```powershell
python --version
```
- 현재 whl 파일들은 Python 3.11용입니다.
- 다른 버전이면 해당 버전용 whl 파일이 필요합니다.

## 상세 가이드

- **자세한 설치 가이드**: `INSTALL_WHL_MANUAL.md`
- **기존 설치 스크립트**: `install_offline_packages.bat` (또는 `.sh`)




