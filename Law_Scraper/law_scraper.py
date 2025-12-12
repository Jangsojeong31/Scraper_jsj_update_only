"""
법제처 - 국가법령정보센터 스크래퍼
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (common 모듈 import를 위해)
def find_project_root():
    """common 디렉토리를 찾을 때까지 상위 디렉토리로 이동"""
    try:
        # __file__이 있는 경우 (스크립트 실행)
        current = Path(__file__).resolve().parent
    except NameError:
        # __file__이 없는 경우 (인터랙티브 모드)
        current = Path.cwd()
    
    # common 디렉토리를 찾을 때까지 상위로 이동
    while current != current.parent:
        if (current / 'common').exists() and (current / 'common' / 'base_scraper.py').exists():
            return current
        current = current.parent
    
    # 찾지 못한 경우 현재 디렉토리 반환
    return Path.cwd()

project_root = find_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
import json
from urllib.parse import urljoin, quote_plus
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from common.base_scraper import BaseScraper
from common.file_comparator import FileComparator
from common.file_extractor import FileExtractor


class LawGoKrScraper(BaseScraper):
    """법제처 - 국가법령정보센터 스크래퍼"""
    
    # CSV 파일 경로 (기본값)
    DEFAULT_CSV_PATH = "Law_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: str = None):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            csv_path: 법령명 목록이 있는 CSV 파일 경로 (None이면 기본 경로 사용)
        """
        super().__init__(delay)
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        (self.output_dir / "downloads").mkdir(parents=True, exist_ok=True)
        # previous와 current 디렉토리 설정
        self.previous_dir = self.output_dir / "downloads" / "previous"
        self.current_dir = self.output_dir / "downloads" / "current"
        self.previous_dir.mkdir(parents=True, exist_ok=True)
        self.current_dir.mkdir(parents=True, exist_ok=True)
        # FileExtractor 초기화 (current 디렉토리 사용)
        self.file_extractor = FileExtractor(download_dir=str(self.current_dir), session=self.session)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=str(self.output_dir / "downloads"))
        
        # CSV 파일에서 법령명과 구분 정보 읽기
        self.law_items = self._load_target_laws_from_csv(csv_path or self.DEFAULT_CSV_PATH)
        self.law_name_lookup = {
            item.get('법령명', '').strip()
            for item in self.law_items
            if isinstance(item, dict)
        }
    
    def _remove_parentheses(self, text: str) -> str:
        """
        법령명에서 괄호와 그 내용을 제거하여 검색 키워드로 사용
        
        Args:
            text: 원본 법령명
            
        Returns:
            괄호가 제거된 검색 키워드
        """
        import re
        # 괄호와 그 내용 제거 (예: "국민연금법(제124조...)" -> "국민연금법")
        # 한글 괄호와 영문 괄호 모두 처리
        cleaned = re.sub(r'[\(（].*?[\)）]', '', text)
        return cleaned.strip()
    
    def _load_target_laws_from_csv(self, csv_path: str) -> List[Dict]:
        """
        CSV 파일에서 법령명과 구분 정보를 읽어옵니다.
        
        Args:
            csv_path: CSV 파일 경로 (형식: 구분,법령명)
            
        Returns:
            법령 정보 리스트 (각 항목은 {'법령명': str, '검색_키워드': str, '구분': str, '검색_URL': str} 형태)
        """
        import csv
        from pathlib import Path
        from urllib.parse import quote
        
        # 검색 URL 매핑
        search_urls = {
            '법령': 'https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query=',
            '감독규정': 'https://www.law.go.kr/admRulSc.do?menuId=5&subMenuId=41&tabMenuId=183&query=',
        }
        
        # 프로젝트 루트 기준으로 경로 해석
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            # 상대 경로인 경우 프로젝트 루트 기준으로 변환
            project_root = find_project_root()
            csv_file = project_root / csv_path
        
        if not csv_file.exists():
            print(f"⚠ CSV 파일을 찾을 수 없습니다: {csv_file}")
            print(f"  기본값을 사용합니다: 예금자보호법, 국세징수법, 부가가치세법")
            return [
                {'법령명': '예금자보호법', '검색_키워드': '예금자보호법', '구분': '법령', '검색_URL': search_urls['법령']},
                {'법령명': '국세징수법', '검색_키워드': '국세징수법', '구분': '법령', '검색_URL': search_urls['법령']},
                {'법령명': '부가가치세법', '검색_키워드': '부가가치세법', '구분': '법령', '검색_URL': search_urls['법령']},
            ]
        
        target_laws = []
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    law_name = row.get('법령명', '').strip()
                    division = row.get('구분', '').strip()
                    
                    if law_name:
                        # 구분에 맞는 검색 URL 선택
                        search_url = search_urls.get(division, search_urls['법령'])
                        
                        # 괄호 제거하여 검색 키워드 생성
                        search_keyword = self._remove_parentheses(law_name)
                        
                        target_laws.append({
                            '법령명': law_name,  # 원본 법령명 (괄호 포함)
                            '검색_키워드': search_keyword,  # 검색용 키워드 (괄호 제거)
                            '구분': division,
                            '검색_URL': search_url
                        })
            
            if target_laws:
                print(f"✓ CSV 파일에서 {len(target_laws)}개의 법령 정보를 읽었습니다: {csv_file}")
                division_counts = {}
                for item in target_laws:
                    div = item.get('구분', '')
                    division_counts[div] = division_counts.get(div, 0) + 1
                print(f"  구분별 통계: {', '.join([f'{k}: {v}개' for k, v in division_counts.items()])}")
            else:
                print(f"⚠ CSV 파일이 비어있습니다: {csv_file}")
                print(f"  기본값을 사용합니다: 예금자보호법, 국세징수법, 부가가치세법")
                return [
                    {'법령명': '예금자보호법', '검색_키워드': '예금자보호법', '구분': '법령', '검색_URL': search_urls['법령']},
                    {'법령명': '국세징수법', '검색_키워드': '국세징수법', '구분': '법령', '검색_URL': search_urls['법령']},
                    {'법령명': '부가가치세법', '검색_키워드': '부가가치세법', '구분': '법령', '검색_URL': search_urls['법령']},
                ]
        except Exception as e:
            print(f"⚠ CSV 파일 읽기 실패: {csv_file} - {e}")
            print(f"  기본값을 사용합니다: 예금자보호법, 국세징수법, 부가가치세법")
            return [
                {'법령명': '예금자보호법', '검색_키워드': '예금자보호법', '구분': '법령', '검색_URL': search_urls['법령']},
                {'법령명': '국세징수법', '검색_키워드': '국세징수법', '구분': '법령', '검색_URL': search_urls['법령']},
                {'법령명': '부가가치세법', '검색_키워드': '부가가치세법', '구분': '법령', '검색_URL': search_urls['법령']},
            ]
        
        return target_laws
    
    def is_target_law(self, law_name: str) -> bool:
        """
        법령명이 대상 법령 목록에 있는지 확인
        
        Args:
            law_name: 법령명
            
        Returns:
            대상 법령이면 True, 아니면 False
        """
        if not law_name:
            return False
        
        law_name_clean = law_name.strip()
        for target_name in self.law_name_lookup:
            # 정확히 일치하거나 포함되는 경우
            if target_name and (target_name in law_name_clean or law_name_clean in target_name):
                return True
        return False
    
    def _backup_current_to_previous(self) -> None:
        """스크래퍼 시작 시 current 디렉토리를 previous로 백업
        다음 실행 시 비교를 위해 현재 버전을 이전 버전으로 만듦
        """
        if not self.current_dir.exists():
            return
        
        # current 디렉토리에 파일이 있는지 확인
        files_in_current = [f for f in self.current_dir.glob("*") if f.is_file()]
        if not files_in_current:
            return
        
        print(f"  → 이전 버전 백업 중... (current → previous)")
        
        # previous 디렉토리 비우기
        import shutil
        if self.previous_dir.exists():
            for item in self.previous_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        
        # current의 파일들을 previous로 복사
        for file_path in files_in_current:
            shutil.copy2(file_path, self.previous_dir / file_path.name)
        
        # current 디렉토리 비우기 (새 파일만 남기기 위해)
        for file_path in files_in_current:
            file_path.unlink()
        
        print(f"  ✓ 이전 버전 백업 완료 ({len(files_in_current)}개 파일)")
    
    def _clear_diffs_directory(self) -> None:
        """스크래퍼 시작 시 diffs 디렉토리 비우기
        이전 실행의 diff 파일이 남아있어 혼동을 방지하기 위해
        """
        diffs_dir = self.output_dir / "downloads" / "diffs"
        if not diffs_dir.exists():
            return
        
        import shutil
        diff_files = list(diffs_dir.glob("*"))
        if not diff_files:
            return
        
        print(f"  → 이전 diff 파일 정리 중...")
        for item in diff_files:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        
        print(f"  ✓ diff 파일 정리 완료 ({len(diff_files)}개 파일)")
    
    def _find_previous_file(self, file_name: str) -> Optional[Path]:
        """previous 디렉토리에서 같은 파일명의 파일 찾기
        Args:
            file_name: 찾을 파일명
        Returns:
            이전 파일 경로 또는 None
        """
        previous_file = self.previous_dir / file_name
        if previous_file.exists():
            return previous_file
        return None
    
    def _compare_with_previous_file(self, new_file_path: str, file_name: str) -> None:
        """다운로드한 파일을 이전 파일과 비교
        Args:
            new_file_path: 새로 다운로드한 파일 경로
            file_name: 파일명
        """
        try:
            previous_file = self._find_previous_file(file_name)
            
            if not previous_file:
                print(f"  ✓ 새 파일 (이전 파일 없음)")
                return
            
            print(f"  → 이전 파일과 비교 중... (이전 파일: {previous_file})")
            comparison_result = self.file_comparator.compare_and_report(
                new_file_path,
                str(previous_file),
                save_diff=True
            )
            
            if comparison_result['changed']:
                print(f"  ✓ 파일 변경 감지: {comparison_result['diff_summary']}")
                if 'diff_file' in comparison_result:
                    print(f"    Diff 파일: {comparison_result['diff_file']}")
                    html_file = Path(comparison_result['diff_file']).with_suffix('.html')
                    if html_file.exists():
                        print(f"    HTML Diff 파일: {html_file}")
            else:
                print(f"  ✓ 파일 동일 (변경 없음)")
                
        except Exception as e:
            print(f"  ⚠ 파일 비교 중 오류: {e}")
            import traceback
            traceback.print_exc()
    
    def fetch_page(self, url: str, use_selenium: bool = False, driver: Optional[webdriver.Chrome] = None) -> Optional[BeautifulSoup]:
        """
        웹 페이지를 가져와서 BeautifulSoup 객체로 반환 (법령 검색 페이지 특화)
        
        Args:
            url: 스크래핑할 URL
            use_selenium: Selenium을 사용할지 여부 (JavaScript 동적 로드 필요 시)
            driver: 기존 Selenium 드라이버 (재사용 가능)
            
        Returns:
            BeautifulSoup 객체 또는 None
        """
        if use_selenium:
            # Selenium 사용 시 검색 결과 테이블 대기
            if driver is None:
                return super().fetch_page(url, use_selenium=True, driver=None)
            else:
                try:
                    driver.get(url)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#viewHeightDiv table, .result_table, table.tbl"))
                    )
                    time.sleep(2)
                    html = driver.page_source
                    return BeautifulSoup(html, 'lxml')
                except Exception as e:
                    print(f"에러 발생: {url} - {e}")
                    return None
        else:
            return super().fetch_page(url, use_selenium=False, driver=None)
    
    def extract_links(self, soup: BeautifulSoup, base_url: str = None) -> List[str]:
        """
        페이지에서 모든 링크 추출
        
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL (상대 경로를 절대 경로로 변환하기 위해)
            
        Returns:
            링크 URL 리스트
        """
        if soup is None:
            return []
        
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if base_url and not href.startswith('http'):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)
            links.append(href)
        
        return links
    
    def extract_text(self, soup: BeautifulSoup, selector: str = None) -> str:
        """
        페이지에서 텍스트 추출
        
        Args:
            soup: BeautifulSoup 객체
            selector: CSS 선택자 (선택적)
            
        Returns:
            추출된 텍스트
        """
        if soup is None:
            return ""
        
        if selector:
            elements = soup.select(selector)
            return ' '.join([elem.get_text(strip=True) for elem in elements])
        else:
            return soup.get_text(strip=True)
    
    def extract_law_info(self, soup: BeautifulSoup) -> Dict:
        """
        국가법령정보센터 페이지에서 법령 정보 추출
        
        Args:
            soup: BeautifulSoup 객체
            
        Returns:
            추출된 정보 딕셔너리
        """
        if soup is None:
            return {}
        
        info = {
            'title': '',
            'description': '',
            'links': [],
            'main_content': ''
        }
        
        # 제목 추출
        title_tag = soup.find('title')
        if title_tag:
            info['title'] = title_tag.get_text(strip=True)
        
        # 메타 설명 추출
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            info['description'] = meta_desc['content']
        
        # 주요 콘텐츠 영역 추출 (사이트 구조에 따라 조정 필요)
        # 국가법령정보센터의 주요 메뉴나 콘텐츠 영역을 찾아서 추출
        main_content = soup.find('main') or soup.find('div', class_='content') or soup.find('div', id='content')
        if main_content:
            info['main_content'] = main_content.get_text(strip=True, separator='\n')
        
        return info
    
    def _extract_file_links(self, soup: BeautifulSoup, base_url: str = "") -> Dict:
        """상세 페이지에서 파일 다운로드 링크 추출
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL
        Returns:
            {'file_names': [], 'download_links': []} 딕셔너리
        """
        file_info = {
            'file_names': [],
            'download_links': []
        }
        
        if soup is None:
            return file_info
        
        # 방법 1: 국가법령정보센터의 다운로드 버튼 (#bdySaveBtn) 우선 검색
        download_btn = soup.find('a', id='bdySaveBtn') or soup.select_one('#bdySaveBtn')
        if download_btn:
            href = download_btn.get('href', '')
            onclick = download_btn.get('onclick', '')
            
            # onclick에서 URL 추출 시도
            if not href or href == '#' or href.startswith('javascript:'):
                if onclick:
                    import re
                    # onclick에서 URL 패턴 찾기
                    url_patterns = [
                        r"['\"]([^'\"]*download[^'\"]*)['\"]",
                        r"['\"]([^'\"]*fileDown[^'\"]*)['\"]",
                        r"['\"]([^'\"]*\.pdf[^'\"]*)['\"]",
                        r"['\"]([^'\"]*\.hwp[^'\"]*)['\"]",
                        r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
                        r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]",
                    ]
                    for pattern in url_patterns:
                        match = re.search(pattern, onclick, re.IGNORECASE)
                        if match:
                            href = match.group(1)
                            break
            
            if href and not href.startswith('javascript:'):
                # 파일명 추출
                file_name = download_btn.get_text(strip=True)
                if not file_name or len(file_name) < 3:
                    # href에서 파일명 추출 시도
                    if href:
                        file_name = href.split('/')[-1].split('?')[0]
                        if not file_name or '.' not in file_name:
                            file_name = download_btn.get('title', '') or '파일'
                
                # URL 완성
                if base_url and not href.startswith('http'):
                    file_url = urljoin(base_url, href)
                else:
                    file_url = href
                
                if file_url:
                    file_info['file_names'].append(file_name)
                    file_info['download_links'].append(file_url)
                    print(f"  ✓ 파일 링크 발견 (#bdySaveBtn): {file_name} ({file_url[:80]})")
                    return file_info  # 찾았으면 바로 반환
        
        # 방법 2: 일반적인 파일 다운로드 링크 선택자
        file_selectors = [
            'a[href*="download"]',
            'a[href*="fileDown"]',
            'a[href*=".pdf"]',
            'a[href*=".hwp"]',
            'a[href*=".doc"]',
            'a[href*=".docx"]',
            '.file_download a',
            '.attach_file a',
            '#fileList a',
            '.file_list a',
            'a[onclick*="download"]',
            'a[onclick*="fileDown"]',
        ]
        
        for selector in file_selectors:
            file_links = soup.select(selector)
            if file_links:
                for link in file_links:
                    href = link.get('href', '')
                    onclick = link.get('onclick', '')
                    
                    # onclick에서 URL 추출 시도
                    if not href or href == '#' or href.startswith('javascript:'):
                        if onclick:
                            import re
                            # onclick에서 URL 패턴 찾기
                            url_patterns = [
                                r"['\"]([^'\"]*download[^'\"]*)['\"]",
                                r"['\"]([^'\"]*fileDown[^'\"]*)['\"]",
                                r"['\"]([^'\"]*\.pdf[^'\"]*)['\"]",
                                r"['\"]([^'\"]*\.hwp[^'\"]*)['\"]",
                            ]
                            for pattern in url_patterns:
                                match = re.search(pattern, onclick, re.IGNORECASE)
                                if match:
                                    href = match.group(1)
                                    break
                    
                    if not href or href.startswith('javascript:'):
                        continue
                    
                    # 파일명 추출
                    file_name = link.get_text(strip=True)
                    if not file_name or len(file_name) < 3:
                        # href에서 파일명 추출 시도
                        if href:
                            file_name = href.split('/')[-1].split('?')[0]
                            if not file_name or '.' not in file_name:
                                file_name = link.get('title', '') or link.get('alt', '') or '파일'
                    
                    # URL 완성
                    if base_url and not href.startswith('http'):
                        file_url = urljoin(base_url, href)
                    else:
                        file_url = href
                    
                    if file_url and file_url not in file_info['download_links']:
                        file_info['file_names'].append(file_name)
                        file_info['download_links'].append(file_url)
                        print(f"  ✓ 파일 링크 발견: {file_name} ({file_url[:80]})")
        
        # 방법 3: 국가법령정보센터 특정 구조 찾기
        # 파일 다운로드 버튼이나 링크가 있는 영역 찾기
        download_areas = soup.find_all(['div', 'span', 'td'], class_=lambda x: x and ('file' in str(x).lower() or 'download' in str(x).lower() or 'attach' in str(x).lower()))
        for area in download_areas:
            links = area.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if href and ('.pdf' in href.lower() or '.hwp' in href.lower() or 'download' in href.lower() or 'fileDown' in href.lower()):
                    if href not in file_info['download_links']:
                        file_name = link.get_text(strip=True) or href.split('/')[-1].split('?')[0] or '파일'
                        if base_url and not href.startswith('http'):
                            file_url = urljoin(base_url, href)
                        else:
                            file_url = href
                        file_info['file_names'].append(file_name)
                        file_info['download_links'].append(file_url)
                        print(f"  ✓ 파일 링크 발견 (영역 검색): {file_name} ({file_url[:80]})")
        
        return file_info
    
    def _download_file_with_selenium(self, driver, regulation_name: str = "") -> Optional[Dict]:
        """Selenium을 사용하여 팝업을 통해 파일 다운로드
        Args:
            driver: Selenium WebDriver 인스턴스
            regulation_name: 규정명 (파일명 생성용)
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            import re
            import os
            
            # #bdySaveBtn 버튼 찾기 및 클릭 (여러 방법 시도)
            save_btn = None
            
            # 방법 1: CSS 셀렉터로 찾기
            try:
                save_btn = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#bdySaveBtn"))
                )
                print(f"  ✓ 버튼 발견 (CSS 셀렉터)")
            except:
                pass
            
            # 방법 2: XPath로 찾기
            if not save_btn:
                try:
                    save_btn = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "/html/body/form[2]/div[1]/div[2]/div[1]/div[3]/a[5]"))
                    )
                    print(f"  ✓ 버튼 발견 (XPath)")
                except:
                    pass
            
            # 방법 3: 다른 XPath 패턴 시도
            if not save_btn:
                try:
                    # form[2]가 없을 수도 있으므로 다른 패턴 시도
                    xpath_patterns = [
                        "//a[@id='bdySaveBtn']",
                        "//a[contains(@class, 'btn_c') and @id='bdySaveBtn']",
                        "//a[@title='저장' and @id='bdySaveBtn']",
                        "//a[contains(@onclick, 'bdySavePrint')]",
                    ]
                    for xpath in xpath_patterns:
                        try:
                            save_btn = driver.find_element(By.XPATH, xpath)
                            if save_btn:
                                print(f"  ✓ 버튼 발견 (XPath: {xpath[:50]}...)")
                                break
                        except:
                            continue
                except:
                    pass
            
            # 방법 4: iframe 안에 있을 수 있으므로 iframe 확인
            found_in_iframe = False
            if not save_btn:
                try:
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    print(f"  → iframe {len(iframes)}개 발견, 확인 중...")
                    for iframe in iframes:
                        try:
                            driver.switch_to.frame(iframe)
                            save_btn = driver.find_element(By.CSS_SELECTOR, "#bdySaveBtn")
                            if save_btn:
                                print(f"  ✓ 버튼 발견 (iframe 내부)")
                                found_in_iframe = True
                                break
                        except:
                            driver.switch_to.default_content()
                            continue
                    if not save_btn:
                        driver.switch_to.default_content()
                except Exception as e:
                    print(f"  → iframe 확인 중 오류: {e}")
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass
            
            # 버튼을 찾지 못한 경우
            if not save_btn:
                print(f"  ⚠ #bdySaveBtn 버튼을 찾을 수 없습니다")
                print(f"  → 현재 페이지 URL: {driver.current_url}")
                print(f"  → 페이지 소스 일부 확인 중...")
                try:
                    # 페이지에서 'bdySaveBtn' 텍스트가 있는지 확인
                    page_source = driver.page_source
                    if 'bdySaveBtn' in page_source:
                        print(f"  → 페이지 소스에 'bdySaveBtn' 텍스트는 존재합니다")
                        # 모든 a 태그 확인
                        all_links = driver.find_elements(By.TAG_NAME, "a")
                        print(f"  → 페이지에 <a> 태그 {len(all_links)}개 발견")
                        for i, link in enumerate(all_links[:10]):  # 처음 10개만 확인
                            link_id = link.get_attribute('id')
                            link_class = link.get_attribute('class')
                            if link_id or (link_class and 'btn' in link_class):
                                print(f"    [{i}] id={link_id}, class={link_class}")
                    else:
                        print(f"  → 페이지 소스에 'bdySaveBtn' 텍스트가 없습니다")
                except Exception as e:
                    print(f"  → 페이지 소스 확인 중 오류: {e}")
                return None
            
            # 버튼 클릭
            try:
                print(f"  → 다운로드 버튼 클릭 중... (#bdySaveBtn)")
                # 스크롤하여 버튼이 보이도록
                driver.execute_script("arguments[0].scrollIntoView(true);", save_btn)
                time.sleep(0.5)
                # JavaScript로 클릭
                driver.execute_script("arguments[0].click();", save_btn)
                time.sleep(2)
                print(f"  ✓ 버튼 클릭 완료")
            except Exception as e:
                print(f"  ⚠ 버튼 클릭 실패: {e}")
                return None
            
            # iframe에서 찾았으면 default content로 복귀
            if found_in_iframe:
                try:
                    driver.switch_to.default_content()
                    print(f"  → 메인 컨텍스트로 복귀")
                except:
                    pass
            
            # 팝업이 나타날 시간 대기 (모달/div로 같은 페이지에 나타남)
            print(f"  → 팝업 대기 중...")
            # WebDriverWait로 팝업 요소가 나타날 때까지 대기 (최대 3초, 실제로는 더 빠르게)
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#aBtnOutPutSave, input[type='radio']"))
                )
            except:
                time.sleep(1)  # fallback
            
            # 라디오 버튼 선택 (DOC → PDF → HWP 순서로 시도)
            radio_selected = False
            selected_format = None  # 선택된 형식 저장
            radio_buttons = [
                {
                    'name': 'DOC',
                    'xpath': '/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[1]/div[4]/input',
                    'selector': 'input[type="radio"][value*="doc" i], input[type="radio"][value*="DOC"]'
                },
                {
                    'name': 'PDF',
                    'xpath': '/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[1]/div[3]/input',
                    'selector': 'input[type="radio"][value*="pdf" i], input[type="radio"][value*="PDF"]'
                },
                {
                    'name': 'HWP',
                    'xpath': '/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[1]/div[1]/input',
                    'selector': 'input[type="radio"][value*="hwp" i], input[type="radio"][value*="HWP"]'
                }
            ]
            
            for radio_info in radio_buttons:
                radio_btn = None
                # 방법 1: XPath로 찾기
                try:
                    radio_btn = driver.find_element(By.XPATH, radio_info['xpath'])
                    print(f"  ✓ {radio_info['name']} 라디오 버튼 발견 (XPath)")
                except:
                    # 방법 2: CSS 셀렉터로 찾기
                    try:
                        radio_btn = driver.find_element(By.CSS_SELECTOR, radio_info['selector'])
                        print(f"  ✓ {radio_info['name']} 라디오 버튼 발견 (CSS 셀렉터)")
                    except:
                        pass
                
                if radio_btn:
                    try:
                        # 라디오 버튼이 이미 선택되어 있는지 확인
                        if not radio_btn.is_selected():
                            # JavaScript로 클릭하여 선택
                            driver.execute_script("arguments[0].click();", radio_btn)
                            time.sleep(0.3)  # 최소 대기 시간으로 줄임
                            
                            # 선택이 실제로 반영되었는지 확인 (빠른 검증)
                            is_actually_selected = False
                            try:
                                # 방법 1: is_selected() 확인
                                is_actually_selected = radio_btn.is_selected()
                            except:
                                pass
                            
                            if not is_actually_selected:
                                # 방법 2: checked 속성 확인
                                try:
                                    is_actually_selected = driver.execute_script("return arguments[0].checked;", radio_btn)
                                except:
                                    pass
                            
                            if is_actually_selected:
                                print(f"  ✓ {radio_info['name']} 라디오 버튼 선택 완료 (검증됨)")
                            else:
                                print(f"  ⚠ {radio_info['name']} 라디오 버튼 선택 실패 (검증 실패)")
                                # 다시 시도
                                driver.execute_script("arguments[0].checked = true; arguments[0].click();", radio_btn)
                                time.sleep(0.3)  # 재시도 대기 시간도 줄임
                                # 최종 확인
                                try:
                                    if radio_btn.is_selected() or driver.execute_script("return arguments[0].checked;", radio_btn):
                                        print(f"  ✓ {radio_info['name']} 라디오 버튼 선택 완료 (재시도 성공)")
                                        is_actually_selected = True
                                except:
                                    pass
                        else:
                            print(f"  ✓ {radio_info['name']} 라디오 버튼이 이미 선택되어 있음")
                            is_actually_selected = True
                        
                        if is_actually_selected:
                            radio_selected = True
                            selected_format = radio_info['name']  # 선택된 형식 저장
                            break
                    except Exception as e:
                        print(f"  ⚠ {radio_info['name']} 라디오 버튼 선택 실패: {e}")
                        continue
            
            if not radio_selected:
                print(f"  ⚠ 라디오 버튼을 찾을 수 없습니다 (계속 진행)")
            
            # #aBtnOutPutSave 버튼 찾기 (여러 방법 시도)
            download_btn = None
            
            # 방법 1: CSS 셀렉터
            try:
                download_btn = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#aBtnOutPutSave"))
                )
                print(f"  ✓ 저장 버튼 발견 (CSS 셀렉터)")
            except:
                pass
            
            # 방법 2: XPath
            if not download_btn:
                try:
                    download_btn = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, "/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[2]/a[1]"))
                    )
                    print(f"  ✓ 저장 버튼 발견 (XPath)")
                except:
                    pass
            
            # 방법 3: 다른 XPath 패턴들
            if not download_btn:
                xpath_patterns = [
                    "//a[@id='aBtnOutPutSave']",
                    "//a[contains(@onclick, 'beforeSavePrint')]",
                    "//a[@href='#AJAX' and @id='aBtnOutPutSave']",
                ]
                for xpath in xpath_patterns:
                    try:
                        download_btn = driver.find_element(By.XPATH, xpath)
                        if download_btn:
                            print(f"  ✓ 저장 버튼 발견 (XPath: {xpath[:50]}...)")
                            break
                    except:
                        continue
            
            # 버튼을 찾지 못한 경우
            if not download_btn:
                print(f"  ⚠ #aBtnOutPutSave 버튼을 찾을 수 없습니다")
                return None
            
            # 버튼 클릭
            try:
                print(f"  → 다운로드 실행 버튼 클릭 중... (#aBtnOutPutSave)")
                # 스크롤하여 버튼이 보이도록
                driver.execute_script("arguments[0].scrollIntoView(true);", download_btn)
                time.sleep(0.3)  # 스크롤 대기 시간 줄임
                # JavaScript로 클릭
                driver.execute_script("arguments[0].click();", download_btn)
                print(f"  ✓ 버튼 클릭 완료")
                
                # 파일 다운로드 시작 대기 (최소 시간)
                time.sleep(1.5)  # 3초에서 1.5초로 줄임
            except Exception as e:
                print(f"  ⚠ 버튼 클릭 실패: {e}")
                return None
            
            # 다운로드된 파일 찾기 (current 디렉토리에서 최근 파일)
            # 파일이 실제로 다운로드될 때까지 대기 (최대 10초, 폴링 방식)
            max_wait = 10
            wait_interval = 0.5
            waited = 0
            files_before = set(self.current_dir.glob("*"))
            
            while waited < max_wait:
                time.sleep(wait_interval)
                waited += wait_interval
                files_after = set(self.current_dir.glob("*"))
                new_files = files_after - files_before
                # .crdownload 파일이 없고 새 파일이 있으면 다운로드 완료
                crdownload_files = [f for f in new_files if f.name.endswith('.crdownload')]
                if not crdownload_files and new_files:
                    break
            
            # current 디렉토리에서 최근 파일 찾기
            downloaded_files = list(self.current_dir.glob("*"))
            if not downloaded_files:
                print(f"  ⚠ 다운로드된 파일을 찾을 수 없습니다")
                return None
            
            # 가장 최근 파일 선택
            latest_file = max(downloaded_files, key=lambda p: p.stat().st_mtime if p.is_file() else 0)
            
            if not latest_file.is_file():
                print(f"  ⚠ 다운로드된 파일이 아닙니다")
                return None
            
            # 다운로드된 파일의 확장자 확인
            downloaded_ext = latest_file.suffix.lower()
            
            # 선택한 형식과 다운로드된 파일의 확장자 일치 여부 확인
            if selected_format:
                expected_exts = {
                    'DOC': ['.doc', '.docx'],
                    'PDF': ['.pdf'],
                    'HWP': ['.hwp']
                }
                expected_exts_list = expected_exts.get(selected_format, [])
                
                if expected_exts_list and downloaded_ext not in expected_exts_list:
                    print(f"  ⚠ 경고: {selected_format} 형식을 선택했지만 다운로드된 파일은 {downloaded_ext} 형식입니다.")
                    print(f"  → 다운로드된 파일: {latest_file.name}")
                else:
                    print(f"  ✓ {selected_format} 형식으로 다운로드 확인: {downloaded_ext}")
            
            # 파일명 생성 (규정명 기반)
            if regulation_name:
                safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                ext = latest_file.suffix or '.pdf'
                safe_filename = f"{safe_reg_name}{ext}"
            else:
                safe_filename = latest_file.name
            
            # 파일명 변경 (규정명 기반으로)
            new_file_path = self.current_dir / safe_filename
            if latest_file != new_file_path:
                if new_file_path.exists():
                    new_file_path.unlink()
                latest_file.rename(new_file_path)
                print(f"  ✓ 파일 저장: {new_file_path}")
            else:
                print(f"  ✓ 파일 저장: {new_file_path}")
            
            # 이전 파일과 비교
            previous_file_path = self.previous_dir / safe_filename
            comparison_result = None
            
            if previous_file_path.exists():
                print(f"  → 이전 파일과 비교 중...")
                comparison_result = self.file_comparator.compare_and_report(
                    str(new_file_path),
                    str(previous_file_path),
                    save_diff=True
                )
                
                if comparison_result['changed']:
                    print(f"  ✓ 파일 변경 감지: {comparison_result['diff_summary']}")
                else:
                    print(f"  ✓ 파일 동일 (변경 없음)")
            else:
                print(f"  ✓ 새 파일 (이전 파일 없음)")
            
            # 파일 URL과 파일명 반환 (결과에 포함하기 위해)
            return {
                'file_path': str(new_file_path),
                'file_url': '',  # 팝업을 통한 다운로드이므로 URL 없음
                'file_name': safe_filename,
                'previous_file_path': str(previous_file_path) if previous_file_path.exists() else None,
                'comparison': comparison_result,
            }
            
        except Exception as e:
            print(f"  ⚠ Selenium 파일 다운로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _download_and_compare_file(self, file_url: str, file_name: str, regulation_name: str = "") -> Optional[Dict]:
        """파일 다운로드 및 이전 파일과 비교
        Args:
            file_url: 다운로드 URL
            file_name: 파일명
            regulation_name: 규정명 (이전 파일 매칭용)
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            import re
            import os
            # 안전한 파일명 생성
            if regulation_name:
                safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                ext = Path(file_name).suffix if file_name else '.pdf'
                safe_filename = f"{safe_reg_name}{ext}"
            else:
                safe_filename = re.sub(r'[^\w\s.-]', '', file_name).replace(' ', '_')
            
            # 새 파일 다운로드 경로 (current 디렉토리)
            new_file_path = self.current_dir / safe_filename
            
            # 이전 파일 경로 (previous 디렉토리)
            previous_file_path = self.previous_dir / safe_filename
            
            # 파일 다운로드
            print(f"  → 파일 다운로드 중: {file_name}")
            downloaded_result = self.file_extractor.download_file(
                file_url,
                safe_filename,
                use_selenium=False,
                driver=None
            )
            
            if downloaded_result:
                downloaded_path, actual_filename = downloaded_result
            else:
                downloaded_path, actual_filename = None, None
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                print(f"  ⚠ 파일 다운로드 실패")
                return None
            
            # 다운로드한 파일을 새 파일 경로로 이동/복사
            if str(downloaded_path) != str(new_file_path):
                import shutil
                if new_file_path.exists():
                    new_file_path.unlink()
                shutil.move(downloaded_path, new_file_path)
                print(f"  ✓ 파일 저장: {new_file_path}")
            
            # 이전 파일과 비교
            comparison_result = None
            if previous_file_path.exists():
                print(f"  → 이전 파일과 비교 중...")
                comparison_result = self.file_comparator.compare_and_report(
                    str(new_file_path),
                    str(previous_file_path),
                    save_diff=True
                )
                
                if comparison_result['changed']:
                    print(f"  ✓ 파일 변경 감지: {comparison_result['diff_summary']}")
                else:
                    print(f"  ✓ 파일 동일 (변경 없음)")
            else:
                print(f"  ✓ 새 파일 (이전 파일 없음)")
            
            return {
                'file_path': str(new_file_path),
                'previous_file_path': str(previous_file_path) if previous_file_path.exists() else None,
                'comparison': comparison_result,
            }
            
        except Exception as e:
            print(f"  ⚠ 파일 다운로드/비교 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def extract_enactment_and_revision_dates_from_list(self, driver, law_name: str = "") -> Dict[str, str]:
        """
        검색 결과 목록에서 부칙 버튼을 클릭하여 부칙 목록의 날짜 추출 (테스트용)
        
        Args:
            driver: Selenium WebDriver 인스턴스
            law_name: 법령명 (디버깅용)
            
        Returns:
            {'enactment_date': str, 'revision_date': str} 딕셔너리
        """
        from datetime import datetime
        import re
        
        result = {
            'enactment_date': '',
            'revision_date': ''
        }
        
        try:
            # 검색 결과 목록에서 부칙 버튼 찾기
            # 패턴: #liBgcolor1 > div > ul > li:nth-child(2) > a (부칙 버튼)
            print(f"    → 검색 결과 목록에서 부칙 버튼 찾는 중...")
            
            ar_button = None
            
            # 방법 1: class="on"인 liBgcolor 요소에서 부칙 버튼 찾기
            try:
                # 모든 liBgcolor 요소 찾기
                all_li_elements = driver.find_elements(By.CSS_SELECTOR, "li[id^='liBgcolor']")
                print(f"    → liBgcolor 요소 {len(all_li_elements)}개 발견")
                
                # class="on"인 항목 찾기
                li_on_element = None
                for li_elem in all_li_elements:
                    li_class = li_elem.get_attribute('class') or ''
                    if 'on' in li_class:
                        li_on_element = li_elem
                        print(f"    ✓ class='on'인 liBgcolor 항목 발견 (ID: {li_elem.get_attribute('id')})")
                        break
                
                if li_on_element:
                    # #liBgcolor > div > ul > li:nth-child(2) > a 패턴 (부칙 버튼)
                    ar_buttons = li_on_element.find_elements(By.CSS_SELECTOR, "div > ul > li:nth-child(2) > a")
                    if not ar_buttons:
                        # 대체 패턴: div > ul > li > a (부칙 관련, onclick에 SpanAr 포함)
                        ar_buttons = li_on_element.find_elements(By.XPATH, ".//div//ul//li[2]//a[contains(@onclick, 'SpanAr')]")
                    if not ar_buttons:
                        # onclick에 'SpanAr'이 포함된 모든 a 태그
                        ar_buttons = li_on_element.find_elements(By.XPATH, ".//a[contains(@onclick, 'SpanAr')]")
                    
                    if ar_buttons:
                        ar_button = ar_buttons[0]
                        print(f"    ✓ class='on' 항목에서 부칙 버튼 발견")
            except Exception as e:
                print(f"    ⚠ class='on' 항목에서 부칙 버튼 찾기 실패: {e}")
            
            # 방법 2: class="on"인 항목을 찾지 못한 경우, 모든 liBgcolor 요소에서 찾기
            if not ar_button:
                try:
                    all_li_elements = driver.find_elements(By.CSS_SELECTOR, "li[id^='liBgcolor']")
                    for li_elem in all_li_elements:
                        ar_buttons = li_elem.find_elements(By.XPATH, ".//div//ul//li[2]//a[contains(@onclick, 'SpanAr')]")
                        if not ar_buttons:
                            ar_buttons = li_elem.find_elements(By.XPATH, ".//a[contains(@onclick, 'SpanAr')]")
                        
                        if ar_buttons:
                            ar_button = ar_buttons[0]
                            print(f"    ✓ liBgcolor 항목에서 부칙 버튼 발견 (ID: {li_elem.get_attribute('id')})")
                            break
                except Exception as e:
                    print(f"    ⚠ liBgcolor 요소에서 부칙 버튼 찾기 실패: {e}")
            
            # 방법 3: 일반적인 패턴으로 찾기
            if not ar_button:
                try:
                    xpath_patterns = [
                        "//li[@id='liBgcolor1']//div//ul//li[2]//a[contains(@onclick, 'SpanAr')]",
                        "//li[starts-with(@id, 'liBgcolor')]//div//ul//li[2]//a[contains(@onclick, 'SpanAr')]",
                        "//a[contains(@onclick, 'fSelectJoListAncTree') and contains(@onclick, 'SpanAr')]",
                    ]
                    
                    for xpath in xpath_patterns:
                        try:
                            ar_button = driver.find_element(By.XPATH, xpath)
                            if ar_button:
                                print(f"    ✓ 부칙 버튼 발견 (XPath)")
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"    ⚠ 부칙 버튼 찾기 실패 (XPath): {e}")
            
            if not ar_button:
                print(f"    ⚠ 검색 결과 목록에서 부칙 버튼을 찾을 수 없습니다.")
                return result
            
            # 부칙 버튼 클릭 (접힌 상태를 열기)
            try:
                print(f"    → 부칙 버튼 클릭 중... (접힌 목록 열기)")
                driver.execute_script("arguments[0].scrollIntoView(true);", ar_button)
                time.sleep(0.3)
                
                # 부칙 목록이 이미 열려있는지 확인
                li_id = None
                try:
                    # 부칙 버튼의 onclick에서 li ID 추출
                    onclick = ar_button.get_attribute('onclick') or ''
                    import re
                    id_match = re.search(r"['\"]liBgcolor(\d+)['\"]", onclick)
                    if id_match:
                        li_id = f"liBgcolor{id_match.group(1)}"
                except:
                    pass
                
                # 부칙 목록이 닫혀있는지 확인 (SpanAr이 숨겨져 있는지)
                is_closed = True
                if li_id:
                    try:
                        span_ar = driver.find_element(By.CSS_SELECTOR, f"#{li_id}SpanAr")
                        # display 스타일 확인
                        display_style = span_ar.value_of_css_property('display')
                        if display_style and display_style != 'none':
                            is_closed = False
                    except:
                        pass
                
                if is_closed:
                    # 부칙 버튼 클릭하여 열기
                    driver.execute_script("arguments[0].click();", ar_button)
                    time.sleep(0.5)  # 클릭 후 짧은 대기
                    
                    # 부칙 목록이 열릴 때까지 대기
                    if li_id:
                        try:
                            WebDriverWait(driver, 3).until(
                                lambda d: d.find_element(By.CSS_SELECTOR, f"#{li_id}SpanAr").value_of_css_property('display') != 'none'
                            )
                            print(f"    ✓ 부칙 목록이 열렸습니다")
                        except:
                            print(f"    ⚠ 부칙 목록 열기 대기 시간 초과")
                    else:
                        time.sleep(1)  # 대체 대기
                else:
                    print(f"    ✓ 부칙 목록이 이미 열려있습니다")
                
                print(f"    ✓ 부칙 버튼 클릭 완료")
            except Exception as e:
                print(f"    ⚠ 부칙 버튼 클릭 실패: {e}")
                import traceback
                traceback.print_exc()
                return result
            
            # 부칙 목록이 나타날 때까지 대기 (더 확실하게)
            try:
                if li_id:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, f"#{li_id}SpanAr ul li"))
                    )
                else:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[id^='liBgcolor'][id$='SpanAr'] ul li"))
                    )
                print(f"    ✓ 부칙 목록 로드 완료")
                time.sleep(0.5)  # 추가 안정화 대기
            except Exception as e:
                print(f"    ⚠ 부칙 목록 로드 대기 시간 초과: {e}")
                # 계속 진행 (이미 열려있을 수 있음)
            
            # 부칙 목록에서 날짜 링크 추출
            # 패턴: #liBgcolor1SpanAr > ul > li > ul > li:nth-child(1) > a
            date_elements = []
            date_pattern = re.compile(r'\d{4}\s*[.\-]\s*\d{1,2}\s*[.\-]\s*\d{1,2}')
            
            try:
                # 부칙 목록 영역 찾기 (li_id가 있으면 우선 사용)
                ar_list_area = None
                
                if li_id:
                    try:
                        ar_list_area = driver.find_element(By.CSS_SELECTOR, f"#{li_id}SpanAr")
                        print(f"    ✓ 부칙 목록 영역 발견: #{li_id}SpanAr")
                    except:
                        pass
                
                if not ar_list_area:
                    # 대체 방법: 일반적인 패턴으로 찾기
                    ar_list_selectors = [
                        "[id^='liBgcolor'][id$='SpanAr']",
                        "div[id^='liBgcolor'][id$='SpanAr']",
                    ]
                    
                    for selector in ar_list_selectors:
                        try:
                            ar_list_area = driver.find_element(By.CSS_SELECTOR, selector)
                            if ar_list_area:
                                print(f"    ✓ 부칙 목록 영역 발견: {selector}")
                                break
                        except:
                            continue
                
                if ar_list_area:
                    # 부칙 목록이 실제로 보이는지 확인
                    try:
                        display_style = ar_list_area.value_of_css_property('display')
                        if display_style == 'none':
                            print(f"    ⚠ 부칙 목록이 숨겨져 있습니다 (display: none)")
                    except:
                        pass
                    
                    # 부칙 목록의 모든 링크 찾기 (여러 패턴 시도)
                    ar_links = []
                    
                    # 패턴 1: ul li ul li a (일반적인 구조)
                    ar_links = ar_list_area.find_elements(By.CSS_SELECTOR, "ul li ul li a")
                    if not ar_links:
                        # 패턴 2: ul > li > ul > li > a
                        ar_links = ar_list_area.find_elements(By.CSS_SELECTOR, "ul > li > ul > li > a")
                    if not ar_links:
                        # 패턴 3: 모든 a 태그
                        ar_links = ar_list_area.find_elements(By.CSS_SELECTOR, "a")
                    
                    print(f"    → 부칙 목록 링크 {len(ar_links)}개 발견")
                    
                    for link in ar_links:
                        try:
                            # 링크가 보이는지 확인
                            if not link.is_displayed():
                                continue
                            
                            link_text = link.text.strip()
                            # title 속성도 확인
                            title_text = link.get_attribute('title') or ''
                            
                            # 날짜 패턴 확인 (링크 텍스트와 title 모두)
                            for text in [link_text, title_text]:
                                if text and date_pattern.search(text):
                                    date_match = date_pattern.search(text)
                                    if date_match:
                                        date_str = date_match.group(0).strip()
                                        if date_str not in date_elements:
                                            date_elements.append(date_str)
                                            print(f"    ✓ 날짜 발견: {date_str} (텍스트: {text[:50]})")
                                            break
                        except Exception as e:
                            continue
                    
                    # 링크에서 날짜를 찾지 못한 경우, 부칙 목록 전체 텍스트에서 날짜 찾기
                    if not date_elements:
                        try:
                            ar_list_text = ar_list_area.text
                            all_dates = date_pattern.findall(ar_list_text)
                            for date_str in all_dates:
                                date_str = date_str.strip()
                                if date_str not in date_elements:
                                    date_elements.append(date_str)
                                    print(f"    ✓ 날짜 발견 (전체 텍스트): {date_str}")
                        except Exception as e:
                            pass
                else:
                    # 대체 방법: 페이지 소스에서 찾기
                    print(f"    → Selenium 요소를 찾지 못해 HTML 소스에서 검색 중...")
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'lxml')
                    ar_div = soup.find('div', id=lambda x: x and x.startswith('liBgcolor') and x.endswith('SpanAr'))
                    if ar_div:
                        # display:none이 아닌지 확인
                        style = ar_div.get('style', '')
                        if 'display:none' not in style and 'display: none' not in style:
                            all_links = ar_div.find_all('a')
                            for link in all_links:
                                link_text = link.get_text(strip=True)
                                if date_pattern.search(link_text):
                                    date_match = date_pattern.search(link_text)
                                    if date_match:
                                        date_str = date_match.group(0).strip()
                                        if date_str not in date_elements:
                                            date_elements.append(date_str)
                                            print(f"    ✓ 날짜 발견 (HTML): {date_str}")
            except Exception as e:
                print(f"    ⚠ 부칙 목록에서 날짜 추출 실패: {e}")
                import traceback
                traceback.print_exc()
            
            if not date_elements:
                print(f"    ⚠ 부칙 목록에서 날짜를 찾을 수 없습니다.")
                return result
            
            # 날짜 파싱 및 정렬
            parsed_dates = []
            for date_str in date_elements:
                cleaned_date = re.sub(r'\s+', '', date_str)
                normalized_date = cleaned_date.replace('.', '-')
                
                parsed_date = None
                try:
                    date_match = re.search(r'(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})', normalized_date)
                    if date_match:
                        year, month, day = date_match.groups()
                        date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        parsed_date = datetime.strptime(date_str_formatted, '%Y-%m-%d')
                except ValueError:
                    continue
                
                if parsed_date:
                    parsed_dates.append((parsed_date, date_str))
            
            if not parsed_dates:
                print(f"    ⚠ 날짜 파싱 실패 (발견된 날짜 문자열: {date_elements})")
                return result
            
            # 날짜 정렬 (오래된 순)
            parsed_dates.sort(key=lambda x: x[0])
            
            # 가장 오래된 날짜 = 제정일
            result['enactment_date'] = parsed_dates[0][1]
            
            # 가장 최근 날짜 = 최근 개정일 (날짜가 2개 이상일 때만 설정)
            if len(parsed_dates) > 1:
                result['revision_date'] = parsed_dates[-1][1]
            else:
                result['revision_date'] = ''  # 날짜가 하나만 있으면 최근 개정일은 비움
            
            print(f"    ✓ 날짜 추출 완료: 제정일={result['enactment_date']}, 최근 개정일={result['revision_date']} (발견된 날짜: {len(parsed_dates)}개)")
            
        except Exception as e:
            print(f"    ⚠ 부칙 목록에서 날짜 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    def extract_enactment_and_revision_dates(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        법령 상세 페이지의 부칙 영역에서 제정일과 최근 개정일 추출
        
        Args:
            soup: BeautifulSoup 객체 (법령 상세 페이지)
            
        Returns:
            {'enactment_date': str, 'revision_date': str} 딕셔너리
        """
        from datetime import datetime
        import re
        
        result = {
            'enactment_date': '',
            'revision_date': ''
        }
        
        if soup is None:
            return result
        
        # 부칙 영역 찾기 (#arDivArea)
        ar_div_area = soup.find('div', id='arDivArea')
        if not ar_div_area:
            # CSS 선택자로도 시도
            ar_div_area = soup.select_one('#arDivArea')
        
        # 다른 가능한 ID나 클래스로도 시도
        if not ar_div_area:
            # '부칙' 텍스트가 포함된 div 찾기
            all_divs = soup.find_all('div')
            for div in all_divs:
                div_text = div.get_text(strip=True)
                if '부칙' in div_text and len(div_text) < 100:  # 제목 정도의 길이
                    # 부칙 제목 div의 다음 형제나 부모 찾기
                    parent = div.parent
                    if parent:
                        ar_div_area = parent
                        break
        
        if not ar_div_area:
            # 디버깅: 부칙 영역을 찾지 못한 경우
            print(f"    ⚠ 부칙 영역(#arDivArea)을 찾을 수 없습니다.")
            return result
        
        # 부칙 영역 내의 모든 날짜 링크 찾기
        # 예: p.pty3 > a > span 또는 다른 패턴
        date_elements = []
        
        # 날짜 패턴 (공백 포함 가능: "2025. 4. 22." 형식도 처리)
        date_pattern = re.compile(r'\d{4}\s*[.\-]\s*\d{1,2}\s*[.\-]\s*\d{1,2}')
        
        # 방법 1: span 태그 내의 날짜 텍스트 찾기 (부칙 날짜 링크)
        date_spans = ar_div_area.find_all('span')
        for span in date_spans:
            span_text = span.get_text(strip=True)
            # 날짜 형식 확인 (YYYY.MM.DD 또는 YYYY-MM-DD 등, 공백 포함 가능)
            if date_pattern.search(span_text):
                date_match = date_pattern.search(span_text)
                if date_match:
                    date_elements.append(date_match.group(0).strip())
        
        # 방법 2: a 태그 내의 날짜 텍스트 찾기
        date_links = ar_div_area.find_all('a')
        for link in date_links:
            link_text = link.get_text(strip=True)
            # 날짜 형식 확인
            if date_pattern.search(link_text):
                date_match = date_pattern.search(link_text)
                if date_match:
                    date_str = date_match.group(0).strip()
                    if date_str not in date_elements:
                        date_elements.append(date_str)
        
        # 방법 3: p.pty3 클래스를 가진 요소 내의 날짜 찾기
        pty3_elements = ar_div_area.find_all('p', class_='pty3')
        for pty3 in pty3_elements:
            # pty3 내의 모든 a 태그와 span 태그 확인
            for elem in pty3.find_all(['a', 'span']):
                elem_text = elem.get_text(strip=True)
                if date_pattern.search(elem_text):
                    date_match = date_pattern.search(elem_text)
                    if date_match:
                        date_str = date_match.group(0).strip()
                        if date_str not in date_elements:
                            date_elements.append(date_str)
        
        # 방법 4: 부칙 영역 전체 텍스트에서 날짜 패턴 찾기
        if not date_elements:
            ar_div_text = ar_div_area.get_text()
            all_dates = date_pattern.findall(ar_div_text)
            for date_str in all_dates:
                date_str = date_str.strip()
                if date_str not in date_elements:
                    date_elements.append(date_str)
        
        if not date_elements:
            print(f"    ⚠ 부칙 영역에서 날짜를 찾을 수 없습니다. (부칙 영역 텍스트 길이: {len(ar_div_area.get_text())}자)")
            return result
        
        # 날짜 파싱 및 정렬
        parsed_dates = []
        for date_str in date_elements:
            # 날짜 문자열 정리 (공백 제거)
            cleaned_date = re.sub(r'\s+', '', date_str)  # 모든 공백 제거
            # 날짜 형식 정규화 (YYYY.MM.DD 또는 YYYY-MM-DD)
            normalized_date = cleaned_date.replace('.', '-')
            
            # 날짜 파싱 시도
            parsed_date = None
            try:
                # 날짜 문자열에서 숫자만 추출하여 파싱
                date_match = re.search(r'(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})', normalized_date)
                if date_match:
                    year, month, day = date_match.groups()
                    date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    parsed_date = datetime.strptime(date_str_formatted, '%Y-%m-%d')
            except ValueError:
                continue
            
            if parsed_date:
                # 원본 날짜 문자열 저장 (공백 포함 가능)
                parsed_dates.append((parsed_date, date_str))
        
        if not parsed_dates:
            print(f"    ⚠ 날짜 파싱 실패 (발견된 날짜 문자열: {date_elements})")
            return result
        
        # 날짜 정렬 (오래된 순)
        parsed_dates.sort(key=lambda x: x[0])
        
        # 가장 오래된 날짜 = 제정일
        result['enactment_date'] = parsed_dates[0][1]
        
        # 가장 최근 날짜 = 최근 개정일 (날짜가 2개 이상일 때만 설정)
        if len(parsed_dates) > 1:
            result['revision_date'] = parsed_dates[-1][1]
        else:
            result['revision_date'] = ''  # 날짜가 하나만 있으면 최근 개정일은 비움
        
        return result
    
    def extract_law_detail(self, soup: BeautifulSoup) -> str:
        """
        법령 상세 페이지에서 법령 내용 추출
        
        Args:
            soup: BeautifulSoup 객체 (법령 상세 페이지)
            
        Returns:
            추출된 법령 내용 (텍스트)
        """
        if soup is None:
            return ""
        
        content = ""
        
        # 법령 본문 영역 찾기 (다양한 선택자 시도)
        content_selectors = [
            ('div', {'id': 'pDetail'}),
            ('div', {'id': 'lawContent'}),
            ('div', {'class': 'lawContent'}),
            ('div', {'id': 'conts'}),
            ('div', {'class': 'conts'}),
            ('div', {'id': 'content'}),
            ('div', {'class': 'content'}),
        ]
        
        content_div = None
        for tag, attrs in content_selectors:
            content_div = soup.find(tag, attrs) or soup.select_one(f"{tag}[id*='content'], {tag}[class*='content']")
            if content_div:
                break
        
        if content_div:
            # 법령 조문 내용 추출
            # 화면에서 보이는 것처럼 자연스럽게 추출 (개행 유지)
            # 스크립트, 스타일 등 제외
            for element in content_div.find_all(['script', 'style', 'nav', 'header', 'footer']):
                element.decompose()
            # 전체 텍스트 추출 (개행 유지)
            content = content_div.get_text(separator='\n', strip=True)
        
        # 내용이 없으면 본문 영역 전체에서 추출
        if not content:
            body = soup.find('body')
            if body:
                # 스크립트, 스타일, 네비게이션 등 제외
                for element in body.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    element.decompose()
                content = body.get_text(separator='\n', strip=True)
        
        # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
        import re
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # 연속된 개행을 최대 2개로 제한 (너무 많은 빈 줄 방지)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()
    
    def extract_department_from_detail(self, soup: BeautifulSoup, driver=None, is_adm_rul: bool = False) -> str:
        """
        법령 상세 페이지에서 소관부서 추출
        
        Args:
            soup: BeautifulSoup 객체 (법령 상세 페이지)
            driver: Selenium WebDriver (XPath 사용 시 필요)
            is_adm_rul: 행정규칙 페이지 여부 (True면 감독규정 등)
            
        Returns:
            추출된 소관부서 (문자열, 괄호 앞부분만)
        """
        if soup is None:
            return ""
        
        department = ""
        
        def clean_department_text(text: str) -> str:
            """
            소관부서 텍스트를 정리하여 괄호 앞부분만 반환
            예: "금융위원회(서민금융과), 02-2100-2612" -> "금융위원회"
            """
            if not text:
                return ""
            import re
            # 괄호 앞부분만 추출
            match = re.match(r'^([^(,]+)', text.strip())
            if match:
                cleaned = match.group(1).strip()
                # 쉼표나 전화번호 패턴 제거
                cleaned = re.sub(r',\s*\d{2,3}-\d{3,4}-\d{4}.*$', '', cleaned)
                cleaned = cleaned.strip()
                return cleaned
            return text.strip()
        
        # 방법 1: 행정규칙 페이지 (감독규정)의 경우 우선 처리
        if is_adm_rul:
            # 방법 1-1: Selenium driver를 사용하여 XPath로 직접 추출
            if driver:
                try:
                    # 행정규칙 페이지 XPath: /html/body/form[1]/div[1]/div[2]/div[4]/div/div/div/div[2]/div[1]
                    xpath = "/html/body/form[1]/div[1]/div[2]/div[4]/div/div/div/div[2]/div[1]"
                    element = driver.find_element(By.XPATH, xpath)
                    department_raw = element.text.strip()
                    if department_raw:
                        department = clean_department_text(department_raw)
                        print(f"  ✓ 행정규칙 페이지 XPath로 소관부서 추출: {department_raw} -> {department}")
                        return department
                except Exception as e:
                    print(f"  ⚠ 행정규칙 페이지 XPath로 소관부서 추출 실패: {e}")
            
            # 방법 1-2: CSS 선택자로 추출 (#conScroll > div.subtit2)
            try:
                element = soup.select_one('#conScroll > div.subtit2')
                if element:
                    department_raw = element.get_text(strip=True)
                    if department_raw:
                        department = clean_department_text(department_raw)
                        print(f"  ✓ 행정규칙 페이지 CSS 선택자로 소관부서 추출: {department_raw} -> {department}")
                        return department
            except Exception as e:
                print(f"  ⚠ 행정규칙 페이지 CSS 선택자로 소관부서 추출 실패: {e}")
            
            # 방법 1-3: BeautifulSoup로 form[1] 경로 따라가기
            try:
                forms = soup.find_all('form')
                if len(forms) >= 1:
                    form1 = forms[0]  # 인덱스 0 = 첫 번째 form
                    # 경로를 따라가기: div[1]/div[2]/div[4]/div/div/div/div[2]/div[1]
                    current = form1
                    divs = current.find_all('div', recursive=False)
                    if divs:
                        current = divs[0]  # div[1]
                        divs = current.find_all('div', recursive=False)
                        if len(divs) >= 2:
                            current = divs[1]  # div[2]
                            divs = current.find_all('div', recursive=False)
                            if len(divs) >= 4:
                                current = divs[3]  # div[4] (인덱스 3)
                                # div/div/div/div[2]/div[1]
                                target = current.select_one('div > div > div > div:nth-child(2) > div:nth-child(1)')
                                if target:
                                    department_raw = target.get_text(strip=True)
                                    if department_raw:
                                        department = clean_department_text(department_raw)
                                        print(f"  ✓ 행정규칙 페이지 BeautifulSoup로 소관부서 추출: {department_raw} -> {department}")
                                        return department
            except Exception as e:
                print(f"  ⚠ 행정규칙 페이지 BeautifulSoup로 소관부서 추출 실패: {e}")
        
        # 방법 2: 일반 법령 페이지 (form[2] 사용)
        if driver:
            try:
                # XPath: /html/body/form[2]/div[1]/div[2]/div[6]/div/div[1]/div/div/div[2]/div[1]/p/a/span[1]
                xpath = "/html/body/form[2]/div[1]/div[2]/div[6]/div/div[1]/div/div/div[2]/div[1]/p/a/span[1]"
                element = driver.find_element(By.XPATH, xpath)
                department_raw = element.text.strip()
                if department_raw:
                    department = clean_department_text(department_raw)
                    print(f"  ✓ XPath로 소관부서 추출: {department_raw} -> {department}")
                    return department
            except Exception as e:
                print(f"  ⚠ XPath로 소관부서 추출 실패: {e}")
                # 다른 XPath 패턴 시도
                try:
                    # 대체 XPath 패턴들
                    alt_xpaths = [
                        "/html/body/form[2]//div[6]//div[2]//p//a//span[1]",
                        "//form[2]//div[6]//div[2]//p//a//span[1]",
                        "//p//a//span[1]",
                    ]
                    for alt_xpath in alt_xpaths:
                        try:
                            element = driver.find_element(By.XPATH, alt_xpath)
                            department_raw = element.text.strip()
                            if department_raw:
                                department = clean_department_text(department_raw)
                                if department and len(department) < 50:  # 너무 긴 텍스트는 제외
                                    print(f"  ✓ 대체 XPath로 소관부서 추출: {department_raw} -> {department}")
                                    return department
                        except:
                            continue
                except:
                    pass
        
        # 방법 2: BeautifulSoup로 경로를 따라가서 추출
        try:
            # form[2] 찾기
            forms = soup.find_all('form')
            if len(forms) >= 2:
                form2 = forms[1]  # 인덱스 1 = 두 번째 form
                
                # 경로를 따라가기: div[1]/div[2]/div[6]/div/div[1]/div/div/div[2]/div[1]/p/a/span[1]
                current = form2
                
                # div[1]
                divs = current.find_all('div', recursive=False)
                if divs:
                    current = divs[0]
                    # div[2]
                    divs = current.find_all('div', recursive=False)
                    if len(divs) >= 2:
                        current = divs[1]
                        # div[6]
                        divs = current.find_all('div', recursive=False)
                        if len(divs) >= 6:
                            current = divs[5]  # 인덱스 5 = 6번째 div
                            # div/div[1]/div/div/div[2]/div[1]/p/a/span[1]
                            # 더 깊이 들어가기
                            p_tag = current.select_one('div > div:nth-child(1) > div > div > div:nth-child(2) > div:nth-child(1) > p')
                            if p_tag:
                                a_tag = p_tag.find('a')
                                if a_tag:
                                    span_tag = a_tag.find('span')
                                    if span_tag:
                                        department_raw = span_tag.get_text(strip=True)
                                        if department_raw:
                                            department = clean_department_text(department_raw)
                                            print(f"  ✓ BeautifulSoup로 소관부서 추출: {department_raw} -> {department}")
                                            return department
        except Exception as e:
            print(f"  ⚠ BeautifulSoup로 소관부서 추출 실패: {e}")
        
        # 방법 3: CSS 선택자로 일반적인 패턴 찾기
        try:
            # p > a > span[1] 패턴으로 찾기
            spans = soup.select('p > a > span:first-child')
            for span in spans:
                text_raw = span.get_text(strip=True)
                # 소관부서로 보이는 짧은 텍스트 (50자 이하, 부서명 같은 패턴)
                if text_raw and len(text_raw) < 50 and ('부' in text_raw or '청' in text_raw or '원' in text_raw or '위원회' in text_raw):
                    department = clean_department_text(text_raw)
                    if department:
                        print(f"  ✓ CSS 선택자로 소관부서 추출: {text_raw} -> {department}")
                        return department
        except Exception as e:
            print(f"  ⚠ CSS 선택자로 소관부서 추출 실패: {e}")
        
        return department
    
    def extract_law_search_results(self, soup: BeautifulSoup, base_url: str = None, is_adm_rul: bool = False, skip_target_filter: bool = False) -> Dict:
        """
        국가법령정보센터 검색 결과 페이지에서 법령 목록 추출
        
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL (상대 경로를 절대 경로로 변환하기 위해)
            is_adm_rul: 행정규칙 검색 페이지 여부 (True면 admRulSc.do 형식)
            
        Returns:
            법령 정보 리스트 (각 항목은 딕셔너리)
        """
        if soup is None:
            return {'total_count': 0, 'results': []}
        
        results = []
        
        # 검색 결과 총 개수 추출
        total_count = 0
        total_count_elem = soup.find('strong', class_='num') or soup.find('span', class_='num')
        if total_count_elem:
            try:
                total_count = int(total_count_elem.get_text(strip=True).replace(',', ''))
            except:
                pass
        
        # 행정규칙 검색 페이지와 법령 검색 페이지의 구조가 다를 수 있음
        # #viewHeightDiv > table > tbody > tr 구조로 검색 결과 추출
        # CSS 선택자로 직접 찾기: #viewHeightDiv > table > tbody > tr > td.tl > a
        view_height_div = soup.find('div', id='viewHeightDiv')
        if not view_height_div:
            # 다른 방법으로 찾기
            view_height_div = soup.select_one('#viewHeightDiv')
        
        # 행정규칙 검색 페이지의 경우 다른 선택자도 시도
        if not view_height_div and is_adm_rul:
            view_height_div = soup.find('div', class_='result_list') or soup.find('div', class_='list_area')
        
        if view_height_div:
            table = view_height_div.find('table')
            if not table:
                table = view_height_div.select_one('table')
            
            if table:
                tbody = table.find('tbody')
                if not tbody:
                    tbody = table.select_one('tbody')
                
                if tbody:
                    rows = tbody.find_all('tr')
                    # 헤더 행 확인 (첫 번째 행이 헤더일 수 있음)
                    # 첫 번째 행이 헤더인지 확인 (th 태그가 있거나 특정 텍스트가 있으면 헤더)
                    if rows:
                        first_row = rows[0]
                        first_row_has_th = first_row.find('th') is not None
                        first_cell_text = first_row.find('td')
                        if first_cell_text:
                            first_cell_text = first_cell_text.get_text(strip=True)
                            # 첫 번째 셀이 숫자가 아니고 헤더 텍스트가 있으면 헤더로 간주
                            if first_row_has_th or (first_cell_text and not first_cell_text.isdigit() and 
                                                     ('법령명' in first_cell_text or '번호' in first_cell_text)):
                                rows = rows[1:]  # 헤더 제외
                    
                    for row in rows:
                        item = {}
                        cells = row.find_all('td')
                        
                        # 디버깅: 첫 번째 행의 셀 구조 확인
                        if not hasattr(self, '_table_structure_logged') and cells:
                            cell_info = []
                            for idx, cell in enumerate(cells):
                                cell_text = cell.get_text(strip=True)[:30]  # 처음 30자만
                                cell_class = ' '.join(cell.get('class', []))
                                cell_info.append(f"셀[{idx}]: '{cell_text}' (class: {cell_class})")
                            print(f"  [디버그] 테이블 구조: {len(cells)}개 셀 발견")
                            print(f"  [디버그] " + " | ".join(cell_info))
                            self._table_structure_logged = True
                        
                        # 법령명 추출: td.tl > a (CSS 선택자 사용)
                        law_name_link = None
                        law_name_cell = row.find('td', class_='tl')
                        if not law_name_cell:
                            # class가 리스트가 아닐 수도 있으므로 다른 방법도 시도
                            for td in cells:
                                if 'tl' in td.get('class', []):
                                    law_name_cell = td
                                    break
                        
                        if law_name_cell:
                            law_name_link = law_name_cell.find('a')
                        
                        if law_name_link:
                            item['law_name'] = law_name_link.get_text(strip=True)
                            # 링크 추출
                            link = law_name_link.get('href', '')
                            
                            # href가 '#'이거나 빈 문자열인 경우, onclick 속성 확인
                            if not link or link == '#' or link.startswith('javascript:'):
                                onclick = law_name_link.get('onclick', '')
                                if onclick:
                                    # onclick에서 URL 추출 시도
                                    import re
                                    url_match = re.search(r"['\"]([^'\"]*lsInfoP[^'\"]*)['\"]", onclick)
                                    if url_match:
                                        link = url_match.group(1)
                                    else:
                                        # 검색 URL을 기본값으로 사용
                                        link = base_url if base_url else ""
                                else:
                                    # 링크가 없으면 검색 URL을 기본값으로 사용
                                    link = base_url if base_url else ''
                            # else: link가 이미 유효한 경우 그대로 사용
                            
                            if link and base_url and not link.startswith('http'):
                                item['link'] = urljoin(base_url, link)
                            elif link:
                                item['link'] = link
                            else:
                                # 링크가 없으면 검색 URL 사용
                                item['link'] = base_url if base_url else ''
                        
                        # 각 셀에서 정보 추출 (실제 테이블 구조에 맞게 동적으로 처리)
                        # 주의: 테이블 구조는 페이지마다 다를 수 있으므로 셀 개수와 내용을 확인하여 추출
                        for i, cell in enumerate(cells):
                            cell_text = cell.get_text(strip=True)
                            cell_class = cell.get('class', [])
                            
                            # 법령명은 이미 처리했으므로 건너뛰기
                            if 'tl' in cell_class:
                                continue
                            
                            # 셀 내용을 기반으로 정보 추출 (위치 기반이 아닌 내용 기반)
                            # 공포일자: 날짜 형식이 포함된 경우
                            if ('년' in cell_text or '.' in cell_text) and not item.get('promulgation_date'):
                                # 법령번호가 아닌지 확인 (제XXX호 형식 제외)
                                if '호' not in cell_text and '제' not in cell_text[:5]:
                                    item['promulgation_date'] = cell_text
                            # 시행일자: 날짜 형식이 포함된 경우
                            elif ('년' in cell_text or '.' in cell_text) and not item.get('enforcement_date'):
                                if '호' not in cell_text and '제' not in cell_text[:5]:
                                    item['enforcement_date'] = cell_text
                            # 법령종류: 짧은 텍스트이고 날짜가 아닌 경우
                            elif cell_text and len(cell_text) < 20 and not item.get('law_type'):
                                if '년' not in cell_text and '.' not in cell_text and '호' not in cell_text:
                                    item['law_type'] = cell_text
                            # 소관부처: 마지막 셀이고 법령번호가 아닌 경우
                            elif i == len(cells) - 1:
                                if cell_text and '호' not in cell_text and '제' not in cell_text:
                                    item['ministry'] = cell_text
                                    # department도 동일하게 설정 (호환성을 위해)
                                    item['department'] = cell_text
                        
                        if item.get('law_name'):  # 법령명이 있는 경우만 추가
                            # skip_target_filter가 True이면 필터링 건너뛰기 (엑셀 파일에서 읽은 법령 처리 시)
                            if skip_target_filter:
                                results.append(item)
                            else:
                                # 대상 법령인지 확인 (목록이 정의되어 있고 비어있지 않은 경우만 필터링)
                                if self.law_items:
                                    if self.is_target_law(item['law_name']):
                                        results.append(item)
                                else:
                                    # 목록이 비어있으면 모든 결과 포함
                                    results.append(item)
        
        # 위 방법으로 추출이 안 되면 기존 방법 시도
        if not results:
            # 기존 테이블 구조 시도
            table = soup.find('table', class_='tbl') or soup.find('table', id='resultTable')
            if table:
                rows = table.find_all('tr')[1:]  # 헤더 제외
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        item = {}
                        # 법령명 추출
                        law_name_elem = cells[0].find('a') or cells[0]
                        if law_name_elem:
                            item['law_name'] = law_name_elem.get_text(strip=True)
                            link = law_name_elem.get('href', '')
                            if link and base_url:
                                item['link'] = urljoin(base_url, link)
                            else:
                                item['link'] = link
                        
                        if len(cells) > 1:
                            item['law_type'] = cells[1].get_text(strip=True)
                        if len(cells) > 2:
                            item['promulgation_date'] = cells[2].get_text(strip=True)
                        if len(cells) > 3:
                            item['enforcement_date'] = cells[3].get_text(strip=True)
                        if len(cells) > 4:
                            cell_text = cells[4].get_text(strip=True)
                            item['ministry'] = cell_text
                            # department도 동일하게 설정 (호환성을 위해)
                            item['department'] = cell_text
                        
                        if item.get('law_name'):
                            # 대상 법령인지 확인
                            if self.law_items:
                                if self.is_target_law(item['law_name']):
                                    results.append(item)
                            else:
                                results.append(item)
        
        return {
            'total_count': total_count,
            'results': results
        }
    
    def save_results(self, data: Dict, filename: str = 'crawl_results.json'):
        """
        스크래핑 결과를 JSON 파일로 저장
        
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
        스크래핑 결과를 CSV 파일로 저장 (KFB_Scraper와 동일한 컬럼 구조)
        
        Args:
            records: 행 단위 데이터 리스트 (이미 한글 필드명으로 정리된 데이터)
            meta: 메타 정보 딕셔너리 (예: url, crawled_at, total_count 등)
            filename: 저장할 파일명
        """
        import os
        import csv
        os.makedirs('output', exist_ok=True)
        filepath = os.path.join('output', filename)

        if not records:
            print(f"저장할 데이터가 없습니다.")
            return

        # 헤더 정의 (번호, 파일 다운로드 링크 제거, 구분 추가)
        headers = ["구분", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 이름"]

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for law_item in records:
                # 본문 내용 처리 (개행 유지, 1000자 제한)
                content = law_item.get("본문", "") or ""
                # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                if len(content) > 1000:
                    content = content[:1000]
                
                csv_item = law_item.copy()
                csv_item["본문"] = content
                writer.writerow(csv_item)

        print(f"\nCSV로 저장되었습니다: {filepath}")

    def build_search_url(self, base_url: str, keyword: str, page: int = 1) -> str:
        """
        검색 키워드를 쿼리 파라미터에 넣어 검색 URL 생성
        
        Args:
            base_url: 기본 검색 URL (query=까지 포함)
            keyword: 검색 키워드
            page: 페이지 번호 (기본값: 1)
        """
        if not keyword:
            # 키워드가 없으면 base_url 그대로 반환 (페이지 번호만 추가)
            if page > 1:
                return f"{base_url}&pageNo={page}"
            return base_url
        
        # URL에 이미 query=가 있으므로 키워드를 URL 인코딩하여 추가
        url = f"{base_url}{quote_plus(keyword)}"
        
        # 페이지 번호 추가 (국가법령정보센터는 여러 파라미터 형식 사용 가능)
        if page > 1:
            # 여러 가능한 파라미터 이름 시도
            # outMax는 페이지당 항목 수, pageNo 또는 page는 페이지 번호
            url += f"&pageNo={page}"  # 국가법령정보센터는 pageNo를 사용할 가능성이 높음
        
        return url
    
    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """
        검색 결과 페이지에서 총 페이지 수 추출
        
        Args:
            soup: BeautifulSoup 객체
            
        Returns:
            총 페이지 수 (찾지 못하면 1 반환)
        """
        if soup is None:
            return 1
        
        # 페이지네이션 영역 찾기 (다양한 선택자 시도)
        pagination_selectors = [
            ('div', {'class': 'paging'}),
            ('div', {'class': 'pagination'}),
            ('div', {'id': 'paging'}),
            ('div', {'class': 'page'}),
            ('div', {'id': 'pageList'}),
        ]
        
        pagination = None
        for tag, attrs in pagination_selectors:
            pagination = soup.find(tag, attrs) or soup.select_one(f"{tag}[class*='paging'], {tag}[id*='paging']")
            if pagination:
                break
        
        if pagination:
            # 페이지 번호 링크 찾기
            page_links = pagination.find_all('a')
            max_page = 1
            for link in page_links:
                link_text = link.get_text(strip=True)
                # 숫자인 페이지 번호 찾기
                if link_text.isdigit():
                    max_page = max(max_page, int(link_text))
                # href에서 페이지 번호 추출
                href = link.get('href', '')
                if href:
                    # 다양한 파라미터 형식 시도
                    for param in ['page=', 'pageNo=', 'p=', 'currentPage=']:
                        if param in href:
                            try:
                                page_num = int(href.split(param)[1].split('&')[0].split('#')[0])
                                max_page = max(max_page, page_num)
                            except:
                                pass
            
            if max_page > 1:
                print(f"페이지네이션에서 찾은 최대 페이지: {max_page}")
                return max_page
        
        # 총 검색 결과 개수로 페이지 수 계산 (페이지당 50개 가정)
        total_count_elem = soup.find('strong', class_='num') or soup.find('span', class_='num')
        if total_count_elem:
            try:
                total_count_text = total_count_elem.get_text(strip=True).replace(',', '')
                total_count = int(total_count_text)
                # 페이지당 50개로 계산
                total_pages = (total_count + 49) // 50  # 올림 계산
                print(f"총 검색 결과 수({total_count})로 계산한 페이지 수: {total_pages}")
                return max(1, total_pages)
            except:
                pass
        
        print("페이지 수를 찾을 수 없어 기본값 1 반환")
        return 1


def main():
    """메인 함수 - 국가법령정보센터 검색 결과 스크래핑 (모든 페이지)"""
    import argparse
    parser = argparse.ArgumentParser(description='국가법령정보센터 법령 검색 스크래퍼')
    parser.add_argument('--query', '-q', type=str, default='', help='법령명 키워드 (예: 환경)')
    parser.add_argument('--limit', type=int, default=0, help='검색 목록에서 가져올 개수 제한 (0=전체)')
    parser.add_argument('--details-limit', type=int, default=0, help='상세 내용 스크래핑 개수 제한 (0=전체)')
    parser.add_argument('--content', type=int, default=0, help='본문 길이 제한 (0=제한 없음, 문자 수)')
    parser.add_argument('--no-download', action='store_true', help='파일 다운로드 및 저장 기능 스킵')
    args = parser.parse_args()

    keyword = args.query.strip()
    list_limit = max(0, int(args.limit))
    details_limit = max(0, int(args.details_limit))
    content_limit = max(0, int(args.content))
    no_download = args.no_download

    crawler = LawGoKrScraper(delay=1.0)
    
    # 스크래퍼 시작 시 current를 previous로 백업 (이전 실행 결과를 이전 버전으로)
    crawler._backup_current_to_previous()
    # 이전 실행의 diff 파일 정리
    crawler._clear_diffs_directory()
    
    # 국가법령정보센터 검색 페이지 베이스 URL (기본값)
    default_base_search_url = "https://www.law.go.kr/LSW/lsSc.do?section=&menuId=1&subMenuId=15&tabMenuId=81&eventGubun=060101&query="
    
    print("=== 국가법령정보센터 검색 결과 스크래핑 시작 ===")
    
    # Selenium 드라이버 생성 (재사용)
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--lang=ko-KR')
    
    # Chrome 다운로드 디렉토리 설정 (current 디렉토리)
    import os
    download_dir = str(crawler.current_dir)
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,  # PDF를 외부에서 열기
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=chrome_options)
    
    all_results = []
    total_count = 0
    first_page_url = None  # 초기화
    total_pages = 1  # 초기화
    law_info = {}  # 초기화
    
    try:
        # CSV 파일에서 읽은 법령 정보 사용
        if crawler.law_items and len(crawler.law_items) > 0:
            print(f"대상 법령: {len(crawler.law_items)}개")
            
            for i, target_item in enumerate(crawler.law_items, 1):
                # CSV 목록 항목인 경우
                if isinstance(target_item, dict):
                    original_law_name = target_item.get('법령명', '')  # 원본 법령명 (괄호 포함)
                    search_keyword = target_item.get('검색_키워드', original_law_name)  # 검색용 키워드 (괄호 제거)
                    division = target_item.get('구분', '')
                    base_search_url = target_item.get('검색_URL', default_base_search_url)
                else:
                    # 기존 호환성: 문자열인 경우
                    original_law_name = str(target_item)
                    search_keyword = crawler._remove_parentheses(original_law_name)
                    division = '법령'
                    base_search_url = default_base_search_url
                
                if not search_keyword:
                    continue
                
                print(f"\n[{i}/{len(crawler.law_items)}] '{original_law_name}' 검색 중... (검색 키워드: '{search_keyword}', 구분: {division})")
                
                # 검색 키워드로 검색 URL 생성 (괄호 제거된 키워드 사용)
                search_url = crawler.build_search_url(base_search_url, search_keyword, page=1)
                if first_page_url is None:
                    first_page_url = search_url  # 첫 번째 검색 URL 저장
                    # 첫 번째 검색에서 페이지 정보 추출
                    temp_soup = crawler.fetch_page(search_url, use_selenium=True, driver=driver)
                    if temp_soup:
                        law_info = crawler.extract_law_info(temp_soup)
                
                soup = crawler.fetch_page(search_url, use_selenium=True, driver=driver)
                
                if not soup:
                    print(f"  ⚠ '{original_law_name}' 검색 페이지를 가져오는데 실패했습니다.")
                    continue
                
                # 첫 번째 페이지에서 검색 결과 추출 (목록만 가져오기)
                # CSV에서 읽은 법령이므로 목록 필터링 건너뛰기
                is_adm_rul = 'admRulSc.do' in base_search_url
                search_results = crawler.extract_law_search_results(soup, search_url, is_adm_rul=is_adm_rul, skip_target_filter=True)
                page_results = search_results.get('results', [])
                
                # 검색 결과가 없으면 다음으로
                if not page_results:
                    print(f"  ✗ '{original_law_name}' 검색 결과를 찾을 수 없습니다. (결과 개수: 0)")
                    continue
                
                # 디버깅: 검색 결과 확인
                print(f"  검색 결과 {len(page_results)}개 발견")
                
                # 검색 결과에서 정확히 일치하거나 유사한 항목 찾기
                target_item = None
                
                # 법령명 정규화 함수 (띄어쓰기, 특수문자 제거)
                def normalize_law_name(name: str) -> str:
                    import re
                    # 띄어쓰기 제거, 특수문자 제거
                    normalized = re.sub(r'[\s\W]+', '', name)
                    return normalized.lower()
                
                # 검색 키워드를 정규화하여 비교
                normalized_target = normalize_law_name(search_keyword)
                
                # 정확히 일치하는 항목 찾기
                for result in page_results:
                    law_name = result.get('law_name', '')
                    if not law_name:
                        continue
                    normalized_result = normalize_law_name(law_name)
                    
                    # 정확히 일치하거나 포함 관계 확인
                    if normalized_result == normalized_target or normalized_target in normalized_result or normalized_result in normalized_target:
                        target_item = result
                        print(f"  ✓ 법령 찾음: {law_name}")
                        break
                
                # 정확히 일치하는 항목이 없으면 첫 번째 항목 사용
                if not target_item and page_results:
                    target_item = page_results[0]
                    print(f"  ⚠ 정확히 일치하는 항목을 찾지 못해 첫 번째 결과를 사용합니다: {target_item.get('law_name', 'N/A')}")
                
                if target_item:
                    law_link = target_item.get('link', '')
                    if law_link:
                        print(f"  ✓ 법령 링크 찾음: {target_item.get('law_name', 'N/A')}")
                        print(f"  → 상세 페이지로 이동하여 본문 추출 중...")
                        
                        detail_soup = None
                        law_content = ""
                        
                        # 링크가 검색 URL이거나 JavaScript 링크인 경우, Selenium으로 직접 클릭
                        if 'lsSc.do' in law_link or 'javascript:' in law_link or not law_link.startswith('http'):
                            try:
                                # 검색 페이지로 이동
                                driver.get(search_url)
                                time.sleep(2)
                                
                                # 검색 결과 목록 대기 (liBgcolor 요소 또는 테이블)
                                WebDriverWait(driver, 10).until(
                                    EC.any_of(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "li[id^='liBgcolor']")),
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a"))
                                    )
                                )
                                
                                # 방법 1: class="on"인 liBgcolor 항목 찾기 (우선)
                                target_li = None
                                target_anchor = None
                                
                                try:
                                    # 모든 liBgcolor 요소 찾기 (0, 1, 2...)
                                    all_li_elements = driver.find_elements(By.CSS_SELECTOR, "li[id^='liBgcolor']")
                                    print(f"  → liBgcolor 요소 {len(all_li_elements)}개 발견")
                                    
                                    # class="on"인 항목 찾기
                                    li_on_element = None
                                    for li_elem in all_li_elements:
                                        li_class = li_elem.get_attribute('class') or ''
                                        if 'on' in li_class:
                                            li_on_element = li_elem
                                            print(f"  ✓ class='on'인 liBgcolor 항목 발견 (ID: {li_elem.get_attribute('id')})")
                                            break
                                    
                                    if li_on_element:
                                        # 검색 키워드로 정규화하여 비교
                                        normalized_search_keyword = normalize_law_name(search_keyword)
                                        
                                        # liBgcolor 내부에서 법령명 링크 찾기
                                        # 여러 패턴 시도: span.tx > a, 또는 직접 a 태그
                                        law_name_links = li_on_element.find_elements(By.CSS_SELECTOR, "span.tx a, a span.tx, a")
                                        
                                        for link in law_name_links:
                                            link_text = link.text.strip()
                                            # span.tx 내부의 텍스트도 확인
                                            if not link_text:
                                                # span.tx 내부의 strong 태그 텍스트 확인
                                                strong_tags = link.find_elements(By.CSS_SELECTOR, "strong")
                                                if strong_tags:
                                                    link_text = ' '.join([s.text.strip() for s in strong_tags])
                                            
                                            if link_text:
                                                normalized_link = normalize_law_name(link_text)
                                                # 검색 키워드와 일치하는지 확인
                                                if normalized_search_keyword == normalized_link or normalized_search_keyword in normalized_link or normalized_link in normalized_search_keyword:
                                                    target_li = li_on_element
                                                    target_anchor = link
                                                    print(f"  ✓ class='on' 항목에서 법령명 일치: {link_text[:50]}... (ID: {li_on_element.get_attribute('id')})")
                                                    break
                                        
                                        # 검색 키워드와 일치하는 링크를 찾지 못한 경우, class='on' 항목의 첫 번째 링크 사용
                                        if not target_anchor and law_name_links:
                                            target_li = li_on_element
                                            target_anchor = law_name_links[0]
                                            print(f"  ⚠ class='on' 항목에서 검색 키워드와 일치하는 링크를 찾지 못해 첫 번째 링크 사용: {target_anchor.text[:50]}...")
                                    else:
                                        # class="on"인 항목을 찾지 못한 경우, 모든 liBgcolor 요소에서 검색 키워드와 일치하는 항목 찾기
                                        print(f"  ⚠ class='on'인 항목을 찾을 수 없습니다. 모든 liBgcolor 요소에서 검색 중...")
                                        normalized_search_keyword = normalize_law_name(search_keyword)
                                        
                                        for li_elem in all_li_elements:
                                            try:
                                                # liBgcolor 내부의 a 태그 찾기
                                                a_tags = li_elem.find_elements(By.CSS_SELECTOR, "a")
                                                
                                                for a_tag in a_tags:
                                                    # title 속성 확인
                                                    title_text = a_tag.get_attribute('title') or ''
                                                    # span.tx 내부의 텍스트 확인
                                                    span_tx = a_tag.find_elements(By.CSS_SELECTOR, "span.tx")
                                                    link_text = ''
                                                    
                                                    if span_tx:
                                                        link_text = span_tx[0].text.strip()
                                                        # strong 태그 텍스트도 확인
                                                        if not link_text:
                                                            strong_tags = span_tx[0].find_elements(By.CSS_SELECTOR, "strong")
                                                            if strong_tags:
                                                                link_text = ' '.join([s.text.strip() for s in strong_tags])
                                                    
                                                    # title이나 link_text에서 검색 키워드와 일치하는지 확인
                                                    if title_text:
                                                        normalized_title = normalize_law_name(title_text)
                                                        if normalized_search_keyword == normalized_title or normalized_search_keyword in normalized_title or normalized_title in normalized_search_keyword:
                                                            target_li = li_elem
                                                            target_anchor = a_tag
                                                            print(f"  ✓ liBgcolor 항목에서 타이틀 일치: {title_text[:50]}... (ID: {li_elem.get_attribute('id')})")
                                                            break
                                                    
                                                    if link_text:
                                                        normalized_link = normalize_law_name(link_text)
                                                        if normalized_search_keyword == normalized_link or normalized_search_keyword in normalized_link or normalized_link in normalized_search_keyword:
                                                            target_li = li_elem
                                                            target_anchor = a_tag
                                                            print(f"  ✓ liBgcolor 항목에서 법령명 일치: {link_text[:50]}... (ID: {li_elem.get_attribute('id')})")
                                                            break
                                                
                                                if target_anchor:
                                                    break
                                            except Exception as e:
                                                continue
                                        
                                        if not target_anchor:
                                            print(f"  ⚠ 모든 liBgcolor 요소에서 검색 키워드와 일치하는 항목을 찾을 수 없습니다.")
                                    
                                    # liBgcolor1에서 찾지 못한 경우, 테이블에서 찾기
                                    if not target_anchor:
                                        print(f"  → liBgcolor1에서 찾지 못해 테이블에서 검색 중...")
                                        anchors = driver.find_elements(By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a")
                                        
                                        for anchor in anchors:
                                            anchor_text = anchor.text.strip()
                                            normalized_anchor = normalize_law_name(anchor_text)
                                            if normalized_search_keyword == normalized_anchor or normalized_search_keyword in normalized_anchor or normalized_anchor in normalized_search_keyword:
                                                target_anchor = anchor
                                                print(f"  ✓ 테이블에서 항목 발견: {anchor_text[:50]}...")
                                                break
                                    
                                except Exception as e:
                                    print(f"  ⚠ liBgcolor 요소 찾기 실패: {e}")
                                    # 대체 방법: 테이블에서 찾기
                                    anchors = driver.find_elements(By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a")
                                    normalized_search_keyword = normalize_law_name(search_keyword)
                                    
                                    for anchor in anchors:
                                        anchor_text = anchor.text.strip()
                                        normalized_anchor = normalize_law_name(anchor_text)
                                        if normalized_search_keyword == normalized_anchor or normalized_search_keyword in normalized_anchor or normalized_anchor in normalized_search_keyword:
                                            target_anchor = anchor
                                            break
                                    
                                    if not target_anchor and anchors:
                                        target_anchor = anchors[0]
                                
                                if target_anchor:
                                    # JavaScript로 클릭 시도
                                    print(f"  → 법령 링크 클릭 중...")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", target_anchor)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", target_anchor)
                                    time.sleep(2)
                                    
                                    # 상세 페이지 로드 대기
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "#pDetail, #lawContent, .lawContent, #conts, .conts, #content, .content, .law_view"))
                                    )
                                    time.sleep(1)
                                    detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                                    print(f"  ✓ 상세 페이지 로드 완료")
                                else:
                                    print(f"  ⚠ 클릭할 링크를 찾을 수 없습니다.")
                            except Exception as e:
                                print(f"  ⚠ Selenium 클릭 실패: {str(e)[:100]}")
                                import traceback
                                traceback.print_exc()
                        else:
                            # 일반 링크인 경우 직접 접근
                            detail_soup = crawler.fetch_page(law_link, use_selenium=True, driver=driver)
                        
                        if detail_soup:
                            # 디버깅: 첫 번째 상세 페이지만 HTML 저장
                            if not hasattr(crawler, '_debug_html_saved'):
                                debug_dir = crawler.output_dir / "debug"
                                debug_dir.mkdir(parents=True, exist_ok=True)
                                debug_file = debug_dir / "debug_law_detail.html"
                                if not debug_file.exists():
                                    with open(debug_file, 'w', encoding='utf-8') as f:
                                        f.write(detail_soup.prettify())
                                    print(f"  ✓ 디버그 HTML 저장: {debug_file}")
                                    crawler._debug_html_saved = True
                            
                            law_content = crawler.extract_law_detail(detail_soup)
                            target_item['law_content'] = law_content
                            if law_content and len(law_content.strip()) > 100:  # 의미있는 내용인지 확인
                                print(f"  ✓ 본문 추출 완료 ({len(law_content)}자)")
                            else:
                                print(f"  ⚠ 본문 추출 실패 또는 빈 내용")
                            
                            # 부칙 영역에서 제정일과 최근 개정일 추출
                            # 방법 1: 검색 결과 목록에서 부칙 버튼 클릭하여 추출 (테스트)
                            date_info = {'enactment_date': '', 'revision_date': ''}
                            
                            # 검색 결과 목록 페이지로 돌아가서 부칙 버튼 클릭 시도
                            if 'lsSc.do' in law_link or 'javascript:' in law_link or not law_link.startswith('http'):
                                try:
                                    print(f"  → 검색 결과 목록에서 부칙 목록 추출 시도 중...")
                                    # 검색 페이지로 다시 이동
                                    driver.get(search_url)
                                    time.sleep(2)
                                    
                                    # 검색 결과 테이블 대기
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a"))
                                    )
                                    
                                    # 부칙 목록에서 날짜 추출 시도
                                    date_info_from_list = crawler.extract_enactment_and_revision_dates_from_list(driver, law_name=original_law_name)
                                    
                                    if date_info_from_list.get('enactment_date') or date_info_from_list.get('revision_date'):
                                        print(f"  ✓ 검색 결과 목록 방식으로 날짜 추출 성공")
                                        date_info = date_info_from_list
                                    else:
                                        print(f"  ⚠ 검색 결과 목록 방식으로 날짜 추출 실패, 상세 페이지 방식 시도")
                                except Exception as e:
                                    print(f"  ⚠ 검색 결과 목록에서 부칙 추출 실패: {e}")
                            
                            # 방법 2: 상세 페이지의 부칙 영역에서 추출 (기존 방식)
                            if not (date_info.get('enactment_date') or date_info.get('revision_date')):
                                print(f"  → 상세 페이지 부칙 영역에서 날짜 추출 중...")
                                date_info = crawler.extract_enactment_and_revision_dates(detail_soup)
                                if date_info.get('enactment_date') or date_info.get('revision_date'):
                                    print(f"  ✓ 상세 페이지 방식으로 날짜 추출 성공")
                            
                            if date_info.get('enactment_date'):
                                target_item['enactment_date'] = date_info['enactment_date']
                                print(f"  ✓ 제정일 추출: {date_info['enactment_date']}")
                            else:
                                target_item['enactment_date'] = ''
                                print(f"  ⚠ 제정일 추출 실패 (부칙 영역에서 날짜를 찾을 수 없음)")
                            if date_info.get('revision_date'):
                                target_item['revision_date'] = date_info['revision_date']
                                print(f"  ✓ 최근 개정일 추출: {date_info['revision_date']}")
                            else:
                                target_item['revision_date'] = ''
                                print(f"  ⚠ 최근 개정일 추출 실패 (부칙 영역에서 날짜를 찾을 수 없음)")
                            
                            # 상세 페이지에서 소관부서 추출
                            print(f"  → 상세 페이지에서 소관부서 추출 시도 중...")
                            department_from_detail = crawler.extract_department_from_detail(detail_soup, driver=driver, is_adm_rul=is_adm_rul)
                            if department_from_detail:
                                # 상세 페이지에서 추출한 소관부서가 있으면 우선 사용
                                target_item['department'] = department_from_detail
                                target_item['ministry'] = department_from_detail
                                print(f"  ✓ 소관부서 추출: {department_from_detail}")
                            elif not target_item.get('ministry') and not target_item.get('department'):
                                # 검색 결과 목록에서 추출하지 못했고, 상세 페이지에서도 추출하지 못한 경우
                                print(f"  ⚠ 소관부서 추출 실패")
                            
                            # 파일 다운로드 (Selenium을 사용하여 팝업 처리)
                            # --no-download 플래그가 있으면 파일 다운로드 스킵
                            if no_download:
                                print(f"  → 파일 다운로드 스킵 (--no-download 플래그 활성화)")
                                target_item['file_download_link'] = ''
                                target_item['file_name'] = ''
                            else:
                                # 상세 페이지가 이미 Selenium으로 열려있으므로 driver 사용 가능
                                print(f"  → 파일 다운로드 시도 중...")
                                
                                # Selenium으로 파일 다운로드 (팝업 처리)
                                downloaded_file_path = crawler._download_file_with_selenium(driver, regulation_name=original_law_name)
                                
                                if downloaded_file_path and downloaded_file_path.get('file_path'):
                                    target_item['file_download_link'] = downloaded_file_path.get('file_url', '')
                                    target_item['file_name'] = downloaded_file_path.get('file_name', '')
                                    
                                    file_path = downloaded_file_path['file_path']
                                    if file_path.lower().endswith('.pdf'):
                                        print(f"  → PDF 내용 추출 중...")
                                        pdf_content = crawler.file_extractor.extract_pdf_content(file_path)
                                        if pdf_content:
                                            # PDF 내용이 있으면 본문으로 사용
                                            target_item['law_content'] = pdf_content
                                            print(f"  ✓ PDF에서 {len(pdf_content)}자 추출 완료")
                                else:
                                    # Selenium 다운로드 실패 시 기존 방법 시도
                                    file_info = crawler._extract_file_links(detail_soup, law_link)
                                    if file_info['download_links']:
                                        target_item['file_download_link'] = file_info['download_links'][0]
                                        target_item['file_name'] = file_info['file_names'][0] if file_info['file_names'] else ''
                                        
                                        # 파일 다운로드 및 비교
                                        downloaded_file_path = crawler._download_and_compare_file(
                                            file_info['download_links'][0],
                                            file_info['file_names'][0] if file_info['file_names'] else '파일.pdf',
                                            regulation_name=original_law_name
                                        )
                                        
                                        # PDF 파일이면 내용 추출
                                        if downloaded_file_path and downloaded_file_path.get('file_path'):
                                            file_path = downloaded_file_path['file_path']
                                            if file_path.lower().endswith('.pdf'):
                                                print(f"  → PDF 내용 추출 중...")
                                                pdf_content = crawler.file_extractor.extract_pdf_content(file_path)
                                                if pdf_content:
                                                    # PDF 내용이 있으면 본문으로 사용
                                                    target_item['law_content'] = pdf_content
                                                    print(f"  ✓ PDF에서 {len(pdf_content)}자 추출 완료")
                                    else:
                                        target_item['file_download_link'] = ''
                                        target_item['file_name'] = ''
                        else:
                            print(f"  ✗ 상세 페이지 가져오기 실패")
                            target_item['law_content'] = ""
                            target_item['file_download_link'] = ''
                            target_item['file_name'] = ''
                        
                        # 구분 정보 추가
                        target_item['division'] = division
                        
                        # 원본 법령명 저장 (결과에 표시할 원본 법령명)
                        target_item['original_law_name'] = original_law_name
                        
                        # 결과에 추가
                        all_results.append(target_item)
                        total_count += 1
                    else:
                        print(f"  ✗ '{original_law_name}' 링크를 찾을 수 없습니다.")
                else:
                    print(f"  ✗ '{original_law_name}' 검색 결과를 찾을 수 없습니다.")
        
        # law_items가 비어있으면 기존 방식 (키워드 검색 또는 전체 목록)
        if not (crawler.law_items and len(crawler.law_items) > 0):
            if keyword:
                print(f"검색 키워드: {keyword}")
            
            # 첫 번째 페이지 가져오기
            first_page_url = crawler.build_search_url(base_search_url, keyword, page=1)
            soup = crawler.fetch_page(first_page_url, use_selenium=True, driver=driver)
            
            if not soup:
                print("페이지를 가져오는데 실패했습니다.")
                return
            
            # 기본 페이지 정보 추출
            law_info = crawler.extract_law_info(soup)
            print(f"\n페이지 제목: {law_info.get('title', 'N/A')}")
            
            # 총 페이지 수 확인
            total_pages = crawler.get_total_pages(soup)
            print(f"총 페이지 수: {total_pages}")
            
            # 첫 번째 페이지 결과 추출
            search_results = crawler.extract_law_search_results(soup, first_page_url)
            total_count = search_results.get('total_count', 0)
            all_results = search_results.get('results', [])
            
            print(f"\n검색 결과 총 개수: {total_count}")
            print(f"페이지 1/{total_pages} 완료: {len(all_results)}개 추출")
            
            # 나머지 페이지들 순회
            if total_pages > 1:
                for page_num in range(2, total_pages + 1):
                    print(f"페이지 {page_num}/{total_pages} 스크래핑 중...")
                    page_url = crawler.build_search_url(base_search_url, keyword, page=page_num)
                    page_soup = crawler.fetch_page(page_url, use_selenium=True, driver=driver)
                    
                    if page_soup:
                        is_adm_rul = 'admRulSc.do' in page_url
                        page_results = crawler.extract_law_search_results(page_soup, page_url, is_adm_rul=is_adm_rul)
                        page_data = page_results.get('results', [])
                        all_results.extend(page_data)
                        print(f"  페이지 {page_num}/{total_pages} 완료: {len(page_data)}개 추출 (누적: {len(all_results)}개)")
                    else:
                        print(f"  페이지 {page_num}/{total_pages} 가져오기 실패")
            
            # 법령명 키워드 필터링 (대소문자 무시)
            if keyword:
                lowered = keyword.lower()
                all_results = [r for r in all_results if str(r.get('law_name', '')).lower().find(lowered) != -1]
            
            # 목록 제한 적용 (테스트용)
            if list_limit > 0 and len(all_results) > list_limit:
                all_results = all_results[:list_limit]
                print(f"목록 제한 적용: 처음 {list_limit}개 항목만 사용")

        print(f"\n=== 최종 결과 ===")
        print(f"검색 결과 총 개수: {total_count}")
        print(f"추출된 결과 수: {len(all_results)}")
        
        # CSV 목록을 사용한 경우 이미 상세 내용을 추출했으므로 중복 추출하지 않음
        # CSV 목록이 없고 키워드 검색을 사용한 경우에만 상세 내용 추출
        if not (crawler.law_items and len(crawler.law_items) > 0):
            # 각 법령의 상세 내용 추출
            print(f"\n=== 법령 상세 내용 추출 시작 ===")
            print(f"총 {len(all_results)}개 법령의 상세 내용을 추출합니다...")
            
            # 상세 스크래핑 개수 제한 계산
            max_details = len(all_results) if details_limit == 0 else min(details_limit, len(all_results))

            for idx, item in enumerate(all_results[:max_details], 1):
                law_link = item.get('link', '')
                if law_link:
                    print(f"[{idx}/{len(all_results)}] {item.get('law_name', 'N/A')[:50]}... 스크래핑 중")
                    detail_soup = crawler.fetch_page(law_link, use_selenium=True, driver=driver)
                    # 링크가 검색 URL로 보이는 등 상세로 이동하지 못한 경우, 목록 첫 행을 클릭하여 이동 시도
                    if detail_soup and first_page_url and ('lsSc.do' in law_link or not crawler.extract_law_detail(detail_soup)):
                        try:
                            # 목록 페이지로 이동 후 첫 번째 결과 클릭
                            driver.get(first_page_url)
                            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a")))
                            first_anchor = driver.find_element(By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a")
                            driver.execute_script("arguments[0].click();", first_anchor)
                            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#pDetail, #lawContent, .lawContent, #conts, .conts, #content, .content, .law_view")))
                            time.sleep(1)
                            detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                        except Exception as _:
                            pass
                if detail_soup:
                    law_content = crawler.extract_law_detail(detail_soup)
                    item['law_content'] = law_content
                    if law_content:
                        print(f"  ✓ 내용 추출 완료 ({len(law_content)}자)")
                    else:
                        print(f"  ⚠ 내용 추출 실패 또는 빈 내용")
                    
                    # 부칙 영역에서 제정일과 최근 개정일 추출
                    print(f"  → 부칙 영역에서 날짜 추출 중...")
                    date_info = crawler.extract_enactment_and_revision_dates(detail_soup)
                    if date_info.get('enactment_date'):
                        item['enactment_date'] = date_info['enactment_date']
                        print(f"  ✓ 제정일 추출: {date_info['enactment_date']}")
                    else:
                        item['enactment_date'] = ''
                        print(f"  ⚠ 제정일 추출 실패 (부칙 영역에서 날짜를 찾을 수 없음)")
                    if date_info.get('revision_date'):
                        item['revision_date'] = date_info['revision_date']
                        print(f"  ✓ 최근 개정일 추출: {date_info['revision_date']}")
                    else:
                        item['revision_date'] = ''
                        print(f"  ⚠ 최근 개정일 추출 실패 (부칙 영역에서 날짜를 찾을 수 없음)")
                else:
                    print(f"  ✗ 페이지 가져오기 실패")
                    item['law_content'] = ""
                    item['enactment_date'] = ''
                    item['revision_date'] = ''
            else:
                print(f"[{idx}/{len(all_results)}] 링크가 없어 건너뜀")
                item['law_content'] = ""
        
        print(f"\n=== 법령 상세 내용 추출 완료 ===")

            # 상세 스크래핑 제한 적용 (테스트용)
        if details_limit > 0:
            print(f"상세 제한: 처음 {details_limit}개만 상세 스크래핑")
    finally:
        driver.quit()
    
    # 결과 저장
    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    if all_results:
        print("\n=== 추출된 법령 정보 (처음 5개) ===")
        for i, item in enumerate(all_results[:5], 1):
            print(f"\n{i}. 법령명: {item.get('law_name', 'N/A')}")
            print(f"   법령 종류: {item.get('law_type', 'N/A')}")
            print(f"   공포일자: {item.get('promulgation_date', 'N/A')}")
            print(f"   시행일자: {item.get('enforcement_date', 'N/A')}")
            print(f"   소관부처: {item.get('ministry', 'N/A')}")
            print(f"   링크: {item.get('link', 'N/A')}")
            content = item.get('law_content', '')
            if content:
                print(f"   내용: {content[:100]}... ({len(content)}자)")
            else:
                print(f"   내용: 없음")
        
        def truncate_content(text: str) -> str:
            """본문 내용 처리 (개행 유지, 1000자 제한)"""
            if not text:
                return ''
            # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
            content = text.replace("\r\n", "\n").replace("\r", "\n")
            # 1000자 제한 (content_limit이 있으면 그것도 고려하되, 최대 1000자)
            max_length = min(1000, content_limit) if content_limit > 0 else 1000
            if len(content) > max_length:
                content = content[:max_length]
            return content

        for item in all_results:
            # 원본 법령명 우선 사용 (괄호 포함), 없으면 검색 결과의 법령명 사용
            regulation_name = item.get('original_law_name', '') or item.get('regulation_name', '') or item.get('law_name', '')
            full_content = item.get('content', item.get('law_content', ''))
            truncated_content = truncate_content(full_content)
            
            law_item = {
                '구분': item.get('division', ''),  # CSV의 구분 값
                '규정명': regulation_name,  # 원본 법령명 (괄호 포함) 사용
                '기관명': item.get('organization', '법제처'),
                '본문': truncated_content,
                '제정일': item.get('enactment_date', ''),  # 부칙에서 추출한 날짜만 사용 (대체 없음)
                '최근 개정일': item.get('revision_date', ''),  # 부칙에서 추출한 날짜만 사용 (대체 없음)
                '소관부서': item.get('department', item.get('ministry', '')),
                '파일 이름': item.get('file_name', '')
            }
            law_results.append(law_item)
    
    output_data = {
        'url': first_page_url or '',
            'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_pages': total_pages,
        'page_info': law_info,
        'total_count': len(law_results),
        'results': law_results
        }
    # law_results에 CSV 목록 전체를 반영 (미수집 항목은 빈 값으로 채움)
    def _normalize_name(name: str) -> str:
        import re
        return re.sub(r'[\s\W]+', '', (name or '').strip()).lower()

    final_results: List[Dict] = []
    if crawler.law_items:
        scraped_map = {}
        scraped_norm_map = {}
        for item in law_results:
            name = (item.get('규정명') or '').strip()
            if not name:
                continue
            if name not in scraped_map:
                scraped_map[name] = item
            norm_name = _normalize_name(name)
            if norm_name and norm_name not in scraped_norm_map:
                scraped_norm_map[norm_name] = item

        for target in crawler.law_items:
            if isinstance(target, dict):
                original_name = (target.get('법령명') or '').strip()
            else:
                original_name = str(target).strip()

            matched_item = scraped_map.get(original_name)
            if not matched_item and original_name:
                matched_item = scraped_norm_map.get(_normalize_name(original_name))

            if matched_item:
                # 이미 truncate된 값이지만 safety 차원에서 재확인
                matched_item = matched_item.copy()
                matched_item['본문'] = truncate_content(matched_item.get('본문', ''))
                final_results.append(matched_item)
            else:
                # CSV에서 구분 정보 가져오기
                division = ''
                if isinstance(target, dict):
                    division = target.get('구분', '')
                
                final_results.append(
                    {
                        '구분': division,
                        '규정명': original_name,
                        '기관명': '법제처',
                        '본문': '',
                        '제정일': '',
                        '최근 개정일': '',
                        '소관부서': '',
                        '파일 이름': '',
                    }
                )
    else:
        final_results = law_results

    total_export_count = len(final_results)

    # 파일명을 스크래퍼 이름에 맞춰 통일성 있게 변경
    json_name = 'law_scraper.json'
    # JSON 저장 시에도 전체 결과 사용
    output_data['total_count'] = total_export_count
    output_data['results'] = final_results
    crawler.save_results(output_data, json_name)

    # CSV 저장 (정리된 law_results 사용)
    meta_for_excel = {
        'url': first_page_url or '',
        'crawled_at': output_data['crawled_at'],
        'total_count': total_export_count,
        'total_pages': total_pages,
        'extracted_count': total_export_count,
        'keyword': keyword
    }
    csv_name = 'law_scraper.csv'
    crawler.save_results_csv(final_results, meta_for_excel, csv_name)
    
    print("\n=== 스크래핑 완료 ===")


if __name__ == "__main__":
    main()

