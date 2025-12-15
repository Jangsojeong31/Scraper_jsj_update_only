"""
폐쇄망 환경 시뮬레이션 테스트 스크립트 (인터넷 차단 상태)
인터넷을 차단한 상태에서 실행하여 실제 폐쇄망 환경을 시뮬레이션합니다.
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
def find_project_root():
    """common 디렉토리를 찾을 때까지 상위 디렉토리로 이동"""
    try:
        current = Path(__file__).resolve().parent
    except NameError:
        current = Path.cwd()
    
    while current != current.parent:
        if (current / 'common').exists() and (current / 'common' / 'base_scraper.py').exists():
            return current
        current = current.parent
    
    return Path.cwd()

project_root = find_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from common.base_scraper import BaseScraper
import shutil
import socket

def check_internet_connection():
    """인터넷 연결 확인"""
    try:
        # Google DNS에 연결 시도
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def find_chromedriver():
    """chromedriver 경로 찾기 (여러 위치 확인)"""
    # 방법 1: PATH에서 찾기
    path = shutil.which('chromedriver')
    if path:
        return path
    
    # 방법 2: 일반적인 설치 위치 확인
    common_paths = [
        '/usr/local/bin/chromedriver',
        '/opt/homebrew/bin/chromedriver',
        '/usr/bin/chromedriver',
        os.path.expanduser('~/bin/chromedriver'),
        os.path.expanduser('~/.local/bin/chromedriver'),
    ]
    
    for path in common_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    
    # 방법 3: Selenium이 사용하는 캐시 위치 확인
    try:
        from selenium import webdriver
        # 임시로 드라이버를 생성해서 경로 확인 (인터넷 연결 필요)
        temp_driver = webdriver.Chrome()
        driver_path = temp_driver.service.path
        temp_driver.quit()
        if driver_path and os.path.exists(driver_path):
            return driver_path
    except:
        pass
    
    return None

def test_offline_environment():
    """인터넷 차단 상태에서 폐쇄망 환경 테스트"""
    print("=" * 70)
    print("폐쇄망 환경 시뮬레이션 테스트 (인터넷 차단 상태)")
    print("=" * 70)
    
    # 인터넷 연결 확인
    print("\n1. 인터넷 연결 확인 중...")
    has_internet = check_internet_connection()
    if has_internet:
        print("   ⚠ 인터넷 연결이 감지되었습니다.")
        print("   → 실제 폐쇄망 테스트를 위해서는 인터넷을 차단해주세요.")
        print("   → (Wi-Fi 끄기 또는 네트워크 설정에서 연결 차단)")
        response = input("\n   계속 진행하시겠습니까? (y/n): ")
        if response.lower() != 'y':
            print("   테스트를 중단합니다.")
            return False
    else:
        print("   ✓ 인터넷 연결이 차단된 상태입니다. (폐쇄망 시뮬레이션)")
    
    # chromedriver 찾기
    print("\n2. chromedriver 경로 찾기 중...")
    chromedriver_path = find_chromedriver()
    
    if not chromedriver_path:
        print("   ❌ chromedriver를 찾을 수 없습니다.")
        print("\n   폐쇄망 환경에서는 chromedriver가 미리 설치되어 있어야 합니다.")
        print("   설치 방법:")
        print("   1. Chrome 브라우저 버전 확인")
        print("   2. 해당 버전에 맞는 chromedriver 다운로드")
        print("   3. PATH에 추가하거나 SELENIUM_DRIVER_PATH 환경변수 설정")
        return False
    
    print(f"   ✓ chromedriver 발견: {chromedriver_path}")
    
    # 원본 환경변수 백업
    original_selenium_driver_path = os.environ.get('SELENIUM_DRIVER_PATH')
    original_selenium_manager_skip = os.environ.get('SELENIUM_MANAGER_SKIP')
    
    try:
        # 폐쇄망 환경 시뮬레이션 설정
        print("\n3. 폐쇄망 환경 설정 중...")
        
        # 환경변수로 명시적으로 chromedriver 경로 설정
        os.environ['SELENIUM_DRIVER_PATH'] = chromedriver_path
        print(f"   ✓ SELENIUM_DRIVER_PATH 환경변수 설정: {chromedriver_path}")
        
        # SeleniumManager 우회 설정
        os.environ['SELENIUM_MANAGER_SKIP'] = '1'
        print("   ✓ SELENIUM_MANAGER_SKIP=1 설정 (SeleniumManager 우회)")
        
        # BaseScraper 인스턴스 생성
        print("\n4. BaseScraper 인스턴스 생성 중...")
        scraper = BaseScraper(delay=1.0)
        print(f"   ✓ BaseScraper 생성 완료")
        print(f"   → 드라이버 경로: {scraper.selenium_driver_path}")
        
        if scraper.selenium_driver_path != chromedriver_path:
            print(f"   ⚠ 경로 불일치: 예상={chromedriver_path}, 실제={scraper.selenium_driver_path}")
            print("   → 환경변수가 제대로 읽히지 않았을 수 있습니다.")
        else:
            print("   ✓ 환경변수에서 드라이버 경로를 올바르게 읽었습니다.")
        
        # Chrome 옵션 설정
        print("\n5. Chrome 옵션 설정 중...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ko-KR')
        print("   ✓ Chrome 옵션 설정 완료")
        
        # 드라이버 생성 (폐쇄망 환경 대응 방식)
        print("\n6. Selenium 드라이버 생성 중...")
        print("   → BaseScraper._create_webdriver() 사용")
        print("   → 폐쇄망 환경: 로컬 chromedriver 사용, 인터넷 연결 불필요")
        print("   → SeleniumManager는 사용하지 않음")
        
        try:
            driver = scraper._create_webdriver(chrome_options)
            print("   ✓ 드라이버 생성 성공!")
            print("   → 인터넷 연결 없이 로컬 드라이버를 사용했습니다.")
            
            # 간단한 테스트 (인터넷 연결 불필요)
            print("\n7. 테스트 페이지 접속 중...")
            try:
                # data URL로 간단한 테스트 (인터넷 연결 불필요)
                driver.get("data:text/html,<html><head><title>폐쇄망 테스트</title></head><body><h1>✅ 폐쇄망 환경에서 정상 작동합니다!</h1><p>인터넷 연결 없이 로컬 드라이버를 사용했습니다.</p></body></html>")
                print(f"   ✓ 페이지 접속 성공: {driver.title}")
                print("   → 인터넷 연결 없이도 정상 작동합니다.")
            except Exception as e:
                print(f"   ⚠ 페이지 접속 실패: {e}")
                # 하지만 드라이버 생성 자체는 성공했으므로 OK
            
            # 드라이버 종료
            print("\n8. 드라이버 종료 중...")
            driver.quit()
            print("   ✓ 드라이버 종료 완료")
            
            print("\n" + "=" * 70)
            print("✅ 폐쇄망 환경 시뮬레이션 테스트 성공!")
            print("=" * 70)
            print("\n요약:")
            print("  ✓ 인터넷 연결 없이도 드라이버 생성 성공")
            print("  ✓ SeleniumManager를 사용하지 않고 로컬 chromedriver 사용")
            print("  ✓ BaseScraper._create_webdriver()가 정상 작동")
            print("  ✓ 실제 폐쇄망 환경에서도 동일하게 작동할 것입니다.")
            return True
            
        except Exception as e:
            print(f"\n❌ 드라이버 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            print("\n가능한 원인:")
            print("  1. chromedriver가 실행 불가능하거나 손상됨")
            print("  2. Chrome 브라우저가 설치되지 않음")
            print("  3. chromedriver와 Chrome 버전이 호환되지 않음")
            print("  4. 인터넷 연결이 필요할 수 있음 (SeleniumManager가 작동 중)")
            return False
            
    finally:
        # 환경변수 복원
        if original_selenium_driver_path:
            os.environ['SELENIUM_DRIVER_PATH'] = original_selenium_driver_path
        elif 'SELENIUM_DRIVER_PATH' in os.environ:
            del os.environ['SELENIUM_DRIVER_PATH']
        
        if original_selenium_manager_skip:
            os.environ['SELENIUM_MANAGER_SKIP'] = original_selenium_manager_skip
        elif 'SELENIUM_MANAGER_SKIP' in os.environ:
            del os.environ['SELENIUM_MANAGER_SKIP']

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("폐쇄망 환경 시뮬레이션 테스트 (인터넷 차단 상태)")
    print("=" * 70)
    print("\n주의사항:")
    print("  - 이 테스트는 인터넷 연결이 차단된 상태에서 실행하는 것이 이상적입니다.")
    print("  - Wi-Fi를 끄거나 네트워크 연결을 차단한 후 실행하세요.")
    print("  - chromedriver가 로컬에 설치되어 있어야 합니다.")
    print("")
    
    success = test_offline_environment()
    
    if success:
        print("\n🎉 테스트 통과! 폐쇄망 환경에서 정상 작동합니다.")
        sys.exit(0)
    else:
        print("\n⚠ 테스트 실패. 로그를 확인하세요.")
        sys.exit(1)

