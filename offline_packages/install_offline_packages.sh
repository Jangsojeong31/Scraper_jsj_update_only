#!/bin/bash
# 오프라인 패키지 설치 스크립트 (Linux/macOS)
# source_packages 디렉토리의 모든 패키지를 설치합니다

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${SCRIPT_DIR}/source_packages"

if [ ! -d "$PACKAGE_DIR" ]; then
    echo "오류: source_packages 디렉토리를 찾을 수 없습니다."
    exit 1
fi

echo "========================================"
echo "오프라인 패키지 설치 시작"
echo "========================================"
echo ""

# .whl 파일 먼저 설치
echo "[1단계] .whl 파일 설치 중..."
for whl_file in "$PACKAGE_DIR"/*.whl; do
    if [ -f "$whl_file" ]; then
        echo "설치 중: $(basename "$whl_file")"
        pip install --no-index --find-links "$PACKAGE_DIR" "$whl_file" || echo "경고: $(basename "$whl_file") 설치 실패"
    fi
done

echo ""
echo "[2단계] 소스 패키지 설치 중..."

# olefile-0.46.zip 설치
if [ -f "$PACKAGE_DIR/olefile-0.46.zip" ]; then
    echo "설치 중: olefile-0.46.zip"
    if pip install --no-index --find-links "$PACKAGE_DIR" --no-build-isolation "$PACKAGE_DIR/olefile-0.46.zip"; then
        echo "성공: olefile-0.46.zip 설치 완료"
    else
        echo "오류: olefile-0.46.zip 설치 실패"
        echo "대안: 인터넷 연결 환경에서 .whl 파일로 변환 후 다시 시도하세요."
    fi
elif ls "$PACKAGE_DIR"/olefile-0.46*.whl 1> /dev/null 2>&1; then
    echo "발견: olefile .whl 파일이 이미 존재합니다."
    for whl_file in "$PACKAGE_DIR"/olefile-0.46*.whl; do
        echo "설치 중: $(basename "$whl_file")"
        pip install --no-index --find-links "$PACKAGE_DIR" "$whl_file"
    done
fi

# pyhwp-0.1b15.tar.gz 설치
if [ -f "$PACKAGE_DIR/pyhwp-0.1b15.tar.gz" ]; then
    echo "설치 중: pyhwp-0.1b15.tar.gz"
    # pyhwp는 olefile에 의존하므로 olefile이 먼저 설치되어 있어야 함
    if pip install --no-index --find-links "$PACKAGE_DIR" --no-build-isolation "$PACKAGE_DIR/pyhwp-0.1b15.tar.gz"; then
        echo "성공: pyhwp-0.1b15.tar.gz 설치 완료"
    else
        echo "오류: pyhwp-0.1b15.tar.gz 설치 실패"
        echo "참고: pyhwp는 C 확장이 포함되어 있어 컴파일러가 필요할 수 있습니다."
        echo "대안: 인터넷 연결 환경에서 .whl 파일로 변환 후 다시 시도하세요."
    fi
elif ls "$PACKAGE_DIR"/pyhwp-0.1b15*.whl 1> /dev/null 2>&1; then
    echo "발견: pyhwp .whl 파일이 이미 존재합니다."
    for whl_file in "$PACKAGE_DIR"/pyhwp-0.1b15*.whl; do
        echo "설치 중: $(basename "$whl_file")"
        pip install --no-index --find-links "$PACKAGE_DIR" "$whl_file"
    done
fi

echo ""
echo "========================================"
echo "설치 완료"
echo "========================================"

