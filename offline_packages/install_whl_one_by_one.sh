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
        echo "[설치] $whl_file"
        if pip install --no-index --find-links "$PACKAGE_DIR" "$PACKAGE_DIR/$whl_file"; then
            echo "[성공] $whl_file 설치 완료"
        else
            echo "[실패] $whl_file 설치 실패 - 계속 진행합니다..."
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
echo ""
echo "설치된 패키지 확인:"
pip list



