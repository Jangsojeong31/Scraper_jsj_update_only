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
            # 조문들은 보통 특정 클래스나 구조를 가지고 있음
            articles = content_div.find_all(['div', 'p', 'span'], class_=lambda x: x and ('article' in x.lower() or 'jo' in x.lower() or 'item' in x.lower()))
            if articles:
                for article in articles:
                    text = article.get_text(strip=True, separator='\n')
                    if text:
                        content += text + "\n\n"
            else:
                # 조문이 없으면 전체 텍스트 추출
                content = content_div.get_text(strip=True, separator='\n')
        
        # 내용이 없으면 본문 영역 전체에서 추출
        if not content:
            body = soup.find('body')
            if body:
                # 스크립트, 스타일, 네비게이션 등 제외
                for element in body.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    element.decompose()
                content = body.get_text(strip=True, separator='\n')
        
        return content.strip()
    
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
                        
                        # 각 셀에서 정보 추출 (테이블 구조에 맞게)
                        # 구조: 인덱스 | 법령명 | 공포일자 | 법령종류 | 법령번호 | 시행일자 | 타법개정 | 소관부처
                        for i, cell in enumerate(cells):
                            cell_text = cell.get_text(strip=True)
                            cell_class = cell.get('class', [])
                            
                            # 법령명은 이미 처리했으므로 건너뛰기
                            if 'tl' in cell_class:
                                continue
                            
                            # 셀 위치에 따라 정보 추출
                            if i == 2:  # 공포일자 (셀 인덱스 2)
                                if '년' in cell_text or '.' in cell_text:
                                    item['promulgation_date'] = cell_text
                            elif i == 3:  # 법령종류 (셀 인덱스 3)
                                if cell_text and not item.get('law_type'):
                                    item['law_type'] = cell_text
                            elif i == 5:  # 시행일자 (셀 인덱스 5)
                                if '년' in cell_text or '.' in cell_text:
                                    item['enforcement_date'] = cell_text
                            elif i == len(cells) - 1:  # 마지막 셀 (소관부처)
                                if cell_text and '호' not in cell_text and '제' not in cell_text:
                                    item['ministry'] = cell_text
                        
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
                            item['ministry'] = cells[4].get_text(strip=True)
                        
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

        # KFB_Scraper와 동일한 헤더 정의
        headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 다운로드 링크", "파일 이름"]

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for law_item in records:
                # records는 이미 한글 필드명으로 정리된 데이터이므로 그대로 사용
                # CSV 저장 시 본문의 줄바꿈 처리만 추가
                csv_item = law_item.copy()
                csv_item["본문"] = csv_item.get("본문", "").replace("\n", " ").replace("\r", " ")
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
    args = parser.parse_args()

    keyword = args.query.strip()
    list_limit = max(0, int(args.limit))
    details_limit = max(0, int(args.details_limit))

    crawler = LawGoKrScraper(delay=1.0)
    
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
                                
                                # 검색 결과 테이블 대기
                                WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a"))
                                )
                                
                                # 정확히 일치하는 법령명 링크 찾기 (검색 키워드로 비교)
                                anchors = driver.find_elements(By.CSS_SELECTOR, "#viewHeightDiv table tbody tr td.tl a")
                                target_anchor = None
                                
                                # 검색 키워드로 정규화하여 비교
                                normalized_search_keyword = normalize_law_name(search_keyword)
                                
                                for anchor in anchors:
                                    anchor_text = anchor.text.strip()
                                    normalized_anchor = normalize_law_name(anchor_text)
                                    # 검색 키워드가 앵커 텍스트에 포함되거나 일치하는 경우
                                    if normalized_search_keyword in normalized_anchor or normalized_anchor in normalized_search_keyword:
                                        target_anchor = anchor
                                        break
                                
                                # 정확히 일치하는 항목이 없으면 첫 번째 항목 사용
                                if not target_anchor and anchors:
                                    target_anchor = anchors[0]
                                
                                if target_anchor:
                                    # JavaScript로 클릭 시도
                                    driver.execute_script("arguments[0].click();", target_anchor)
                                    time.sleep(2)
                                    
                                    # 상세 페이지 로드 대기
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "#pDetail, #lawContent, .lawContent, #conts, .conts, #content, .content, .law_view"))
                                    )
                                    time.sleep(1)
                                    detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                                else:
                                    print(f"  ⚠ 클릭할 링크를 찾을 수 없습니다.")
                            except Exception as e:
                                print(f"  ⚠ Selenium 클릭 실패: {str(e)[:100]}")
                        else:
                            # 일반 링크인 경우 직접 접근
                            detail_soup = crawler.fetch_page(law_link, use_selenium=True, driver=driver)
                        
                        if detail_soup:
                            law_content = crawler.extract_law_detail(detail_soup)
                            target_item['law_content'] = law_content
                            if law_content and len(law_content.strip()) > 100:  # 의미있는 내용인지 확인
                                print(f"  ✓ 본문 추출 완료 ({len(law_content)}자)")
                            else:
                                print(f"  ⚠ 본문 추출 실패 또는 빈 내용")
                        else:
                            print(f"  ✗ 상세 페이지 가져오기 실패")
                            target_item['law_content'] = ""
                        
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
        else:
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
                if detail_soup and ('lsSc.do' in law_link or not crawler.extract_law_detail(detail_soup)):
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
                else:
                    print(f"  ✗ 페이지 가져오기 실패")
                    item['law_content'] = ""
            else:
                print(f"[{idx}/{len(all_results)}] 링크가 없어 건너뜀")
                item['law_content'] = ""
        
        print(f"\n=== 법령 상세 내용 추출 완료 ===")

            # 상세 스크래핑 제한 적용 (테스트용)
        if details_limit > 0:
            print(f"상세 제한: 처음 {details_limit}개만 상세 스크래핑")
    finally:
        driver.quit()
    
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
        
        # 결과 저장
        # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
        law_results = []
        for item in all_results:
            # 원본 법령명 우선 사용 (괄호 포함), 없으면 검색 결과의 법령명 사용
            regulation_name = item.get('original_law_name', '') or item.get('regulation_name', '') or item.get('law_name', '')
            
            law_item = {
                '번호': item.get('no', ''),
                '규정명': regulation_name,  # 원본 법령명 (괄호 포함) 사용
                '기관명': item.get('organization', '법제처'),
                '본문': item.get('content', item.get('law_content', '')),
                '제정일': item.get('enactment_date', item.get('promulgation_date', '')),
                '최근 개정일': item.get('revision_date', item.get('enforcement_date', '')),
                '소관부서': item.get('department', item.get('ministry', '')),
                '파일 다운로드 링크': item.get('file_download_link', item.get('download_link', '')),
                '파일 이름': item.get('file_name', '')
            }
            law_results.append(law_item)
        
    output_data = {
        'url': first_page_url,
            'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_pages': total_pages,
        'page_info': law_info,
            'total_count': len(law_results),
            'results': law_results
    }
    json_name = 'law_search_results.json' if not keyword else f"law_search_results_{keyword}.json"
    crawler.save_results(output_data, json_name)

        # CSV 저장 (정리된 law_results 사용)
    meta_for_excel = {
        'url': first_page_url,
        'crawled_at': output_data['crawled_at'],
            'total_count': len(law_results),
        'total_pages': total_pages,
            'extracted_count': len(law_results),
        'keyword': keyword
    }
    csv_name = 'law_search_results.csv' if not keyword else f"law_search_results_{keyword}.csv"
    crawler.save_results_csv(law_results, meta_for_excel, csv_name)
    
    print("\n=== 스크래핑 완료 ===")


if __name__ == "__main__":
    main()

