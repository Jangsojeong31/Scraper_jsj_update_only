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
    
    def __init__(self, delay: float = 1.0):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
        """
        super().__init__(delay)
    
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
    
    def extract_law_search_results(self, soup: BeautifulSoup, base_url: str = None) -> Dict:
        """
        국가법령정보센터 검색 결과 페이지에서 법령 목록 추출
        
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL (상대 경로를 절대 경로로 변환하기 위해)
            
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
        
        # #viewHeightDiv > table > tbody > tr 구조로 검색 결과 추출
        # CSS 선택자로 직접 찾기: #viewHeightDiv > table > tbody > tr > td.tl > a
        view_height_div = soup.find('div', id='viewHeightDiv')
        if not view_height_div:
            # 다른 방법으로 찾기
            view_height_div = soup.select_one('#viewHeightDiv')
        
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
                            if link and base_url:
                                item['link'] = urljoin(base_url, link)
                            else:
                                item['link'] = link
                        
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
        스크래핑 결과를 CSV 파일로 저장
        
        Args:
            records: 행 단위 데이터 리스트 (예: 검색 결과 항목들)
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

    def build_search_url(self, base_url: str, keyword: str, page: int = 1) -> str:
        """
        검색 키워드를 쿼리 파라미터에 넣어 검색 URL 생성
        
        Args:
            base_url: 기본 검색 URL
            keyword: 검색 키워드
            page: 페이지 번호 (기본값: 1)
        """
        if not keyword:
            return base_url
        
        # URL에 이미 query=가 있으므로 키워드만 추가
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
    
    # 국가법령정보센터 검색 페이지 베이스 URL
    base_search_url = "https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query="
    
    print("=== 국가법령정보센터 검색 결과 스크래핑 시작 ===")
    if keyword:
        print(f"검색 키워드: {keyword}")
    
    # Selenium 드라이버 생성 (재사용)
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--lang=ko-KR')
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
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
                    page_results = crawler.extract_law_search_results(page_soup, page_url)
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
                        first_anchor.click()
                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#pDetail, #lawContent, .lawContent, #conts, .conts, #content, .content")))
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

        # 상세 스크래핑 제한 적용 (테스트용): 상단 루프에서 이미 처리되었으나, 메시지 출력 목적
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
    output_data = {
        'url': first_page_url,
            'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_pages': total_pages,
        'page_info': law_info,
        'search_results': {
            'total_count': total_count,
            'results': all_results
        }
    }
    json_name = 'law_search_results.json' if not keyword else f"law_search_results_{keyword}.json"
    crawler.save_results(output_data, json_name)

    # 엑셀 저장
    meta_for_excel = {
        'url': first_page_url,
        'crawled_at': output_data['crawled_at'],
        'total_count': total_count,
        'total_pages': total_pages,
        'extracted_count': len(all_results),
        'keyword': keyword
    }
    csv_name = 'law_search_results.csv' if not keyword else f"law_search_results_{keyword}.csv"
    crawler.save_results_csv(all_results, meta_for_excel, csv_name)
    
    print("\n=== 스크래핑 완료 ===")


if __name__ == "__main__":
    main()

