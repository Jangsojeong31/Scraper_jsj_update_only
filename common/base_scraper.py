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
from datetime import datetime
from pathlib import Path

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
    
    def __init__(self, delay: float = 1.0, selenium_driver_path: Optional[str] = None, log_to_file: bool = True, log_dir: Optional[str] = None):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            selenium_driver_path: 수동으로 설치한 ChromeDriver 경로
                (미지정 시 환경변수 → PATH 순으로 자동 탐지)
            log_to_file: 로그를 파일로 저장할지 여부
            log_dir: 로그 파일 저장 디렉토리 (None이면 output/logs 사용)
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
        
        # 로그 파일 설정
        self.log_to_file = log_to_file
        self.log_file = None
        self.original_print = None
        if self.log_to_file:
            self._init_log_file(log_dir)
    
    def _init_log_file(self, log_dir: Optional[str] = None):
        """
        로그 파일 초기화
        
        Args:
            log_dir: 로그 파일 저장 디렉토리 (None이면 output/logs 사용)
        """
        try:
            if log_dir is None:
                log_dir = Path('output') / 'logs'
            else:
                log_dir = Path(log_dir)
            
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 크롤러 클래스명 기반으로 로그 파일명 생성
            crawler_name = self.__class__.__name__.lower().replace('scraper', '').replace('crawler', '')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = log_dir / f"{crawler_name}_{timestamp}.log"
            
            self.log_file = open(log_filename, 'w', encoding='utf-8')
            self.log_file.write(f"=== 로그 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self.log_file.flush()
            
            print(f"로그 파일: {log_filename}")
        except Exception as e:
            print(f"⚠ 로그 파일 초기화 실패: {e}")
            self.log_to_file = False
            self.log_file = None
    
    def start_logging(self):
        """
        print 함수를 래핑하여 로그 파일에도 기록하도록 설정
        """
        if self.log_to_file and self.log_file:
            import builtins
            self.original_print = builtins.print
            
            def wrapped_print(*args, **kwargs):
                # 터미널에 출력
                self.original_print(*args, **kwargs)
                # 파일에도 출력
                try:
                    message = ' '.join(str(arg) for arg in args)
                    if kwargs.get('end', '\n') != '\n':
                        message += kwargs.get('end', '')
                    else:
                        message += '\n'
                    self.log_file.write(message)
                    self.log_file.flush()
                except Exception:
                    pass
            
            builtins.print = wrapped_print
    
    def stop_logging(self):
        """
        print 함수 래핑 해제 및 로그 파일 닫기
        """
        if self.log_to_file and self.log_file:
            import builtins
            if self.original_print:
                builtins.print = self.original_print
            
            try:
                self.log_file.write(f"=== 로그 종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                log_file_path = self.log_file.name
                self.log_file.close()
                print(f"로그 파일 저장 완료: {log_file_path}")
            except Exception as e:
                print(f"로그 파일 닫기 중 오류: {e}")
    
    def __del__(self):
        """소멸자: 로그 파일 닫기"""
        self.stop_logging()
    
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
    
    def normalize_date_format(self, date_str: str) -> str:
        """
        날짜 문자열을 YYYY-MM-DD 형식으로 정규화
        
        지원 형식:
        - YYYY-MM-DD
        - YYYY.MM.DD
        - YYYY/MM/DD
        - YYYYMMDD
        - YYYY. M. D. (공백 포함)
        - YYYY년 MM월 DD일
        
        Args:
            date_str: 정규화할 날짜 문자열
            
        Returns:
            YYYY-MM-DD 형식의 날짜 문자열 (변환 실패 시 원본 반환)
        """
        if not date_str:
            return ''
        
        import re
        from datetime import datetime
        
        date_str = str(date_str).strip()
        if not date_str:
            return ''
        
        # 이미 YYYY-MM-DD 형식인 경우
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # YYYYMMDD 형식 (예: 20250205)
        if re.match(r'^\d{8}$', date_str):
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # 다양한 날짜 형식 시도
        date_formats = [
            '%Y-%m-%d',
            '%Y.%m.%d',
            '%Y/%m/%d',
            '%Y. %m. %d.',
            '%Y년 %m월 %d일',
            '%Y-%m-%d %H:%M:%S',  # 날짜시간 형식도 처리
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # 정규표현식으로 직접 추출 시도
        # YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD 패턴
        match = re.search(r'(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})', date_str)
        if match:
            year = match.group(1)
            month = str(int(match.group(2))).zfill(2)
            day = str(int(match.group(3))).zfill(2)
            return f"{year}-{month}-{day}"
        
        # 변환 실패 시 원본 반환
        return date_str
    
    def normalize_date_fields(self, data: Dict) -> Dict:
        """
        딕셔너리의 날짜 필드들을 YYYY-MM-DD 형식으로 정규화
        
        Args:
            data: 정규화할 딕셔너리
            
        Returns:
            날짜 필드가 정규화된 딕셔너리
        """
        # 날짜 필드명 목록 (한글/영문 모두 포함)
        date_fields = [
            '제정일', '최근 개정일', '시행일', '공포일', '등록일', '작성일',
            'enactment_date', 'revision_date', 'execution_date', 'publication_date',
            'registration_date', 'created_date', 'date', 'period'
        ]
        
        normalized = data.copy()
        for field in date_fields:
            if field in normalized:
                normalized[field] = self.normalize_date_format(normalized[field])
        
        return normalized
    
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

