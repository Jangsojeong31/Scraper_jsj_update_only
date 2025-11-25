# 소스 패키지를 .whl 파일로 수동 변환하기

## 방법 1: pip wheel 사용 (권장)

인터넷이 연결된 환경에서 다음 명령어를 실행하세요:

```bash
# olefile 변환
pip wheel --no-deps olefile-0.46.zip

# pyhwp 변환
pip wheel --no-deps pyhwp-0.1b15.tar.gz
```

생성된 .whl 파일을 `source_packages` 디렉토리로 복사하세요.

## 방법 2: PyPI에서 직접 다운로드

인터넷이 연결된 환경에서:

```bash
# olefile wheel 다운로드
pip download olefile==0.46 --only-binary :all: -d source_packages

# pyhwp wheel 다운로드 (가능한 경우)
pip download pyhwp==0.1b15 --only-binary :all: -d source_packages
```

**참고**: `pyhwp`는 wheel 파일이 제공되지 않을 수 있습니다. 이 경우 방법 1을 사용하세요.

## 방법 3: setup.py를 사용한 변환

소스 패키지를 압축 해제한 후:

```bash
# olefile-0.46.zip 압축 해제
unzip olefile-0.46.zip
cd olefile-0.46

# wheel 파일 생성
python setup.py bdist_wheel

# 생성된 파일은 dist/ 디렉토리에 있습니다
# dist/olefile-0.46-py2.py3-none-any.whl 파일을 source_packages로 복사
```

```bash
# pyhwp-0.1b15.tar.gz 압축 해제
tar -xzf pyhwp-0.1b15.tar.gz
cd pyhwp-0.1b15

# wheel 파일 생성
python setup.py bdist_wheel

# 생성된 파일은 dist/ 디렉토리에 있습니다
```

## 변환 후 확인

변환된 .whl 파일이 올바른지 확인:

```bash
pip install --dry-run --no-index --find-links source_packages olefile==0.46
pip install --dry-run --no-index --find-links source_packages pyhwp==0.1b15
```


