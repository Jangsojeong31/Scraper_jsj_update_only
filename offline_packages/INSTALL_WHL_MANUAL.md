# 폐쇄망 환경 WHL 파일 개별 설치 가이드

## 개요
폐쇄망 환경에서 Python 패키지를 하나씩 설치하는 방법을 정리한 가이드입니다.
`requirements.txt`를 한 번에 설치하는 것이 실패할 경우, 이 가이드를 참고하여 의존성 순서대로 하나씩 설치하세요.

## 기본 명령어 형식

### Windows PowerShell/CMD
```powershell
pip install --no-index --find-links .\source_packages .\source_packages\<패키지명>.whl
```

### Linux/macOS
```bash
pip install --no-index --find-links ./source_packages ./source_packages/<패키지명>.whl
```

## 설치 순서 (의존성 고려)

### 1단계: 기본 유틸리티 패키지 (의존성이 없는 패키지)

이 패키지들은 다른 패키지의 기반이 되므로 먼저 설치해야 합니다.

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\six-1.17.0-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\packaging-25.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\attrs-25.4.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\idna-3.11-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\certifi-2025.11.12-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\charset_normalizer-3.4.4-cp311-cp311-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\sniffio-1.3.1-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\h11-0.16.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\outcome-1.3.0.post0-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\sortedcontainers-2.4.0-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\wsproto-1.3.2-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\pytz-2025.2-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\tzdata-2025.2-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\python_dateutil-2.9.0.post0-py2.py3-none-any.whl
```

### 2단계: 암호화/보안 관련 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\pycparser-2.23-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\cffi-2.0.0-cp311-cp311-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\cryptography-46.0.3-cp311-abi3-win_amd64.whl
```

### 3단계: HTTP 클라이언트 관련 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\urllib3-2.5.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\PySocks-1.7.1-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\requests-2.31.0-py3-none-any.whl
```

### 4단계: XML/HTML 파싱 관련 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\lxml-4.9.3-cp311-cp311-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\soupsieve-2.8-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\beautifulsoup4-4.12.2-py3-none-any.whl
```

### 5단계: 데이터 처리 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\numpy-2.3.5-cp311-cp311-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\pandas-2.3.3-cp311-cp311-win_amd64.whl
```

### 6단계: 파일 처리 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\et_xmlfile-2.0.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\openpyxl-3.1.2-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\olefile-0.46-py2.py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\pyhwp-0.1b15-py3-none-any.whl
```

**참고**: `olefile-0.46.zip`이 있다면, whl 파일 대신 소스 패키지로 설치:
```powershell
pip install --no-index --find-links .\source_packages --no-build-isolation .\source_packages\olefile-0.46.zip
```

**참고**: `pyhwp-0.1b15.tar.gz`가 있다면, whl 파일 대신 소스 패키지로 설치:
```powershell
pip install --no-index --find-links .\source_packages --no-build-isolation .\source_packages\pyhwp-0.1b15.tar.gz
```

### 7단계: PDF 처리 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\pdfminer_six-20251107-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\pdfplumber-0.11.8-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\pypdf2-3.0.1-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\pymupdf-1.26.6-cp310-abi3-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\pypdfium2-5.0.0-py3-none-win_amd64.whl
```

### 8단계: 이미지 처리 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\pillow-12.0.0-cp311-cp311-win_amd64.whl
pip install --no-index --find-links .\source_packages .\source_packages\pytesseract-0.3.13-py3-none-any.whl
```

### 9단계: 웹 자동화 패키지

```powershell
# Windows
pip install --no-index --find-links .\source_packages .\source_packages\trio-0.32.0-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\trio_websocket-0.12.2-py3-none-any.whl
pip install --no-index --find-links .\source_packages .\source_packages\selenium-4.15.2-py3-none-any.whl
```

## 전체 설치 스크립트 (Windows 배치 파일)

`install_whl_one_by_one.bat` 파일을 생성하여 사용할 수 있습니다:

```batch
@echo off
REM 폐쇄망 환경 WHL 파일 개별 설치 스크립트
REM 의존성 순서를 고려하여 하나씩 설치합니다

setlocal enabledelayedexpansion
set PACKAGE_DIR=%~dp0source_packages

if not exist "%PACKAGE_DIR%" (
    echo 오류: source_packages 디렉토리를 찾을 수 없습니다.
    exit /b 1
)

echo ========================================
echo WHL 파일 개별 설치 시작
echo ========================================
echo.

REM 1단계: 기본 유틸리티 패키지
echo [1단계] 기본 유틸리티 패키지 설치...
call :install_whl "six-1.17.0-py2.py3-none-any.whl"
call :install_whl "packaging-25.0-py3-none-any.whl"
call :install_whl "attrs-25.4.0-py3-none-any.whl"
call :install_whl "idna-3.11-py3-none-any.whl"
call :install_whl "certifi-2025.11.12-py3-none-any.whl"
call :install_whl "charset_normalizer-3.4.4-cp311-cp311-win_amd64.whl"
call :install_whl "sniffio-1.3.1-py3-none-any.whl"
call :install_whl "h11-0.16.0-py3-none-any.whl"
call :install_whl "outcome-1.3.0.post0-py2.py3-none-any.whl"
call :install_whl "sortedcontainers-2.4.0-py2.py3-none-any.whl"
call :install_whl "wsproto-1.3.2-py3-none-any.whl"
call :install_whl "pytz-2025.2-py2.py3-none-any.whl"
call :install_whl "tzdata-2025.2-py3-none-any.whl"
call :install_whl "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"

REM 2단계: 암호화/보안 관련
echo.
echo [2단계] 암호화/보안 관련 패키지 설치...
call :install_whl "pycparser-2.23-py3-none-any.whl"
call :install_whl "cffi-2.0.0-cp311-cp311-win_amd64.whl"
call :install_whl "cryptography-46.0.3-cp311-abi3-win_amd64.whl"

REM 3단계: HTTP 클라이언트
echo.
echo [3단계] HTTP 클라이언트 패키지 설치...
call :install_whl "urllib3-2.5.0-py3-none-any.whl"
call :install_whl "PySocks-1.7.1-py3-none-any.whl"
call :install_whl "requests-2.31.0-py3-none-any.whl"

REM 4단계: XML/HTML 파싱
echo.
echo [4단계] XML/HTML 파싱 패키지 설치...
call :install_whl "lxml-4.9.3-cp311-cp311-win_amd64.whl"
call :install_whl "soupsieve-2.8-py3-none-any.whl"
call :install_whl "beautifulsoup4-4.12.2-py3-none-any.whl"

REM 5단계: 데이터 처리
echo.
echo [5단계] 데이터 처리 패키지 설치...
call :install_whl "numpy-2.3.5-cp311-cp311-win_amd64.whl"
call :install_whl "pandas-2.3.3-cp311-cp311-win_amd64.whl"

REM 6단계: 파일 처리
echo.
echo [6단계] 파일 처리 패키지 설치...
call :install_whl "et_xmlfile-2.0.0-py3-none-any.whl"
call :install_whl "openpyxl-3.1.2-py2.py3-none-any.whl"
call :install_whl "olefile-0.46-py2.py3-none-any.whl"
call :install_whl "pyhwp-0.1b15-py3-none-any.whl"

REM 7단계: PDF 처리
echo.
echo [7단계] PDF 처리 패키지 설치...
call :install_whl "pdfminer_six-20251107-py3-none-any.whl"
call :install_whl "pdfplumber-0.11.8-py3-none-any.whl"
call :install_whl "pypdf2-3.0.1-py3-none-any.whl"
call :install_whl "pymupdf-1.26.6-cp310-abi3-win_amd64.whl"
call :install_whl "pypdfium2-5.0.0-py3-none-win_amd64.whl"

REM 8단계: 이미지 처리
echo.
echo [8단계] 이미지 처리 패키지 설치...
call :install_whl "pillow-12.0.0-cp311-cp311-win_amd64.whl"
call :install_whl "pytesseract-0.3.13-py3-none-any.whl"

REM 9단계: 웹 자동화
echo.
echo [9단계] 웹 자동화 패키지 설치...
call :install_whl "trio-0.32.0-py3-none-any.whl"
call :install_whl "trio_websocket-0.12.2-py3-none-any.whl"
call :install_whl "selenium-4.15.2-py3-none-any.whl"

echo.
echo ========================================
echo 설치 완료
echo ========================================
pause
exit /b 0

:install_whl
set WHL_FILE=%~1
if exist "%PACKAGE_DIR%\%WHL_FILE%" (
    echo 설치 중: %WHL_FILE%
    pip install --no-index --find-links "%PACKAGE_DIR%" "%PACKAGE_DIR%\%WHL_FILE%"
    if errorlevel 1 (
        echo [실패] %WHL_FILE% 설치 실패
        echo 계속 진행합니다...
    ) else (
        echo [성공] %WHL_FILE% 설치 완료
    )
) else (
    echo [건너뜀] %WHL_FILE% 파일을 찾을 수 없습니다.
)
exit /b 0
```

## Linux/macOS용 설치 스크립트

`install_whl_one_by_one.sh` 파일을 생성하여 사용할 수 있습니다:

```bash
#!/bin/bash
# 폐쇄망 환경 WHL 파일 개별 설치 스크립트
# 의존성 순서를 고려하여 하나씩 설치합니다

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${SCRIPT_DIR}/source_packages"

if [ ! -d "$PACKAGE_DIR" ]; then
    echo "오류: source_packages 디렉토리를 찾을 수 없습니다."
    exit 1
fi

install_whl() {
    local whl_file="$1"
    if [ -f "$PACKAGE_DIR/$whl_file" ]; then
        echo "설치 중: $whl_file"
        if pip install --no-index --find-links "$PACKAGE_DIR" "$PACKAGE_DIR/$whl_file"; then
            echo "[성공] $whl_file 설치 완료"
        else
            echo "[실패] $whl_file 설치 실패 (계속 진행합니다)"
        fi
    else
        echo "[건너뜀] $whl_file 파일을 찾을 수 없습니다."
    fi
}

echo "========================================"
echo "WHL 파일 개별 설치 시작"
echo "========================================"
echo ""

# 1단계: 기본 유틸리티 패키지
echo "[1단계] 기본 유틸리티 패키지 설치..."
install_whl "six-1.17.0-py2.py3-none-any.whl"
install_whl "packaging-25.0-py3-none-any.whl"
install_whl "attrs-25.4.0-py3-none-any.whl"
install_whl "idna-3.11-py3-none-any.whl"
install_whl "certifi-2025.11.12-py3-none-any.whl"
install_whl "charset_normalizer-3.4.4-cp311-cp311-win_amd64.whl"
install_whl "sniffio-1.3.1-py3-none-any.whl"
install_whl "h11-0.16.0-py3-none-any.whl"
install_whl "outcome-1.3.0.post0-py2.py3-none-any.whl"
install_whl "sortedcontainers-2.4.0-py2.py3-none-any.whl"
install_whl "wsproto-1.3.2-py3-none-any.whl"
install_whl "pytz-2025.2-py2.py3-none-any.whl"
install_whl "tzdata-2025.2-py3-none-any.whl"
install_whl "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"

# 2단계: 암호화/보안 관련
echo ""
echo "[2단계] 암호화/보안 관련 패키지 설치..."
install_whl "pycparser-2.23-py3-none-any.whl"
install_whl "cffi-2.0.0-cp311-cp311-win_amd64.whl"
install_whl "cryptography-46.0.3-cp311-abi3-win_amd64.whl"

# 3단계: HTTP 클라이언트
echo ""
echo "[3단계] HTTP 클라이언트 패키지 설치..."
install_whl "urllib3-2.5.0-py3-none-any.whl"
install_whl "PySocks-1.7.1-py3-none-any.whl"
install_whl "requests-2.31.0-py3-none-any.whl"

# 4단계: XML/HTML 파싱
echo ""
echo "[4단계] XML/HTML 파싱 패키지 설치..."
install_whl "lxml-4.9.3-cp311-cp311-win_amd64.whl"
install_whl "soupsieve-2.8-py3-none-any.whl"
install_whl "beautifulsoup4-4.12.2-py3-none-any.whl"

# 5단계: 데이터 처리
echo ""
echo "[5단계] 데이터 처리 패키지 설치..."
install_whl "numpy-2.3.5-cp311-cp311-win_amd64.whl"
install_whl "pandas-2.3.3-cp311-cp311-win_amd64.whl"

# 6단계: 파일 처리
echo ""
echo "[6단계] 파일 처리 패키지 설치..."
install_whl "et_xmlfile-2.0.0-py3-none-any.whl"
install_whl "openpyxl-3.1.2-py2.py3-none-any.whl"
install_whl "olefile-0.46-py2.py3-none-any.whl"
install_whl "pyhwp-0.1b15-py3-none-any.whl"

# 7단계: PDF 처리
echo ""
echo "[7단계] PDF 처리 패키지 설치..."
install_whl "pdfminer_six-20251107-py3-none-any.whl"
install_whl "pdfplumber-0.11.8-py3-none-any.whl"
install_whl "pypdf2-3.0.1-py3-none-any.whl"
install_whl "pymupdf-1.26.6-cp310-abi3-win_amd64.whl"
install_whl "pypdfium2-5.0.0-py3-none-win_amd64.whl"

# 8단계: 이미지 처리
echo ""
echo "[8단계] 이미지 처리 패키지 설치..."
install_whl "pillow-12.0.0-cp311-cp311-win_amd64.whl"
install_whl "pytesseract-0.3.13-py3-none-any.whl"

# 9단계: 웹 자동화
echo ""
echo "[9단계] 웹 자동화 패키지 설치..."
install_whl "trio-0.32.0-py3-none-any.whl"
install_whl "trio_websocket-0.12.2-py3-none-any.whl"
install_whl "selenium-4.15.2-py3-none-any.whl"

echo ""
echo "========================================"
echo "설치 완료"
echo "========================================"
```

## 주의사항

### 1. Python 버전 호환성
- 현재 제공된 whl 파일들은 Python 3.11용으로 빌드된 것이 많습니다.
- Python 버전이 다르면 해당 버전에 맞는 whl 파일을 준비해야 합니다.
- `cp311`는 Python 3.11을 의미합니다.

### 2. 플랫폼 호환성
- Windows용 whl 파일은 `win_amd64`로 표시됩니다.
- Linux/macOS 환경에서는 해당 플랫폼용 whl 파일이 필요합니다.

### 3. 설치 실패 시 대처 방법

#### 패키지가 이미 설치된 경우
```powershell
pip install --no-index --find-links .\source_packages --force-reinstall .\source_packages\<패키지명>.whl
```

#### 특정 패키지만 건너뛰고 계속 진행
- 스크립트는 실패해도 계속 진행하도록 설계되어 있습니다.
- 실패한 패키지는 나중에 수동으로 재시도할 수 있습니다.

#### 의존성 오류 발생 시
- 오류 메시지에서 누락된 패키지를 확인합니다.
- 해당 패키지를 먼저 설치한 후 다시 시도합니다.

### 4. 소스 패키지 처리

`olefile-0.46.zip` 또는 `pyhwp-0.1b15.tar.gz` 같은 소스 패키지가 있는 경우:

```powershell
# olefile 소스 패키지 설치
pip install --no-index --find-links .\source_packages --no-build-isolation .\source_packages\olefile-0.46.zip

# pyhwp 소스 패키지 설치 (olefile이 먼저 설치되어 있어야 함)
pip install --no-index --find-links .\source_packages --no-build-isolation .\source_packages\pyhwp-0.1b15.tar.gz
```

## 설치 확인

설치가 완료된 후 다음 명령어로 확인할 수 있습니다:

```powershell
# Windows
pip list

# 특정 패키지 확인
pip show requests
pip show pandas
pip show selenium
```

## 문제 해결

### 문제: "No matching distribution found"
- 원인: Python 버전이나 플랫폼이 맞지 않음
- 해결: 해당 환경에 맞는 whl 파일을 준비하거나 소스 패키지로 설치

### 문제: "Failed building wheel"
- 원인: 빌드 도구가 없거나 의존성이 누락됨
- 해결: 이미 빌드된 whl 파일을 사용하거나, 인터넷 연결 환경에서 whl로 변환

### 문제: "Requirement already satisfied"
- 원인: 패키지가 이미 설치되어 있음
- 해결: 정상입니다. `--force-reinstall` 옵션으로 재설치 가능

## 추가 참고사항

- 모든 패키지를 한 번에 설치하려면 `install_offline_packages.bat` (또는 `.sh`)를 사용하세요.
- 개별 설치가 필요한 경우 이 가이드를 참고하여 순서대로 설치하세요.
- 설치 순서는 의존성 관계를 고려한 것이므로, 가능하면 순서를 지켜주세요.





