"""
Law_Scraper의 Selenium 드라이버 초기화 테스트 스크립트
폐쇄망 환경 대응 수정이 제대로 작동하는지 확인
"""
import sys
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

def test_selenium_init():
    """Selenium 드라이버 초기화 테스트"""
    print("=" * 60)
    print("Selenium 드라이버 초기화 테스트")
    print("=" * 60)
    
    try:
        # BaseScraper 인스턴스 생성 (Law_Scraper와 동일한 방식)
        print("\n1. BaseScraper 인스턴스 생성 중...")
        scraper = BaseScraper(delay=1.0)
        print(f"   ✓ BaseScraper 생성 완료")
        print(f"   → 드라이버 경로: {scraper.selenium_driver_path or '자동 탐지 예정'}")
        
        # Chrome 옵션 설정 (Law_Scraper와 동일)
        print("\n2. Chrome 옵션 설정 중...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ko-KR')
        print("   ✓ Chrome 옵션 설정 완료")
        
        # 드라이버 생성 (수정된 방식)
        print("\n3. Selenium 드라이버 생성 중...")
        print("   → BaseScraper._create_webdriver() 사용 (SeleniumManager 우회)")
        driver = scraper._create_webdriver(chrome_options)
        print("   ✓ 드라이버 생성 성공!")
        
        # 간단한 테스트 페이지 접속
        print("\n4. 테스트 페이지 접속 중...")
        driver.get("https://www.google.com")
        print(f"   ✓ 페이지 접속 성공: {driver.title}")
        
        # 드라이버 종료
        print("\n5. 드라이버 종료 중...")
        driver.quit()
        print("   ✓ 드라이버 종료 완료")
        
        print("\n" + "=" * 60)
        print("✅ 테스트 성공! Selenium 드라이버가 정상적으로 작동합니다.")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_selenium_init()
    sys.exit(0 if success else 1)

