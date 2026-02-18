# 오프라인 패키지 설치 가이드

폐쇄망 환경에서 Python 패키지를 설치하기 위한 가이드입니다.

## 문제 상황

일부 패키지(`olefile-0.46.zip`, `pyhwp-0.1b15.tar.gz`)는 소스 배포판 형태로 제공되어 있어서, 
다른 .whl 파일들과 달리 직접 설치가 어려울 수 있습니다.

## 해결 방법

### 방법 1: .whl 파일로 변환 (권장)

**인터넷이 연결된 환경에서:**

1. `build_wheels.py` 스크립트 실행:
```bash
cd offline_packages
python build_wheels.py
```

2. 생성된 .whl 파일을 `source_packages` 디렉토리에서 확인
3. 변환된 .whl 파일과 함께 폐쇄망으로 이동

**폐쇄망 환경에서:**

```bash
# Windows
install_offline_packages.bat

# Linux/macOS
chmod +x install_offline_packages.sh
./install_offline_packages.sh
```

### 방법 2: 소스 패키지 직접 설치

폐쇄망 환경에서 소스 패키지를 직접 설치할 수 있습니다:

```bash
# Windows
pip install --no-index --find-links source_packages source_packages\olefile-0.46.zip
pip install --no-index --find-links source_packages source_packages\pyhwp-0.1b15.tar.gz

# Linux/macOS
pip install --no-index --find-links source_packages source_packages/olefile-0.46.zip
pip install --no-index --find-links source_packages source_packages/pyhwp-0.1b15.tar.gz
```

## 주의사항

1. **빌드 도구 필요**: 소스 패키지를 설치하려면 해당 패키지의 빌드 도구가 필요할 수 있습니다.
   - `olefile`: 일반적으로 빌드 도구 불필요 (순수 Python)
   - `pyhwp`: C 확장이 포함되어 있을 수 있어 컴파일러가 필요할 수 있음

2. **의존성 확인**: 소스 패키지 설치 시 추가 의존성이 필요할 수 있습니다.
   - `pyhwp`는 `olefile`에 의존할 수 있으므로 `olefile`을 먼저 설치해야 합니다.

3. **Python 버전**: Python 버전과 호환되는 패키지를 사용해야 합니다.

## 권장 설치 순서

1. 먼저 모든 .whl 파일 설치
2. 그 다음 소스 패키지 설치:
   - `olefile-0.46.zip` 먼저
   - `pyhwp-0.1b15.tar.gz` 나중에

## 문제 해결

### 설치 실패 시

1. **에러 메시지 확인**: 어떤 패키지가 누락되었는지 확인
2. **의존성 확인**: `requirements.txt`에 명시된 의존성 모두 준비되었는지 확인
3. **Python 버전 확인**: Python 3.8 이상인지 확인
4. **빌드 도구 확인**: Windows의 경우 Visual C++ Build Tools가 필요할 수 있습니다

### pyhwp 설치 실패 시

`pyhwp`는 C 확장이 포함되어 있어 컴파일러가 필요할 수 있습니다:
- **Windows**: Visual C++ Build Tools 또는 Visual Studio 설치 필요
- **Linux**: `gcc`, `python3-dev` 패키지 필요
- **macOS**: Xcode Command Line Tools 필요

만약 빌드가 불가능한 환경이라면, 인터넷이 연결된 환경에서 .whl 파일로 변환하여 사용하는 것을 권장합니다.

