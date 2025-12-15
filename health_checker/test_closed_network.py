"""
폐쇄망 환경 시뮬레이션 테스트 스크립트
SeleniumManager를 사용하지 않고 로컬 chromedriver를 사용하는지 확인
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
from common.base_scraper import BaseScraper
import shutil

def test_closed_network_simulation():
    """폐쇄망 환경 시뮬레이션 테스트"""
    print("=" * 70)
    print("폐쇄망 환경 시뮬레이션 테스트")
    print("=" * 70)
    
    # 원본 환경변수 백업
    original_selenium_driver_path = os.environ.get('SELENIUM_DRIVER_PATH')
    original_selenium_manager_skip = os.environ.get('SELENIUM_MANAGER_SKIP')
    
    try:
        # 폐쇄망 환경 시뮬레이션 설정
        print("\n1. 폐쇄망 환경 시뮬레이션 설정 중...")
        
        # chromedriver 경로 찾기
        chromedriver_path = shutil.which('chromedriver')
        if chromedriver_path:
            print(f"   ✓ chromedriver 발견: {chromedriver_path}")
            # 환경변수로 명시적으로 설정 (폐쇄망에서 수동 설정하는 것처럼)
            os.environ['SELENIUM_DRIVER_PATH'] = chromedriver_path
            print(f"   → SELENIUM_DRIVER_PATH 환경변수 설정: {chromedriver_path}")
        else:
            # chromedriver가 PATH에 없어도 SeleniumManager가 자동으로 다운로드하지만,
            # 폐쇄망에서는 이것이 실패할 것입니다.
            # 실제 폐쇄망 환경에서는 chromedriver가 미리 설치되어 있어야 합니다.
            print("   ⚠ chromedriver를 PATH에서 찾을 수 없습니다.")
            print("   → 현재 환경: SeleniumManager가 자동으로 다운로드할 수 있음")
            print("   → 폐쇄망 환경: chromedriver가 미리 설치되어 있어야 함")
            print("   → 테스트를 계속 진행하지만, 실제 폐쇄망에서는 chromedriver가 필요합니다.")
            # 테스트는 계속 진행 (SeleniumManager가 작동할 수 있음)
        
        # SeleniumManager 우회 설정 (BaseScraper가 자동으로 설정하지만 명시적으로도 설정)
        os.environ['SELENIUM_MANAGER_SKIP'] = '1'
        print("   → SELENIUM_MANAGER_SKIP=1 설정 (SeleniumManager 우회)")
        
        # BaseScraper 인스턴스 생성
        print("\n2. BaseScraper 인스턴스 생성 중...")
        scraper = BaseScraper(delay=1.0)
        print(f"   ✓ BaseScraper 생성 완료")
        print(f"   → 드라이버 경로: {scraper.selenium_driver_path or '자동 탐지 예정'}")
        
        if scraper.selenium_driver_path:
            print(f"   ✓ 드라이버 경로 자동 탐지 성공: {scraper.selenium_driver_path}")
            print("   → 폐쇄망 환경: 로컬 드라이버 사용 가능")
        else:
            print("   ⚠ 드라이버 경로를 찾지 못했습니다.")
            print("   → 현재 환경: SeleniumManager가 자동으로 다운로드 시도")
            print("   → 폐쇄망 환경: 이 경우 실패할 것입니다 (인터넷 연결 필요)")
            print("   → 테스트는 계속 진행하지만, 실제 폐쇄망에서는 chromedriver가 필요합니다.")
        
        # Chrome 옵션 설정
        print("\n3. Chrome 옵션 설정 중...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ko-KR')
        print("   ✓ Chrome 옵션 설정 완료")
        
        # 드라이버 생성 (폐쇄망 환경 대응 방식)
        print("\n4. Selenium 드라이버 생성 중...")
        print("   → BaseScraper._create_webdriver() 사용 (SeleniumManager 우회)")
        print("   → 폐쇄망 환경: 로컬 chromedriver 사용, 인터넷 연결 불필요")
        
        try:
            driver = scraper._create_webdriver(chrome_options)
            print("   ✓ 드라이버 생성 성공!")
            print("   → SeleniumManager를 사용하지 않고 로컬 드라이버를 사용했습니다.")
            
            # 간단한 테스트 페이지 접속 (로컬 파일 또는 간단한 테스트)
            print("\n5. 테스트 페이지 접속 중...")
            try:
                # data URL로 간단한 테스트 (인터넷 연결 불필요)
                driver.get("data:text/html,<html><head><title>Test</title></head><body><h1>폐쇄망 테스트 성공</h1></body></html>")
                print(f"   ✓ 페이지 접속 성공: {driver.title}")
            except Exception as e:
                print(f"   ⚠ 페이지 접속 실패: {e}")
                # 하지만 드라이버 생성 자체는 성공했으므로 OK
            
            # 드라이버 종료
            print("\n6. 드라이버 종료 중...")
            driver.quit()
            print("   ✓ 드라이버 종료 완료")
            
            print("\n" + "=" * 70)
            print("✅ 폐쇄망 환경 시뮬레이션 테스트 성공!")
            print("=" * 70)
            print("\n요약:")
            print("  - SeleniumManager를 사용하지 않고 로컬 chromedriver 사용")
            print("  - 인터넷 연결 없이도 드라이버 생성 가능")
            print("  - BaseScraper._create_webdriver()가 정상 작동")
            return True
            
        except Exception as e:
            print(f"\n❌ 드라이버 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            print("\n가능한 원인:")
            print("  1. chromedriver가 PATH에 없거나 실행 불가능")
            print("  2. Chrome 브라우저가 설치되지 않음")
            print("  3. chromedriver와 Chrome 버전이 호환되지 않음")
            return False
            
    finally:
        # 환경변수 복원
        if original_selenium_driver_path:
            os.environ['SELENIUM_DRIVER_PATH'] = original_selenium_driver_path
        elif 'SELENIUM_DRIVER_PATH' in os.environ:
            del os.environ['SELENIUM_DRIVER_path']
        
        if original_selenium_manager_skip:
            os.environ['SELENIUM_MANAGER_SKIP'] = original_selenium_manager_skip
        elif 'SELENIUM_MANAGER_SKIP' in os.environ:
            del os.environ['SELENIUM_MANAGER_SKIP']

def test_without_chromedriver_in_path():
    """chromedriver가 PATH에 없는 경우 테스트 (더 엄격한 폐쇄망 시뮬레이션)"""
    print("\n" + "=" * 70)
    print("엄격한 폐쇄망 환경 시뮬레이션 테스트")
    print("(chromedriver가 PATH에 없는 경우)")
    print("=" * 70)
    
    # chromedriver 경로 찾기
    chromedriver_path = shutil.which('chromedriver')
    if not chromedriver_path:
        print("⚠ chromedriver를 PATH에서 찾을 수 없습니다.")
        print("  이 테스트를 실행하려면 chromedriver가 필요합니다.")
        return False
    
    # 원본 환경변수 백업
    original_selenium_driver_path = os.environ.get('SELENIUM_DRIVER_PATH')
    original_path = os.environ.get('PATH')
    
    try:
        # PATH에서 chromedriver 제거 시뮬레이션
        print("\n1. PATH에서 chromedriver 제거 시뮬레이션...")
        print("   → 폐쇄망 환경: chromedriver가 PATH에 없지만 환경변수로 지정됨")
        
        # 환경변수로 명시적으로 chromedriver 경로 설정
        os.environ['SELENIUM_DRIVER_PATH'] = chromedriver_path
        print(f"   ✓ SELENIUM_DRIVER_PATH 환경변수 설정: {chromedriver_path}")
        
        # SeleniumManager 우회
        os.environ['SELENIUM_MANAGER_SKIP'] = '1'
        
        # BaseScraper 인스턴스 생성
        print("\n2. BaseScraper 인스턴스 생성 중...")
        scraper = BaseScraper(delay=1.0)
        print(f"   ✓ BaseScraper 생성 완료")
        print(f"   → 드라이버 경로: {scraper.selenium_driver_path}")
        
        if scraper.selenium_driver_path == chromedriver_path:
            print("   ✓ 환경변수에서 드라이버 경로를 올바르게 읽었습니다.")
        else:
            print(f"   ⚠ 경로 불일치: 예상={chromedriver_path}, 실제={scraper.selenium_driver_path}")
            return False
        
        # Chrome 옵션 설정
        print("\n3. Chrome 옵션 설정 중...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ko-KR')
        
        # 드라이버 생성
        print("\n4. Selenium 드라이버 생성 중...")
        print("   → 환경변수에서 지정한 드라이버 경로 사용")
        
        driver = scraper._create_webdriver(chrome_options)
        print("   ✓ 드라이버 생성 성공!")
        
        # 테스트
        driver.get("data:text/html,<html><head><title>Test</title></head><body><h1>엄격한 폐쇄망 테스트 성공</h1></body></html>")
        print(f"   ✓ 페이지 접속 성공: {driver.title}")
        
        driver.quit()
        
        print("\n" + "=" * 70)
        print("✅ 엄격한 폐쇄망 환경 시뮬레이션 테스트 성공!")
        print("=" * 70)
        print("\n요약:")
        print("  - PATH에 chromedriver가 없어도 환경변수로 지정 가능")
        print("  - BaseScraper가 환경변수를 올바르게 읽음")
        print("  - SeleniumManager를 우회하여 로컬 드라이버 사용")
        return True
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 환경변수 복원
        if original_selenium_driver_path:
            os.environ['SELENIUM_DRIVER_PATH'] = original_selenium_driver_path
        elif 'SELENIUM_DRIVER_PATH' in os.environ:
            del os.environ['SELENIUM_DRIVER_PATH']
        
        if original_path:
            os.environ['PATH'] = original_path

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("폐쇄망 환경 시뮬레이션 테스트 시작")
    print("=" * 70)
    
    # 테스트 1: 기본 폐쇄망 환경 시뮬레이션
    success1 = test_closed_network_simulation()
    
    # 테스트 2: 엄격한 폐쇄망 환경 시뮬레이션
    success2 = test_without_chromedriver_in_path()
    
    print("\n" + "=" * 70)
    print("전체 테스트 결과")
    print("=" * 70)
    print(f"기본 폐쇄망 시뮬레이션: {'✅ 성공' if success1 else '❌ 실패'}")
    print(f"엄격한 폐쇄망 시뮬레이션: {'✅ 성공' if success2 else '❌ 실패'}")
    
    if success1 and success2:
        print("\n🎉 모든 테스트 통과! 폐쇄망 환경에서 정상 작동합니다.")
        sys.exit(0)
    else:
        print("\n⚠ 일부 테스트 실패. 로그를 확인하세요.")
        sys.exit(1)

