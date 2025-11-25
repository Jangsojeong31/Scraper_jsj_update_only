@echo off
REM 오프라인 패키지 설치 스크립트 (Windows)
REM source_packages 디렉토리의 모든 패키지를 설치합니다

setlocal enabledelayedexpansion

set PACKAGE_DIR=%~dp0source_packages

if not exist "%PACKAGE_DIR%" (
    echo 오류: source_packages 디렉토리를 찾을 수 없습니다.
    exit /b 1
)

echo ========================================
echo 오프라인 패키지 설치 시작
echo ========================================
echo.

REM .whl 파일 먼저 설치
echo [1단계] .whl 파일 설치 중...
for %%f in ("%PACKAGE_DIR%\*.whl") do (
    echo 설치 중: %%~nxf
    pip install --no-index --find-links "%PACKAGE_DIR%" "%%f"
    if errorlevel 1 (
        echo 경고: %%~nxf 설치 실패
    )
)

echo.
echo [2단계] 소스 패키지 설치 중...

REM 소스 패키지 설치 (.zip, .tar.gz)
echo.
echo [2단계] 소스 패키지 설치 중...

REM olefile-0.46.zip 설치
if exist "%PACKAGE_DIR%\olefile-0.46.zip" (
    echo 설치 중: olefile-0.46.zip
    pip install --no-index --find-links "%PACKAGE_DIR%" --no-build-isolation "%PACKAGE_DIR%\olefile-0.46.zip"
    if errorlevel 1 (
        echo 오류: olefile-0.46.zip 설치 실패
        echo 대안: 인터넷 연결 환경에서 .whl 파일로 변환 후 다시 시도하세요.
    ) else (
        echo 성공: olefile-0.46.zip 설치 완료
    )
) else if exist "%PACKAGE_DIR%\olefile-0.46*.whl" (
    echo 발견: olefile .whl 파일이 이미 존재합니다.
    for %%f in ("%PACKAGE_DIR%\olefile-0.46*.whl") do (
        echo 설치 중: %%~nxf
        pip install --no-index --find-links "%PACKAGE_DIR%" "%%f"
    )
)

REM pyhwp-0.1b15.tar.gz 설치
if exist "%PACKAGE_DIR%\pyhwp-0.1b15.tar.gz" (
    echo 설치 중: pyhwp-0.1b15.tar.gz
    REM pyhwp는 olefile에 의존하므로 olefile이 먼저 설치되어 있어야 함
    pip install --no-index --find-links "%PACKAGE_DIR%" --no-build-isolation "%PACKAGE_DIR%\pyhwp-0.1b15.tar.gz"
    if errorlevel 1 (
        echo 오류: pyhwp-0.1b15.tar.gz 설치 실패
        echo 참고: pyhwp는 C 확장이 포함되어 있어 컴파일러가 필요할 수 있습니다.
        echo 대안: 인터넷 연결 환경에서 .whl 파일로 변환 후 다시 시도하세요.
    ) else (
        echo 성공: pyhwp-0.1b15.tar.gz 설치 완료
    )
) else if exist "%PACKAGE_DIR%\pyhwp-0.1b15*.whl" (
    echo 발견: pyhwp .whl 파일이 이미 존재합니다.
    for %%f in ("%PACKAGE_DIR%\pyhwp-0.1b15*.whl") do (
        echo 설치 중: %%~nxf
        pip install --no-index --find-links "%PACKAGE_DIR%" "%%f"
    )
)

echo.
echo ========================================
echo 설치 완료
echo ========================================
pause

