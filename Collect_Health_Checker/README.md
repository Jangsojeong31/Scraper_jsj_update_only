# Health Checker

스크래퍼의 상태를 확인하고 폐쇄망 환경에서의 작동 여부를 테스트하는 스크립트 모음입니다.

## 파일 목록

### 1. `test_selenium_init.py`
- **목적**: Selenium 드라이버 초기화 테스트
- **용도**: BaseScraper의 `_create_webdriver()` 메서드가 정상 작동하는지 확인
- **실행 방법**:
  ```bash
  python health_checker/test_selenium_init.py
  ```

### 2. `test_closed_network.py`
- **목적**: 폐쇄망 환경 시뮬레이션 테스트 (일반 환경)
- **용도**: SeleniumManager를 사용하지 않고 로컬 chromedriver를 사용하는지 확인
- **실행 방법**:
  ```bash
  python health_checker/test_closed_network.py
  ```

### 3. `test_closed_network_offline.py`
- **목적**: 폐쇄망 환경 시뮬레이션 테스트 (인터넷 차단 상태)
- **용도**: 인터넷 연결이 차단된 상태에서도 정상 작동하는지 확인
- **실행 방법**:
  ```bash
  # Wi-Fi를 끄거나 네트워크 연결을 차단한 후
  python health_checker/test_closed_network_offline.py
  ```

## 사용 시나리오

### 일반 환경에서 테스트
```bash
# 기본 Selenium 초기화 테스트
python health_checker/test_selenium_init.py

# 폐쇄망 시뮬레이션 테스트 (인터넷 연결 있음)
python health_checker/test_closed_network.py
```

### 폐쇄망 환경 시뮬레이션
1. Wi-Fi 끄기 또는 네트워크 연결 차단
2. 테스트 실행:
   ```bash
   python health_checker/test_closed_network_offline.py
   ```

## 테스트 결과 해석

### ✅ 성공
- 드라이버 생성 성공
- 페이지 접속 성공
- SeleniumManager 우회 확인

### ❌ 실패
- chromedriver를 찾을 수 없음 → chromedriver 설치 필요
- 드라이버 생성 실패 → Chrome 브라우저 설치 또는 버전 호환성 확인
- 인터넷 연결 필요 → 폐쇄망 환경 설정 확인

## 폐쇄망 환경 준비

폐쇄망 환경에서 정상 작동하려면:

1. **chromedriver 설치**
   - Chrome 브라우저 버전 확인
   - 해당 버전에 맞는 chromedriver 다운로드
   - PATH에 추가하거나 `SELENIUM_DRIVER_PATH` 환경변수 설정

2. **환경변수 설정 (선택사항)**
   ```bash
   export SELENIUM_DRIVER_PATH=/path/to/chromedriver
   ```

3. **테스트 실행**
   ```bash
   python health_checker/test_closed_network_offline.py
   ```

## 참고사항

- 모든 테스트 스크립트는 프로젝트 루트에서 실행해야 합니다.
- `common/base_scraper.py`의 `_create_webdriver()` 메서드를 사용합니다.
- 폐쇄망 환경에서는 인터넷 연결 없이도 로컬 chromedriver를 사용합니다.

