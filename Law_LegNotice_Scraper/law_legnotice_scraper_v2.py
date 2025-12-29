# law_legnotice_scraper.py

"""
법제처 시행예정법령 스크래퍼
국가법령정보센터에서 시행예정법령 정보를 추출합니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (common 모듈 import를 위해)
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

from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
import json
import csv
from urllib.parse import urljoin, quote_plus, unquote
from datetime import datetime, date
from common.base_scraper import BaseScraper


class LawLegNoticeScraper(BaseScraper):
    """법제처 시행예정법령 스크래퍼"""
    
    BASE_URL = "https://www.law.go.kr"
    SEARCH_URL_TEMPLATE = "https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query={}"
    DEFAULT_CSV_PATH = "Law_LegNotice_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: str = None, content_all: bool = False):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            csv_path: 법령명 목록이 있는 CSV 파일 경로
            content_all: 본문 전체 가져오기 플래그 (기본값: False, 4000자 제한)
        """
        super().__init__(delay)
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "csv").mkdir(parents=True, exist_ok=True)
        
        # JSON 파일 경로
        self.json_path = self.output_dir / "json" / "law_legnotice_scraper.json"
        
        # CSV 파일에서 법령명 읽기
        self.law_items = self._load_target_laws_from_csv(csv_path or self.DEFAULT_CSV_PATH)
        print(f"✓ 법령 목록 로드: {len(self.law_items)}개")
        
        # 본문 전체 가져오기 플래그
        self.content_all = content_all
    
    def _remove_parentheses(self, text: str) -> str:
        """
        법령명에서 괄호와 그 내용을 제거
        
        Args:
            text: 원본 법령명
            
        Returns:
            괄호가 제거된 법령명
        """
        import re
        # 한글 괄호와 영문 괄호 모두 처리
        # 예: "법률(2026.1.1부터)" -> "법률"
        cleaned = re.sub(r'[\(（].*?[\)）]', '', text)
        return cleaned.strip()
    
    def extract_law_detail(self, soup: BeautifulSoup) -> str:
        """
        법령 상세 페이지에서 법령 내용 추출 (Law_Scraper의 extract_law_detail 참고)
        
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
        
        # 메뉴 항목 제거 (판례, 연혁, 위임행정규칙, 규제, 생활법령, 한눈보기 등)
        # 이런 메뉴 항목들은 본문 앞부분에 나타나므로 제거
        menu_patterns = [
            r'^판례\s*\n',
            r'^연혁\s*\n',
            r'^위임행정규칙\s*\n',
            r'^규제\s*\n',
            r'^생활법령\s*\n',
            r'^한눈보기\s*\n',
        ]
        
        # 메뉴 항목들이 연속으로 나오는 패턴 제거
        # 예: "판례\n연혁\n위임행정규칙\n규제\n생활법령\n한눈보기\n"
        menu_block_pattern = r'^(판례|연혁|위임행정규칙|규제|생활법령|한눈보기)(\s*\n(판례|연혁|위임행정규칙|규제|생활법령|한눈보기))*\s*\n'
        content = re.sub(menu_block_pattern, '', content, flags=re.MULTILINE)
        
        # 개별 메뉴 항목 제거 (남아있는 경우)
        for pattern in menu_patterns:
            content = re.sub(pattern, '', content, flags=re.MULTILINE)
        
        # 연속된 개행을 최대 2개로 제한 (너무 많은 빈 줄 방지)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()
    
    def _clean_content_text(self, content: str) -> str:
        """
        본문 텍스트에서 불필요한 부분 제거
        
        Args:
            content: 원본 본문 텍스트
            
        Returns:
            정제된 본문 텍스트
        """
        if not content:
            return ''
        
        lines = content.split('\n')
        cleaned_lines = []
        
        # 제거할 키워드 목록
        remove_keywords = [
            '본문으로 바로가기',
            '주메뉴 바로가기',
            '이 누리집은 대한민국 공식 전자정부 누리집입니다',
            '공식 전자정부 누리집',
            '100%',
            '뉴스·소식',
            '입법예고',
            '홈',
            '법제처 법령정보',
        ]
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 불필요한 키워드가 라인 시작 부분에 포함된 경우 제거
            should_remove = False
            for keyword in remove_keywords:
                # 라인이 키워드로 시작하거나 라인 전체가 키워드와 일치하는 경우 제거
                if line_stripped.startswith(keyword) or line_stripped == keyword:
                    should_remove = True
                    break
            
            if should_remove:
                continue
            
            cleaned_lines.append(line_stripped)
        
        # 빈 라인 정리 (연속된 빈 라인을 하나로)
        result_lines = []
        prev_empty = False
        for line in cleaned_lines:
            if not line:
                if not prev_empty:
                    result_lines.append('')
                    prev_empty = True
            else:
                result_lines.append(line)
                prev_empty = False
        
        return '\n'.join(result_lines).strip()
    
    def _load_target_laws_from_csv(self, csv_path: str) -> List[Dict]:
        """
        CSV 파일에서 법령명 읽기
        
        Args:
            csv_path: CSV 파일 경로
            
        Returns:
            법령 정보 리스트
        """
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            csv_file = project_root / csv_path
        
        if not csv_file.exists():
            print(f"⚠ CSV 파일을 찾을 수 없습니다: {csv_file}")
            return []
        
        law_items = []
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    law_name = row.get('법령명', '').strip()
                    division = row.get('구분', '').strip()
                    if law_name:
                        # 괄호 제거 (검색용)
                        search_law_name = self._remove_parentheses(law_name)
                        law_items.append({
                            '법령명': search_law_name,  # 괄호 제거된 법령명으로 검색
                            '원본법령명': law_name,  # 원본 법령명도 저장
                            '구분': division
                        })
        except Exception as e:
            print(f"⚠ CSV 파일 읽기 실패: {e}")
        
        return law_items
    
    def build_search_url(self, law_name: str) -> str:
        """
        법령명으로 검색 URL 생성
        
        Args:
            law_name: 법령명
            
        Returns:
            검색 URL
        """
        # URL 인코딩
        encoded_name = quote_plus(law_name)
        return self.SEARCH_URL_TEMPLATE.format(encoded_name)
    
    def search_legnotice(self, law_name: str, driver=None) -> tuple[Optional[BeautifulSoup], Optional]:
        """
        법령명으로 시행예정법령 검색
        
        Args:
            law_name: 법령명
            driver: Selenium WebDriver (재사용 가능)
            
        Returns:
            (검색 결과 페이지 BeautifulSoup 객체, Selenium driver) 튜플 또는 (None, None)
        """
        search_url = self.build_search_url(law_name)
        print(f"  검색 URL: {search_url}")
        
        # 검색 결과가 JavaScript로 동적 로드되므로 Selenium 사용
        if driver is None:
            # driver가 없으면 새로 생성
            soup = self.fetch_page(search_url, use_selenium=True)
            return soup, None
        else:
            # 기존 driver 재사용
            driver.get(search_url)
            time.sleep(2)  # 페이지 로드 대기
            soup = BeautifulSoup(driver.page_source, 'lxml')
            return soup, driver
    
    def normalize_law_name(self, name: str) -> str:
        """
        법령명을 정규화하여 비교 가능한 형태로 변환
        
        Args:
            name: 법령명
            
        Returns:
            정규화된 법령명 (공백, 특수문자 제거, 소문자 변환)
        """
        import re
        if not name:
            return ''
        
        # 공백 제거
        normalized = re.sub(r'\s+', '', name)
        # 특수문자 제거 (한글, 영문, 숫자만 유지)
        normalized = re.sub(r'[^\w가-힣]', '', normalized)
        # 소문자 변환
        normalized = normalized.lower()
        
        return normalized
    
    def is_same_law(self, search_keyword: str, extracted_name: str) -> bool:
        """
        검색 키워드와 추출된 법령명이 같은 법령인지 확인
        
        Args:
            search_keyword: 검색한 법령명
            extracted_name: 추출된 법령명 (앞에 번호가 있을 수 있음, 예: "2.외교부와...")
            
        Returns:
            같은 법령이면 True, 아니면 False
        """
        if not search_keyword or not extracted_name:
            return False
        
        import re
        
        # 추출된 법령명에서 앞의 번호 제거 (예: "2.외교부와..." -> "외교부와...")
        extracted_clean = re.sub(r'^\d+\.\s*', '', extracted_name).strip()
        
        # 정규화하여 비교 (공백, 특수문자 제거)
        normalized_search = self.normalize_law_name(search_keyword)
        normalized_extracted = self.normalize_law_name(extracted_clean)
        
        # 완전 일치 확인
        if normalized_search == normalized_extracted:
            return True
        
        # 검색 키워드가 추출된 법령명에 포함되는지 확인 (부분 일치)
        # 예: "외교부와그소속기관직제" 검색 -> "외교부와그소속기관직제" 추출 (일치)
        # 하지만 "공중등협박목적을위한..." 검색 -> "공중등협박목적및대량살상무기확산을위한..." 추출 (불일치)
        
        # 검색 키워드의 핵심 단어들이 추출된 법령명에 모두 포함되는지 확인
        search_words = re.findall(r'[\w가-힣]+', normalized_search)
        extracted_words = re.findall(r'[\w가-힣]+', normalized_extracted)
        
        # 3자 이상의 중요한 단어만 사용
        important_search_words = [w for w in search_words if len(w) >= 3]
        important_extracted_words = [w for w in extracted_words if len(w) >= 3]
        
        if not important_search_words:
            return False
        
        # 검색 키워드의 모든 중요한 단어가 추출된 법령명에 포함되는지 확인
        all_words_found = True
        for search_word in important_search_words:
            # 추출된 단어 중 하나라도 검색 단어를 포함하거나, 검색 단어가 추출된 단어를 포함하는지 확인
            found = False
            for ext_word in important_extracted_words:
                if search_word in ext_word or ext_word in search_word:
                    found = True
                    break
            if not found:
                all_words_found = False
                break
        
        if not all_words_found:
            return False
        
        # 추출된 법령명에 검색 키워드에 없는 중요한 단어가 많이 추가되었는지 확인
        # 예: "및대량살상무기확산을" 같은 추가 단어가 있으면 불일치로 판단
        search_word_set = set(important_search_words)
        extracted_word_set = set(important_extracted_words)
        
        # 추출된 단어 중 검색 키워드에 없는 단어들
        extra_words = extracted_word_set - search_word_set
        
        # 공통 단어 비율 계산
        common_words = search_word_set & extracted_word_set
        if len(search_word_set) > 0:
            common_ratio = len(common_words) / len(search_word_set)
            # 공통 단어 비율이 80% 이상이고, 추가된 단어가 많지 않으면 일치로 판단
            if common_ratio >= 0.8 and len(extra_words) <= 2:
                return True
        
        return False
    
    def extract_legnotice_items(self, soup: BeautifulSoup, law_name: str, save_debug: bool = False, driver=None) -> List[Dict]:
        """
        검색 결과 페이지에서 시행예정법령 항목 추출
        "앞으로 시행될 법령" 이미지가 있는 항목만 추출
        
        Args:
            soup: BeautifulSoup 객체
            law_name: 검색한 법령명
            save_debug: 디버그 HTML 저장 여부
            driver: Selenium WebDriver (본문 추출용)
            
        Returns:
            시행예정법령 정보 리스트
        """
        if soup is None:
            return []
        
        # 디버그 HTML 저장
        if save_debug:
            debug_dir = self.output_dir / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "debug_legnotice_search.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            print(f"  ✓ 디버그 HTML 저장: {debug_file}")
        
        items = []
        
        # 검색 결과가 있는지 확인
        # "총 0건" 같은 메시지 확인
        page_text = soup.get_text()
        import re
        total_match = re.search(r'총\s*(\d+)\s*건', page_text)
        if total_match:
            total_count = int(total_match.group(1))
            if total_count == 0:
                return []
        
        # 전체 HTML에서 "앞으로 시행될 법령" 이미지가 있는 li 태그 직접 찾기
        # 방법 1: 이미지로 직접 찾기
        legnotice_imgs = soup.find_all('img', src=lambda x: x and 'bul_list1.gif' in x)
        if not legnotice_imgs:
            # alt 속성으로도 시도
            legnotice_imgs = soup.find_all('img', alt='앞으로 시행될 법령')
        
        if not legnotice_imgs:
            # 결과가 없는 것으로 판단
            return []
        
        # 각 이미지가 포함된 li 태그 찾기
        list_items = []
        for img in legnotice_imgs:
            # 이미지의 부모를 따라 올라가서 li 태그 찾기
            parent = img.parent
            while parent and parent.name != 'li':
                parent = parent.parent
                if parent is None:
                    break
            
            if parent and parent.name == 'li':
                list_items.append(parent)
        
        # 중복 제거
        list_items = list(dict.fromkeys(list_items))  # 순서 유지하면서 중복 제거
        
        for li in list_items:
            # "앞으로 시행될 법령" 이미지가 있는지 확인
            # li 내부 어디서든 찾기 (li > a > span.tx > img 구조)
            img = li.find('img', alt='앞으로 시행될 법령')
            if not img:
                # alt 속성이 없으면 src로 확인 (bul_list1.gif)
                img = li.find('img', src=lambda x: x and 'bul_list1.gif' in x)
            
            if not img:
                # 시행예정법령 이미지가 없으면 건너뛰기
                continue
            
            # 이미지가 있는 경우에만 항목 추출
            import re
            item = {}
            
            # 링크 찾기 (li > a 구조)
            link = li.find('a', href=True)
            if link:
                # onclick 속성에서 상세 정보 추출 시도
                onclick = link.get('onclick', '')
                title = link.get('title', '')
                
                # title에서 시행 정보 추출
                if title:
                    item['title'] = title
                
                # href가 '#'이면 onclick에서 URL 추출 시도
                href = link.get('href', '')
                if href == '#' or not href:
                    # onclick에서 URL 정보 추출 (실제로는 JavaScript 함수 호출)
                    # 상세 페이지는 별도로 구성해야 할 수 있음
                    item['detail_url'] = None  # JavaScript로 동적 로드되는 경우
                else:
                    if href.startswith('/'):
                        item['detail_url'] = urljoin(self.BASE_URL, href)
                    elif href.startswith('http'):
                        item['detail_url'] = href
                    else:
                        item['detail_url'] = urljoin(self.SEARCH_URL_TEMPLATE.format(''), href)
                
                # span.tx에서 법령명 추출 (이미지 다음에 오는 텍스트)
                span_tx = link.find('span', class_='tx')
                if span_tx:
                    # 이미지 제거하고 텍스트만 추출
                    span_tx_copy = span_tx.__copy__()
                    for img_tag in span_tx_copy.find_all('img'):
                        img_tag.decompose()
                    # strong 태그는 유지하되 텍스트만 추출
                    law_name_text = span_tx_copy.get_text(strip=True)
                    if law_name_text:
                        item['법령명'] = law_name_text
                
                # span.tx2에서 추가 정보 추출 (시행 정보 등)
                span_tx2 = link.find('span', class_='tx2')
                execution_info = ''
                if span_tx2:
                    execution_info = span_tx2.get_text(strip=True)
                    item['시행정보'] = execution_info
                
                # title에서도 시행 정보 추출 시도
                if title and not execution_info:
                    execution_info = title
                
                # 시행일 추출: [시행 미정] 또는 [시행 날짜] 형식
                execution_date = None
                if execution_info:
                    # [시행 미정] 패턴
                    execution_match = re.search(r'\[시행\s*미정\]', execution_info)
                    if execution_match:
                        execution_date = '미정'
                    else:
                        # [시행 날짜] 패턴 (예: [시행 2026. 1. 22.])
                        execution_match = re.search(r'\[시행\s*(?:예정)?\s*:?\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*\]', execution_info)
                        if execution_match:
                            year = execution_match.group(1)
                            month = execution_match.group(2).zfill(2)
                            day = execution_match.group(3).zfill(2)
                            execution_date = f"{year}.{month}.{day}"
                        else:
                            # 다른 날짜 형식 시도 (YYYY.MM.DD)
                            execution_match = re.search(r'\[시행\s*(?:예정)?\s*:?\s*(\d{4}\.\d{1,2}\.\d{1,2})\s*\]', execution_info)
                            if execution_match:
                                execution_date = execution_match.group(1)
                
                if execution_date:
                    item['시행일'] = execution_date
                
                # 공포일 추출: [대통령령 제33887호, 2023. 11. 28., 일부개정] 형식
                # 시행일 패턴 이후에 나오는 날짜가 공포일
                publication_date = None
                if execution_info:
                    # 시행일 패턴 제거 후 남은 부분에서 공포일 찾기
                    # [시행 ...] 이후의 날짜가 공포일
                    execution_removed = re.sub(r'\[시행[^\]]+\]', '', execution_info)
                    
                    # 날짜 패턴 찾기 (YYYY. MM. DD. 형식, 마지막에 점이 있는 것)
                    # 법률/대통령령 제XXX호 뒤에 나오는 날짜
                    pub_match = re.search(r'(?:법률|대통령령|총리령|부령)\s*제\d+호[^,]*,\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.', execution_removed)
                    if pub_match:
                        year = pub_match.group(1)
                        month = pub_match.group(2).zfill(2)
                        day = pub_match.group(3).zfill(2)
                        publication_date = f"{year}.{month}.{day}"
                    else:
                        # 다른 패턴 시도: 두 번째 날짜 패턴 (시행일이 아닌 것)
                        # 모든 날짜 패턴 찾기
                        all_dates = re.findall(r'(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.', execution_removed)
                        if len(all_dates) > 0:
                            # 첫 번째 날짜가 공포일 (시행일은 이미 제거됨)
                            year, month, day = all_dates[0]
                            publication_date = f"{year}.{month.zfill(2)}.{day.zfill(2)}"
                        else:
                            # 다른 형식 시도 (YYYY.MM.DD)
                            pub_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', execution_removed)
                            if pub_match:
                                publication_date = pub_match.group(1)
                
                # 공포일이 없으면 "미정"으로 설정
                if not publication_date:
                    publication_date = '미정'
                
                item['공포일'] = publication_date
            
            # 법령명이 없으면 li의 전체 텍스트에서 추출
            if not item.get('법령명'):
                li_text = li.get_text(strip=True)
                # 이미지 alt 텍스트 제거
                li_text = li_text.replace('앞으로 시행될 법령', '').strip()
                # 숫자와 점 제거 (예: "2. " 같은 것)
                li_text = re.sub(r'^\d+\.\s*', '', li_text)
                if li_text:
                    item['법령명'] = li_text
            
            # 의미있는 정보가 있는 경우만 추가
            if item.get('법령명'):
                # 검색 키워드와 추출된 법령명이 일치하는지 확인
                extracted_law_name = item.get('법령명', '')
                if self.is_same_law(law_name, extracted_law_name):
                    # driver가 없으면 빈 본문으로 설정
                    item['본문'] = ''
                    items.append(item)
                else:
                    # 일치하지 않으면 건너뛰기
                    print(f"    ⏭ 법령명 불일치 건너뜀: 검색='{law_name}' vs 추출='{extracted_law_name}'")
        
        return items
    
    def extract_detail_page(self, detail_url: str) -> Dict:
        """
        상세 페이지에서 정보 추출
        
        Args:
            detail_url: 상세 페이지 URL
            
        Returns:
            상세 정보 딕셔너리
        """
        print(f"    상세 페이지 추출 중: {detail_url}")
        
        soup = self.fetch_page(detail_url, use_selenium=False)
        if soup is None:
            return {}
        
        detail = {}
        detail['detail_url'] = detail_url
        
        # 제목 추출
        title_elem = (
            soup.find('h2') or 
            soup.find('h3') or 
            soup.find('h4') or
            soup.find('div', class_='title') or
            soup.find('div', class_='subject')
        )
        if title_elem:
            detail['제목'] = title_elem.get_text(strip=True)
        
        # 본문 내용 추출
        content_elem = (
            soup.find('div', class_='content') or
            soup.find('div', id='content') or
            soup.find('div', class_='view') or
            soup.find('div', class_='law_content')
        )
        
        if content_elem:
            # 스크립트, 스타일 태그 제거
            for script in content_elem(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            detail['본문'] = content_elem.get_text(separator='\n', strip=True)
        
        # 테이블에서 메타 정보 추출
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    
                    if '법령명' in label or '제목' in label:
                        detail['법령명'] = value
                    elif '법령종류' in label or '종류' in label:
                        detail['법령종류'] = value
                    elif '공포일' in label or '공포' in label:
                        detail['공포일'] = value
                    elif '시행일' in label or '시행' in label or '시행예정일' in label:
                        detail['시행일'] = value
                    elif '소관부처' in label or '소관' in label:
                        detail['소관부처'] = value
        
        return detail
    
    def scrape_all(self, max_items: Optional[int] = None, 
                   extract_detail: bool = True) -> List[Dict]:
        """
        모든 법령에 대해 시행예정법령 검색 및 추출
        
        Args:
            max_items: 최대 항목 수 (None이면 전체)
            extract_detail: 상세 페이지 추출 여부
            
        Returns:
            추출된 시행예정법령 정보 리스트
        """
        all_results = []
        driver = None
        
        try:
            # Selenium driver 생성 (본문 추출용)
            from selenium.webdriver.chrome.options import Options
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ko-KR')
            driver = self._create_webdriver(chrome_options)
            print("✓ Selenium 드라이버 생성 완료 (본문 추출용)")
            
            print(f"\n=== 시행예정법령 검색 시작 (총 {len(self.law_items)}개 법령) ===\n")
            
            for idx, law_item in enumerate(self.law_items, 1):
                if max_items and len(all_results) >= max_items:
                    print(f"\n최대 항목 수({max_items})에 도달했습니다.")
                    break
                
                law_name = law_item.get('법령명', '')  # 괄호 제거된 검색용 법령명
                original_law_name = law_item.get('원본법령명', law_name)  # 원본 법령명
                division = law_item.get('구분', '')
                
                print(f"\n[{idx}/{len(self.law_items)}] {original_law_name} ({division})")
                
                # 검색 URL 생성
                search_url = self.build_search_url(law_name)
                
                # 검색 실행 (driver 재사용)
                soup, _ = self.search_legnotice(law_name, driver=driver)
                if soup is None:
                    print(f"  ⚠ 검색 실패")
                    continue
                
                # 검색 결과 추출 (첫 번째 검색만 디버그 저장)
                save_debug = (idx == 1)
                items = self.extract_legnotice_items(soup, law_name, save_debug=save_debug)
                
                if not items:
                    print(f"  ✓ 시행예정법령 없음")
                    continue
                
                print(f"  ✓ {len(items)}개 시행예정법령 발견")
                
                # 각 항목의 본문 추출 (Selenium으로 링크 클릭)
                if extract_detail and driver:
                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    
                    for item_idx, item in enumerate(items, 1):
                        print(f"    [{item_idx}/{len(items)}] 본문 추출 중: {item.get('법령명', 'N/A')[:50]}...")
                        
                        # 원본법령명 추가
                        item['원본법령명'] = original_law_name
                        
                        # Selenium에서 해당 링크 찾기 및 클릭
                        try:
                            # 검색 결과 페이지에서 해당 법령명을 가진 링크 찾기
                            # span.tx에 법령명이 포함된 링크 찾기
                            law_name_text = item.get('법령명', '')
                            if law_name_text:
                                # 법령명에서 앞의 번호 제거 (예: "2.공인회계사법" -> "공인회계사법")
                                import re
                                clean_law_name = re.sub(r'^\d+\.\s*', '', law_name_text).strip()
                                
                                # Selenium에서 링크 찾기 (여러 방법 시도)
                                link_element = None
                                
                                # 방법 1: span.tx에 법령명이 포함된 링크 찾기
                                try:
                                    # 모든 링크를 찾아서 텍스트 확인
                                    all_links = driver.find_elements(By.TAG_NAME, "a")
                                    for link in all_links:
                                        try:
                                            # span.tx 찾기
                                            span_tx = link.find_element(By.CSS_SELECTOR, "span.tx")
                                            link_text = span_tx.text.strip()
                                            # 이미지 제거를 위해 텍스트만 비교
                                            if clean_law_name in link_text or link_text in clean_law_name:
                                                # "앞으로 시행될 법령" 이미지가 있는지 확인
                                                try:
                                                    img = link.find_element(By.CSS_SELECTOR, "img[alt='앞으로 시행될 법령'], img[src*='bul_list1.gif']")
                                                    link_element = link
                                                    break
                                                except:
                                                    continue
                                        except:
                                            continue
                                except:
                                    pass
                                
                                # 방법 2: title 속성으로 찾기
                                if not link_element:
                                    try:
                                        all_links = driver.find_elements(By.TAG_NAME, "a")
                                        for link in all_links:
                                            title = link.get_attribute('title') or ''
                                            if clean_law_name in title or title and clean_law_name in title:
                                                link_element = link
                                                break
                                    except:
                                        pass
                                
                                if link_element:
                                    # 링크 클릭
                                    print(f"      → 링크 클릭 중...")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", link_element)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", link_element)
                                    time.sleep(2)  # 페이지 로드 대기
                                    
                                    # 상세 페이지 로드 대기
                                    try:
                                        WebDriverWait(driver, 10).until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, "#pDetail, #lawContent, .lawContent, #conts, .conts, #content, .content, .law_view"))
                                        )
                                        time.sleep(1)
                                    except:
                                        time.sleep(2)  # fallback 대기
                                    
                                    # 현재 페이지 URL을 detail_url로 저장
                                    current_url = driver.current_url
                                    if current_url and current_url != search_url:
                                        item['detail_url'] = current_url
                                        print(f"      ✓ 상세 페이지 URL 저장: {current_url}")
                                    
                                    # 현재 페이지에서 본문 추출 (Law_Scraper의 extract_law_detail 사용)
                                    detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                                    law_content = self.extract_law_detail(detail_soup)
                                    
                                    if law_content and len(law_content.strip()) > 0:
                                        item['본문'] = law_content
                                        print(f"      ✓ 본문 추출 완료 ({len(law_content)}자)")
                                    else:
                                        print(f"      ⚠ 본문 추출 실패 또는 빈 내용")
                                        item['본문'] = ''
                                    
                                    # 뒤로 가기
                                    driver.back()
                                    time.sleep(1)
                                else:
                                    print(f"      ⚠ 링크를 찾을 수 없음")
                                    item['본문'] = ''
                        except Exception as e:
                            print(f"      ⚠ 본문 추출 중 오류: {e}")
                            import traceback
                            traceback.print_exc()
                            item['본문'] = ''
                            # 오류 발생 시 뒤로 가기 시도
                            try:
                                driver.back()
                                time.sleep(1)
                            except:
                                pass
                        
                        all_results.append(item)
                        time.sleep(self.delay)
                else:
                    # driver가 없거나 extract_detail이 False이면 본문 없이 추가
                    for item in items:
                        item['원본법령명'] = original_law_name
                        if '본문' not in item:
                            item['본문'] = ''
                        all_results.append(item)
                
                time.sleep(self.delay)
        finally:
            # Selenium driver 종료
            if driver:
                driver.quit()
                print("✓ Selenium 드라이버 종료 완료")
        
        return all_results

def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='법제처 시행예정법령 스크래퍼')
    parser.add_argument('--csv-path', type=str, default=None,
                       help='법령명 목록 CSV 파일 경로')
    parser.add_argument('--max-items', type=int, default=None,
                       help='최대 항목 수')
    parser.add_argument('--no-detail', action='store_true',
                       help='상세 페이지 추출 안 함')
    parser.add_argument('--content-all', action='store_true',
                       help='본문 내용을 전체로 가져옵니다 (기본값: 4000자 제한)')
    
    args = parser.parse_args()
    
    data_process(delay=1.0, csv_path=args.csv_path, content_all=args.content_all,max_items=args.max_items, no_detail=args.no_detail)
    
   
def data_process(delay, csv_path=None, content_all=None, max_items=None, no_detail=None):
    print("=== 법제처 시행예정법령 스크래퍼 시작 ===\n")

    scraper = LawLegNoticeScraper(delay, csv_path, content_all)
    
    # 스크래핑 실행
    results = scraper.scrape_all(
        max_items=max_items,
        extract_detail=not no_detail
    )

    print(f"\n=== 스크래핑 완료: {len(results)}개 항목 ===")
    
    # 날짜 필드 정규화 및 본문 길이 제한
    for item in results:
        # 날짜 필드 정규화
        if '시행일' in item:
            item['시행일'] = scraper.normalize_date_format(item.get('시행일', ''))
        if '공포일' in item:
            item['공포일'] = scraper.normalize_date_format(item.get('공포일', ''))
        
        # 본문 내용 처리 (content_all 플래그에 따라 길이 제한)
        content = item.get('본문', '') or ''
        # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # content_all이 False인 경우에만 4000자로 제한
        if not scraper.content_all and len(content) > 4000:
            content = content[:4000]
        item['본문'] = content
    
    # 결과 저장
    output_data = {
        'url': scraper.SEARCH_URL_TEMPLATE.format(''),
        'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(results),
        'results': results
    }
    
    # JSON 저장
    json_path = scraper.json_path
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장 완료: {json_path}")
    
    # CSV 저장
    if results:
        fieldnames = set()
        for item in results:
            fieldnames.update(item.keys())
        fieldnames = sorted(list(fieldnames))
        
        csv_path = scraper.output_dir / "csv" / "law_legnotice_scraper.csv"
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in results:
                csv_item = {}
                for key in fieldnames:
                    value = item.get(key, '')
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False)
                    elif value is None:
                        value = ''
                    elif not isinstance(value, str):
                        value = str(value)
                    value = value.replace('\n', ' ').replace('\r', ' ')
                    csv_item[key] = value
                writer.writerow(csv_item)
        
        print(f"CSV 저장 완료: {csv_path}")
    
    print("\n=== 완료 ===")

# -------------------------------------------------
# Health Check 모드
# -------------------------------------------------
from common.health_schema import base_health_output
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_mapper import apply_health_error
from common.common_http import check_url_status
from common.url_health_mapper import map_urlstatus_to_health_error
from common.constants import URLStatus

def law_legnotice_health_check() -> dict:
    """
    법제처 국가법령정보센터 - 시행예정법령 Health Check
    (시행예정법령 탭 이동 + lsViewWideAll 상세 페이지 접근)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    TARGET_URL = "https://www.law.go.kr/LSW/lsSc.do?menuId=1&subMenuId=23"

    scraper = LawLegNoticeScraper(delay=1.0)

    result = base_health_output(
        auth_src="법제처 > 국가법령정보센터 > 시행예정법령",
        scraper_id="LAW_LEGNOTICE",
        target_url=TARGET_URL,
    )

    driver = None

    try:
        # =================================================
        # 1. Selenium Driver 생성 및 페이지 접근
        # =================================================
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--lang=ko-KR")

        driver = scraper._create_webdriver(chrome_options)
        driver.get(TARGET_URL)

        # result["checks"]["search_page"]["success"] = True
        # result["checks"]["search_page"]["message"] = "검색 페이지 접근 성공"

        # =================================================
        # 2. 시행예정법령 탭 이동 (tab3)
        # =================================================
        try:
            # ======================================================
            # HTTP 접근성 사전 체크
            # ======================================================
            http_result = check_url_status(
                TARGET_URL,
                use_selenium=True,
                allow_fallback=False,
            )

            result["checks"]["http"] = {
                "ok": http_result["status"] == URLStatus.OK,
                "status": http_result["status"].name,
                "status_code": http_result["http_code"],
            }

            if http_result["status"] != URLStatus.OK:
                raise HealthCheckError(
                    map_urlstatus_to_health_error(http_result["status"]),
                    "목록 페이지 HTTP 접근 실패",
                    target=TARGET_URL,
                )
                    
            tab_elem = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "tab3"))
            )

            driver.execute_script("arguments[0].scrollIntoView(true);", tab_elem)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", tab_elem)

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td.tl a"))
            )
            time.sleep(1)

            # result["checks"]["tab_move"]["success"] = True
            # result["checks"]["tab_move"]["message"] = "시행예정법령 탭 이동 성공"

        except Exception as e:
            # result["checks"]["tab_move"]["message"] = str(e)
            # return result
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "시행예정법령 탭 이동 실패",
                ""
            )        

        # =================================================
        # 3. 목록 1건 추출
        # =================================================
        first_link = driver.find_element(By.CSS_SELECTOR, "td.tl a")
        title = first_link.text.strip()

        result["checks"]["list"] = {
            "success": True,
            "count": 1,
            "title": title
        }

        # =================================================
        # 4. 상세 페이지 접근 (lsViewWideAll JS 직접 실행)
        # =================================================
        onclick_js = first_link.get_attribute("onclick")

        if not onclick_js or "lsViewWideAll" not in onclick_js:
            result["error"] = "lsViewWideAll onclick 속성 없음"
            return result

        # onclick JS 실행
        driver.execute_script(onclick_js)
        time.sleep(2)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "#lawContent, #pDetail, .lawContent, #content, .content"
            ))
        )

        detail_url = driver.current_url
        soup = BeautifulSoup(driver.page_source, "lxml")

        content = scraper.extract_law_detail(soup)
        content_length = len(content) if content else 0

        result["checks"]["detail"] = {
            "url": detail_url,
            "success": True,
            "content_length": content_length
        }

        # ======================================================
        # SUCCESS
        # ======================================================
        result["ok"] = True
        result["status"] = "OK"
        return result
    
    except HealthCheckError as he:
        apply_health_error(result, he)
        return result
    
    except Exception as e:
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.UNEXPECTED_ERROR,
                str(e)
            )
        )
        return result

    finally:
        if driver:
            driver.quit()

# ==================================================
# scheduler call
# ==================================================
def run():
    main()

if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="법제처-국가법령정보센터-시행법령")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Health Check만 실행하고 종료",
    )

    args = parser.parse_args()

    if args.check:
        health = law_legnotice_health_check()
        print(json.dumps(health, ensure_ascii=False, indent=2))
        sys.exit(0)
        
    main()

