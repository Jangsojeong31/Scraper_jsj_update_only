"""
기본 크롤러 클래스 - 모든 크롤러의 공통 기능 제공
"""
import os
import shutil
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
import json
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context

# SSL 경고 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL 컨텍스트 설정 (더 관대한 SSL 검증)
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # urllib3의 SSL 컨텍스트 생성 함수 사용
        try:
            ctx = create_urllib3_context()
        except:
            # 폴백: 기본 SSL 컨텍스트
            ctx = ssl.create_default_context()
        
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # 보안 레벨 낮춤
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except:
            pass
        
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


class BaseScraper:
    """모든 스크래퍼의 기본 클래스"""
    
    def __init__(self, delay: float = 1.0, selenium_driver_path: Optional[str] = None):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            selenium_driver_path: 수동으로 설치한 ChromeDriver 경로
                (미지정 시 환경변수 → PATH 순으로 자동 탐지)
        """
        self.delay = delay
        self.selenium_driver_path = self._resolve_driver_path(selenium_driver_path)
        if self.selenium_driver_path:
            # 외부망 차단 환경에서는 Selenium Manager 호출을 건너뛴다
            os.environ.setdefault('SELENIUM_MANAGER_SKIP', '1')
        self.session = requests.Session()
        # SSL 어댑터 마운트
        self.session.mount('https://', SSLAdapter())
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
    
    def fetch_page(self, url: str, use_selenium: bool = False, driver: Optional[webdriver.Chrome] = None) -> Optional[BeautifulSoup]:
        """
        웹 페이지를 가져와서 BeautifulSoup 객체로 반환
        
        Args:
            url: 크롤링할 URL
            use_selenium: Selenium을 사용할지 여부 (JavaScript 동적 로드 필요 시)
            driver: 기존 Selenium 드라이버 (재사용 가능)
            
        Returns:
            BeautifulSoup 객체 또는 None
        """
        try:
            print(f"크롤링 중: {url}")
            
            if use_selenium:
                # 기존 드라이버가 있으면 재사용, 없으면 새로 생성
                if driver is None:
                    chrome_options = self._build_default_chrome_options()
                    driver = self._create_webdriver(chrome_options)
                    created_driver = True
                else:
                    created_driver = False
                
                try:
                    driver.get(url)
                    time.sleep(2)  # 기본 렌더링 대기
                    html = driver.page_source
                finally:
                    # 새로 생성한 드라이버만 종료
                    if created_driver:
                        driver.quit()
                
                soup = BeautifulSoup(html, 'lxml')
            else:
                # SSL 검증 비활성화 및 재시도 로직
                max_retries = 3
                last_error = None
                for attempt in range(max_retries):
                    try:
                        response = self.session.get(url, timeout=30, verify=False)
                        response.raise_for_status()
                        
                        # 인코딩 처리 (한글 사이트를 위해)
                        response.encoding = response.apparent_encoding or 'utf-8'
                        
                        soup = BeautifulSoup(response.text, 'lxml')
                        break  # 성공하면 루프 종료
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # 2초, 4초, 6초 대기
                            print(f"  재시도 {attempt + 1}/{max_retries} ({wait_time}초 후)...")
                            time.sleep(wait_time)
                        else:
                            raise last_error
            
            time.sleep(self.delay)  # 서버 부하 방지
            
            return soup
        except Exception as e:
            print(f"에러 발생: {url} - {e}")
            return None

    def _build_default_chrome_options(self) -> Options:
        """내부망 호환을 고려한 기본 Chrome 옵션 생성"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ko-KR')
        return chrome_options

    def _create_webdriver(self, chrome_options: Options) -> webdriver.Chrome:
        """
        Selenium Manager를 우회하기 위해 명시적으로 드라이버 경로를 지정하여 WebDriver 생성
        """
        if self.selenium_driver_path:
            service = Service(executable_path=self.selenium_driver_path)
            return webdriver.Chrome(service=service, options=chrome_options)
        return webdriver.Chrome(options=chrome_options)

    def _resolve_driver_path(self, explicit_path: Optional[str]) -> Optional[str]:
        """
        드라이버 경로 우선순위
        1) 명시적 인자
        2) 환경변수 SELENIUM_DRIVER_PATH
        3) PATH 내 chromedriver 바이너리
        """
        if explicit_path:
            return explicit_path

        env_path = os.getenv('SELENIUM_DRIVER_PATH')
        if env_path:
            return env_path

        auto_path = shutil.which('chromedriver')
        return auto_path
    
    def save_results(self, data: Dict, filename: str = 'crawl_results.json'):
        """
        크롤링 결과를 JSON 파일로 저장
        
        Args:
            data: 저장할 데이터
            filename: 저장할 파일명
        """
        import os
        os.makedirs('output', exist_ok=True)
        filepath = os.path.join('output', filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n결과가 저장되었습니다: {filepath}")
    
    def save_results_csv(self, records: List[Dict], meta: Dict, filename: str = 'results.csv'):
        """
        크롤링 결과를 CSV 파일로 저장
        
        Args:
            records: 행 단위 데이터 리스트
            meta: 메타 정보 딕셔너리 (CSV에는 주석으로 저장)
            filename: 저장할 파일명
        """
        import os
        import csv
        os.makedirs('output', exist_ok=True)
        filepath = os.path.join('output', filename)

        if not records:
            print(f"저장할 데이터가 없습니다.")
            return

        # 모든 필드명 수집
        fieldnames = set()
        for item in records:
            fieldnames.update(item.keys())
        fieldnames = sorted(list(fieldnames))

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            # 메타 정보를 주석으로 저장
            f.write('# 메타 정보\n')
            for k, v in meta.items():
                f.write(f'# {k}: {v}\n')
            f.write('#\n')
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in records:
                csv_item = {}
                for key in fieldnames:
                    value = item.get(key, '')
                    # 문자열로 변환 (None은 빈 문자열로)
                    if value is None:
                        value = ''
                    elif not isinstance(value, str):
                        value = str(value)
                    # 줄바꿈을 공백으로 변환 (CSV 호환성)
                    value = value.replace('\n', ' ').replace('\r', ' ')
                    csv_item[key] = value
                writer.writerow(csv_item)

        print(f"\nCSV로 저장되었습니다: {filepath}")
    
    def save_debug_html(self, soup: BeautifulSoup, filename: str = None, enabled: bool = True):
        """
        디버깅용 HTML 파일 저장 (크롤러당 하나의 샘플만 저장)
        
        Args:
            soup: BeautifulSoup 객체
            filename: 저장할 파일명 (None이면 크롤러 클래스명 기반으로 자동 생성)
            enabled: 디버그 HTML 저장 활성화 여부
        """
        if not enabled or soup is None:
            return
        
        import os
        
        # 파일명이 없으면 크롤러 클래스명 기반으로 생성
        if filename is None:
            crawler_name = self.__class__.__name__.lower().replace('crawler', '')
            filename = f'debug_{crawler_name}_detail.html'
        
        # output/debug 디렉토리에 저장
        debug_dir = os.path.join('output', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        filepath = os.path.join(debug_dir, filename)
        
        try:
            # 파일이 이미 존재하면 저장하지 않음 (첫 번째 페이지만 저장)
            if os.path.exists(filepath):
                return
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            print(f"  디버깅용 HTML 저장: {filepath}")
        except Exception as e:
            print(f"  ⚠ 디버깅용 HTML 저장 실패: {e}")

