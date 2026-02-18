# moleg_scraper_v2.py

"""
법제처 입법예고 스크래퍼
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
import csv
import re
from datetime import datetime, date
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from common.base_scraper import BaseScraper


class MolegScraper(BaseScraper):
    """법제처 입법예고 스크래퍼"""
    
    BASE_URL = "https://www.moleg.go.kr"
    LIST_URL = "https://www.moleg.go.kr/lawinfo/molegMakingList.mo?mid=a10514020000"
    DEFAULT_CSV_PATH = "Moleg_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: str = None):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            csv_path: 법령명 목록이 있는 CSV 파일 경로
        """
        super().__init__(delay)
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "csv").mkdir(parents=True, exist_ok=True)
        
        # JSON 파일 경로
        self.json_path = self.output_dir / "json" / "moleg_scraper.json"
        
        # CSV 파일에서 법령명 읽기
        self.law_items = self._load_target_laws_from_csv(csv_path or self.DEFAULT_CSV_PATH)
        print(f"✓ 법령 목록 로드: {len(self.law_items)}개")
    
    def _remove_parentheses(self, text: str) -> str:
        """
        법령명에서 괄호와 그 내용을 제거
        
        Args:
            text: 원본 법령명
            
        Returns:
            괄호가 제거된 법령명
        """
        # 한글 괄호와 영문 괄호 모두 처리
        # 예: "법률(2026.1.1부터)" -> "법률"
        cleaned = re.sub(r'[\(（].*?[\)）]', '', text)
        return cleaned.strip()
    
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
            '전체기관 입법예고 바로가기',
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 불필요한 키워드가 포함된 라인 제거
            should_remove = False
            for keyword in remove_keywords:
                if keyword in line:
                    should_remove = True
                    break
            
            if should_remove:
                continue
            
            # '전자메일'로 시작하는 라인 제거 (연락처 정보)
            if line.startswith('전자메일') or line.startswith('전화번호') or line.startswith('담당부서'):
                # 하지만 실제 본문 내용에 '전자메일'이 포함될 수 있으므로, 
                # 단독 라인이고 짧은 경우만 제거
                if len(line) < 50:  # 짧은 라인만 제거 (연락처 정보)
                    continue
            
            cleaned_lines.append(line)
        
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
    
    def build_search_url(self, law_name: str, page: int = 1) -> str:
        """
        법령명으로 검색 URL 생성
        
        Args:
            law_name: 법령명
            page: 페이지 번호 (기본값: 1)
            
        Returns:
            검색 URL
        """
        # URL 인코딩
        encoded_name = quote_plus(law_name)
        # 검색 URL 생성 (keyWord 파라미터에 법령명 추가)
        url = f"{self.LIST_URL}&pageCnt=10&lsClsCd=&keyField=lmNm&keyWord={encoded_name}&stYdFmt=&edYdFmt="
        if page > 1:
            url += f"&currentPage={page}"
        return url
    
    def fetch_list_page(self, law_name: str = None, page: int = 1) -> Optional[BeautifulSoup]:
        """
        입법예고 목록 페이지 가져오기
        
        Args:
            law_name: 검색할 법령명 (None이면 전체 목록)
            page: 페이지 번호 (기본값: 1)
            
        Returns:
            BeautifulSoup 객체 또는 None
        """
        if law_name:
            # 법령명으로 검색 URL 생성
            url = self.build_search_url(law_name, page)
            print(f"검색 페이지 {page} 가져오는 중: {law_name} - {url}")
        else:
            # 전체 목록 (기존 방식)
            url = f"{self.LIST_URL}&currentPage={page}"
            print(f"목록 페이지 {page} 가져오는 중: {url}")
        
        soup = self.fetch_page(url, use_selenium=False)
        return soup
    
    def extract_list_items(self, soup: BeautifulSoup) -> List[Dict]:
        """
        목록 페이지에서 항목 정보 추출
        
        Args:
            soup: BeautifulSoup 객체
            
        Returns:
            항목 정보 리스트
        """
        if soup is None:
            return []
        
        items = []
        
        # 테이블에서 항목 추출
        # 웹사이트 구조에 맞게 선택자 조정 필요
        table = soup.find('table')
        if not table:
            print("  ⚠ 테이블을 찾을 수 없습니다.")
            return []
        
        rows = table.find_all('tr')
        if not rows:
            print("  ⚠ 테이블 행을 찾을 수 없습니다.")
            return []
        
        # 헤더 행 건너뛰기
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            
            item = {}
            
            # 링크 추출 (보통 두 번째 셀에 제목과 링크가 있음)
            link_cell = None
            title_text = ''
            
            # 각 셀에서 링크 찾기
            for cell in cells:
                link = cell.find('a')
                if link and link.get('href'):
                    link_cell = link
                    title_text = link.get_text(strip=True)
                    href = link.get('href')
                    # 상대 경로를 절대 경로로 변환
                    if href.startswith('/'):
                        item['detail_url'] = urljoin(self.BASE_URL, href)
                    elif href.startswith('http'):
                        item['detail_url'] = href
                    else:
                        item['detail_url'] = urljoin(self.LIST_URL, href)
                    break
            
            if not link_cell:
                continue
            
            # 제목 설정
            item['title'] = title_text
            
            # 법령 종류 추출 (첫 번째 셀)
            if len(cells) > 0:
                law_type_text = cells[0].get_text(strip=True)
                # 링크가 아닌 경우만 법령 종류로 사용
                if not cells[0].find('a'):
                    item['law_type'] = law_type_text
            
            # 기간 추출 (마지막 셀)
            if len(cells) > 1:
                period_text = cells[-1].get_text(strip=True)
                # 날짜 형식인지 확인 (YYYY-MM-DD 또는 YYYY.MM.DD)
                import re
                if re.match(r'\d{4}[-.]\d{2}[-.]\d{2}', period_text) or '~' in period_text:
                    item['period'] = period_text
            
            items.append(item)
        
        print(f"  ✓ {len(items)}개 항목 추출")
        return items
    
    def extract_detail_page(self, detail_url: str, save_debug: bool = False) -> Dict:
        """
        상세 페이지에서 정보 추출
        
        Args:
            detail_url: 상세 페이지 URL
            save_debug: 디버그 HTML 저장 여부
            
        Returns:
            상세 정보 딕셔너리
        """
        print(f"  상세 페이지 추출 중: {detail_url}")
        
        soup = self.fetch_page(detail_url, use_selenium=False)
        if soup is None:
            return {}
        
        # 디버그 HTML 저장 (첫 번째 페이지만)
        if save_debug:
            debug_dir = self.output_dir / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "debug_moleg_detail.html"
            if not debug_file.exists():
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(soup.prettify())
                print(f"  ✓ 디버그 HTML 저장: {debug_file}")
        
        detail = {}
        detail['detail_url'] = detail_url
        
        # 본문 영역 찾기: #listForm > div > div.tb_contents
        content_area = None
        
        # 방법 1: CSS 셀렉터로 직접 찾기 (#listForm > div > div.tb_contents)
        list_form = soup.find('form', id='listForm')
        if list_form:
            # listForm 내부의 div > div.tb_contents 찾기
            inner_div = list_form.find('div')
            if inner_div:
                content_area = inner_div.find('div', class_='tb_contents')
        
        # 방법 2: 직접 class로 찾기 (대체 방법)
        if not content_area:
            content_area = soup.find('div', class_='tb_contents')
        
        # 방법 3: 기존 방식 (fallback)
        if not content_area:
            content_area = soup.find('div', class_='view') or soup.find('div', id='view') or soup.find('div', class_='content')
        
        # 제목 추출 - 본문 영역에서 찾기
        if content_area:
            # 제목은 보통 h2, h3, 또는 strong 태그에 있음
            title_elem = content_area.find('h2') or content_area.find('h3') or content_area.find('h4')
            if not title_elem:
                # strong 태그나 큰 텍스트 찾기
                title_elem = content_area.find('strong') or content_area.find('b')
            if title_elem:
                detail['title'] = title_elem.get_text(strip=True)
        
        # 본문 내용 추출
        if content_area:
            # 스크립트, 스타일, 네비게이션 태그 제거
            for script in content_area(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            
            # 접근성 링크 및 불필요한 요소 제거
            # '본문으로 바로가기', '주메뉴 바로가기' 등의 링크 제거
            for link in content_area.find_all('a', href=True):
                link_text = link.get_text(strip=True)
                if any(keyword in link_text for keyword in ['본문으로', '주메뉴', '바로가기', '스킵']):
                    link.decompose()
            
            # '이 누리집은 대한민국 공식 전자정부 누리집입니다.' 같은 텍스트 제거
            for elem in content_area.find_all(['div', 'span', 'p']):
                elem_text = elem.get_text(strip=True)
                if any(keyword in elem_text for keyword in ['이 누리집은', '공식 전자정부', '100%']):
                    elem.decompose()
            
            # 테이블 헤더 정보 제거 (공고번호, 법령종류 등은 이미 별도로 추출됨)
            # 테이블의 첫 번째 행(헤더) 제거
            for table in content_area.find_all('table'):
                first_row = table.find('tr')
                if first_row:
                    # 헤더 행인지 확인 (th 태그가 있으면 헤더)
                    if first_row.find('th'):
                        first_row.decompose()
            
            content_text = content_area.get_text(separator='\n', strip=True)
            # 불필요한 텍스트 라인 제거
            cleaned_content = self._clean_content_text(content_text)
            # 본문은 최대 4000자로 제한
            if cleaned_content and len(cleaned_content) > 4000:
                cleaned_content = cleaned_content[:4000]
            detail['content'] = cleaned_content
        else:
            # 본문 영역을 찾지 못한 경우 경고
            print(f"  ⚠ 본문 영역(#listForm > div > div.tb_contents)을 찾을 수 없습니다.")
            detail['content'] = ''
        
        # 테이블에서 메타 정보 추출 (더 정확하게)
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    
                    # 라벨에 따라 적절한 필드에 저장
                    if '공고번호' in label or '공고' in label:
                        detail['notice_no'] = value
                    elif '법령종류' in label or '종류' in label:
                        detail['law_type'] = value
                    elif '입안유형' in label or '유형' in label:
                        detail['draft_type'] = value
                    elif '예고기간' in label or '입법예고기간' in label or ('기간' in label and '예고' in label):
                        detail['period'] = value
                    elif '담당부서' in label or '부서' in label:
                        detail['department'] = value
                    elif '전화번호' in label or '전화' in label:
                        detail['phone'] = value
                    elif '전자메일' in label or '이메일' in label or '메일' in label:
                        detail['email'] = value
                    elif '소관부처' in label or '소관' in label:
                        detail['ministry'] = value
        
        # dl/dt/dd 구조에서도 정보 추출
        dl_list = soup.find_all('dl')
        for dl in dl_list:
            dt_list = dl.find_all('dt')
            dd_list = dl.find_all('dd')
            for dt, dd in zip(dt_list, dd_list):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                if '공고번호' in label or '공고' in label:
                    detail['notice_no'] = value
                elif '법령종류' in label or '종류' in label:
                    detail['law_type'] = value
                elif '입안유형' in label or '유형' in label:
                    detail['draft_type'] = value
                elif '예고기간' in label or '입법예고기간' in label:
                    detail['period'] = value
                elif '담당부서' in label or '부서' in label:
                    detail['department'] = value
                elif '전화번호' in label or '전화' in label:
                    detail['phone'] = value
                elif '전자메일' in label or '이메일' in label or '메일' in label:
                    detail['email'] = value
                elif '소관부처' in label or '소관' in label:
                    detail['ministry'] = value
        
        # div 구조에서 정보 추출 (label-value 형태)
        info_divs = soup.find_all('div', class_=lambda x: x and ('info' in x.lower() or 'detail' in x.lower() or 'meta' in x.lower()))
        for div in info_divs:
            # label과 value가 나란히 있는 경우
            labels = div.find_all(['span', 'strong', 'b', 'label'], class_=lambda x: x and 'label' in x.lower() if x else False)
            for label_elem in labels:
                label_text = label_elem.get_text(strip=True)
                # 다음 형제 요소나 부모의 다음 형제 찾기
                value_elem = label_elem.find_next_sibling()
                if not value_elem:
                    value_elem = label_elem.parent.find_next_sibling() if label_elem.parent else None
                if value_elem:
                    value_text = value_elem.get_text(strip=True)
                    
                    if '공고번호' in label_text or '공고' in label_text:
                        detail['notice_no'] = value_text
                    elif '법령종류' in label_text or '종류' in label_text:
                        detail['law_type'] = value_text
                    elif '입안유형' in label_text or '유형' in label_text:
                        detail['draft_type'] = value_text
                    elif '예고기간' in label_text or '입법예고기간' in label_text:
                        detail['period'] = value_text
                    elif '담당부서' in label_text or '부서' in label_text:
                        detail['department'] = value_text
                    elif '전화번호' in label_text or '전화' in label_text:
                        detail['phone'] = value_text
                    elif '전자메일' in label_text or '이메일' in label_text or '메일' in label_text:
                        detail['email'] = value_text
                    elif '소관부처' in label_text or '소관' in label_text:
                        detail['ministry'] = value_text
        
        # 텍스트 기반 패턴 매칭으로 정보 추출 (테이블이나 구조화되지 않은 경우)
        content_text = soup.get_text()
        import re
        
        # 공고번호 패턴 (제2025-49호 형식)
        notice_match = re.search(r'공고번호\s*[:\s]*제?(\d{4}-\d+)호?', content_text)
        if notice_match and 'notice_no' not in detail:
            detail['notice_no'] = f"제{notice_match.group(1)}호"
        
        # 전화번호 패턴
        phone_match = re.search(r'전화번호\s*[:\s]*(\d{2,3}-\d{3,4}-\d{4})', content_text)
        if phone_match and 'phone' not in detail:
            detail['phone'] = phone_match.group(1)
        
        # 이메일 패턴
        email_match = re.search(r'전자메일\s*[:\s]*([a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content_text)
        if email_match and 'email' not in detail:
            detail['email'] = email_match.group(1)
        
        # 예고기간 패턴 (YYYY-MM-DD~YYYY-MM-DD)
        period_match = re.search(r'예고기간\s*[:\s]*(\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2})', content_text)
        if period_match and 'period' not in detail:
            detail['period'] = period_match.group(1).replace(' ', '')
        
        # 첨부파일 링크 추출 (더 정확하게)
        file_links = []
        
        # 파일 다운로드 영역 찾기 (다양한 클래스명 시도)
        file_section = (
            soup.find('div', class_='file') or 
            soup.find('div', class_='attach') or 
            soup.find('div', class_='download') or
            soup.find('div', class_='attachment') or
            soup.find('div', id='file') or
            soup.find('div', id='attach')
        )
        
        if file_section:
            links = file_section.find_all('a', href=True)
        else:
            # 본문 영역 내의 링크만 찾기
            if content_area:
                links = content_area.find_all('a', href=True)
            else:
                links = soup.find_all('a', href=True)
        
        seen_urls = set()  # 중복 제거
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # 파일 확장자 확인
            file_extensions = ['.pdf', '.doc', '.docx', '.hwp', '.hwpx', '.xls', '.xlsx', '.zip', '.txt']
            if any(ext in href.lower() for ext in file_extensions):
                # 상대 경로를 절대 경로로 변환
                if href.startswith('/'):
                    file_url = urljoin(self.BASE_URL, href)
                elif href.startswith('http'):
                    file_url = href
                else:
                    file_url = urljoin(detail_url, href)
                
                # 중복 제거
                if file_url in seen_urls:
                    continue
                seen_urls.add(file_url)
                
                # 파일명 추출
                filename = text.strip()
                if not filename or filename == '다운로드' or filename == '파일':
                    # URL에서 파일명 추출
                    filename = href.split('/')[-1].split('?')[0]
                    # URL 디코딩
                    from urllib.parse import unquote
                    filename = unquote(filename)
                
                file_links.append({
                    'filename': filename,
                    'url': file_url
                })
        
        if file_links:
            detail['attachments'] = file_links
        
        # 추가 정보: 본문에서 추출 가능한 구조화된 정보
        # 법령안 섹션 찾기
        law_section = None
        for section in soup.find_all(['div', 'section', 'article']):
            section_text = section.get_text(strip=True)
            if '법령안' in section_text or '제정안' in section_text or '개정안' in section_text:
                law_section = section
                break
        
        if law_section:
            # 법령안 내용 추출
            law_content = law_section.get_text(separator='\n', strip=True)
            if law_content and len(law_content) > 50:  # 의미있는 내용만
                detail['law_draft_content'] = law_content
        
        # 의견제출 섹션 찾기
        opinion_section = None
        for section in soup.find_all(['div', 'section', 'article']):
            section_text = section.get_text(strip=True)
            if '의견제출' in section_text or '의견' in section_text:
                opinion_section = section
                break
        
        if opinion_section:
            # 의견제출 내용 추출
            opinion_content = opinion_section.get_text(separator='\n', strip=True)
            if opinion_content and len(opinion_content) > 50:
                detail['opinion_submission_info'] = opinion_content
        
        return detail
    
    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """
        전체 페이지 수 추출
        
        Args:
            soup: 목록 페이지 BeautifulSoup 객체
            
        Returns:
            전체 페이지 수
        """
        if soup is None:
            return 1
        
        # 먼저 검색 결과가 있는지 확인
        page_text = soup.get_text()
        
        # "총 0건" 같은 메시지 확인
        import re
        total_match = re.search(r'총\s*(\d+)\s*건', page_text)
        if total_match:
            total_count = int(total_match.group(1))
            if total_count == 0:
                return 0
        
        # 페이지네이션 찾기
        pagination = soup.find('div', class_='pagination') or soup.find('div', class_='paging')
        if pagination:
            # 마지막 페이지 링크 찾기
            links = pagination.find_all('a')
            if links:
                last_page_link = links[-1]
                if last_page_link:
                    href = last_page_link.get('href', '')
                    if 'currentPage' in href:
                        try:
                            params = parse_qs(urlparse(href).query)
                            if 'currentPage' in params:
                                return int(params['currentPage'][0])
                        except:
                            pass
                    # 링크 텍스트에서 페이지 번호 추출 시도
                    link_text = last_page_link.get_text(strip=True)
                    page_match = re.search(r'(\d+)', link_text)
                    if page_match:
                        try:
                            return int(page_match.group(1))
                        except:
                            pass
        
        # 페이지 번호 텍스트에서 추출 시도 (예: "1/1", "1 / 1")
        match = re.search(r'(\d+)\s*/\s*(\d+)', page_text)
        if match:
            return int(match.group(2))
        
        # 테이블에 항목이 있으면 최소 1페이지
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            if len(rows) > 1:  # 헤더 제외하고 데이터 행이 있으면
                return 1
        
        return 0
    
    def parse_date_from_period(self, period_str: str) -> Optional[date]:
        """
        예고기간 문자열에서 시작일자 추출
        
        Args:
            period_str: 예고기간 문자열 (예: "2025-11-27~2025-12-11")
            
        Returns:
            시작일자 date 객체 또는 None
        """
        if not period_str:
            return None
        
        import re
        # 날짜 패턴 찾기 (YYYY-MM-DD 형식)
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{4}\.\d{2}\.\d{2})',  # YYYY.MM.DD
            r'(\d{4}/\d{2}/\d{2})',  # YYYY/MM/DD
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, period_str)
            if match:
                date_str = match.group(1)
                # 구분자 통일
                date_str = date_str.replace('.', '-').replace('/', '-')
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    continue
        
        return None
    
    def get_last_scraped_date(self) -> Optional[date]:
        """
        이전 스크래핑 결과에서 마지막 날짜 추출
        
        Returns:
            마지막 스크래핑된 항목의 시작일자 또는 None
        """
        if not self.json_path.exists():
            return None
        
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 먼저 저장된 last_scraped_date 필드 확인
            last_date_str = data.get('last_scraped_date')
            if last_date_str:
                try:
                    return datetime.strptime(last_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # 저장된 필드가 없으면 results에서 계산
            results = data.get('results', [])
            if not results:
                return None
            
            # 모든 항목의 예고기간에서 시작일자 추출
            dates = []
            for item in results:
                period = item.get('period', '')
                if period:
                    parsed_date = self.parse_date_from_period(period)
                    if parsed_date:
                        dates.append(parsed_date)
            
            if dates:
                # 가장 최근 날짜 반환
                return max(dates)
            
            return None
        except Exception as e:
            print(f"  ⚠ 이전 스크래핑 결과 읽기 실패: {e}")
            return None
    
    def should_scrape_item(self, item: Dict, start_date: Optional[date] = None, 
                          end_date: Optional[date] = None) -> bool:
        """
        항목을 스크래핑할지 결정
        
        Args:
            item: 항목 정보 딕셔너리
            start_date: 시작일자 (이 날짜 이후만 스크래핑)
            end_date: 종료일자 (이 날짜 이전만 스크래핑)
            
        Returns:
            스크래핑할지 여부
        """
        period = item.get('period', '')
        if not period:
            # 날짜가 없으면 일단 포함 (나중에 상세 페이지에서 확인)
            return True
        
        item_date = self.parse_date_from_period(period)
        if not item_date:
            # 날짜 파싱 실패 시 일단 포함
            return True
        
        # 시작일자 체크
        if start_date and item_date < start_date:
            return False
        
        # 종료일자 체크
        if end_date and item_date > end_date:
            return False
        
        return True
    
    def scrape_all(self, max_pages: Optional[int] = None, max_items: Optional[int] = None,
                   start_date: Optional[date] = None, end_date: Optional[date] = None,
                   skip_date_filter: bool = False) -> List[Dict]:
        """
        모든 입법예고 항목 스크래핑 (list.csv의 법령명으로 검색)
        
        Args:
            max_pages: 각 법령당 최대 페이지 수 (None이면 전체)
            max_items: 전체 최대 항목 수 (None이면 전체)
            start_date: 시작일자 (이 날짜 이후만 스크래핑)
            end_date: 종료일자 (이 날짜 이전만 스크래핑)
            skip_date_filter: True이면 마지막 날짜 필터를 무시하고 전체 스크래핑
            
        Returns:
            스크래핑된 항목 리스트
        """
        all_items = []
        
        # 기본적으로 이전 스크래핑 이후만 가져오기 (skip_date_filter가 False인 경우)
        if not skip_date_filter:
            last_date = self.get_last_scraped_date()
            if last_date:
                if start_date is None or last_date > start_date:
                    start_date = last_date
                print(f"이전 스크래핑 마지막 날짜: {last_date.strftime('%Y-%m-%d')} 이후 항목만 스크래핑합니다.")
            else:
                print("이전 스크래핑 결과가 없어 전체 항목을 스크래핑합니다.")
        else:
            print("날짜 필터를 무시하고 전체 항목을 스크래핑합니다.")
        
        # 날짜 필터 정보 출력
        if start_date or end_date:
            date_info = []
            if start_date:
                date_info.append(f"시작일: {start_date.strftime('%Y-%m-%d')}")
            if end_date:
                date_info.append(f"종료일: {end_date.strftime('%Y-%m-%d')}")
            print(f"날짜 필터: {', '.join(date_info)}")
        
        print(f"\n=== 입법예고 검색 시작 (총 {len(self.law_items)}개 법령) ===\n")
        
        # 각 법령명에 대해 검색
        for idx, law_item in enumerate(self.law_items, 1):
            if max_items and len(all_items) >= max_items:
                print(f"\n최대 항목 수({max_items})에 도달했습니다.")
                break
            
            law_name = law_item.get('법령명', '')  # 괄호 제거된 검색용 법령명
            original_law_name = law_item.get('원본법령명', law_name)  # 원본 법령명
            division = law_item.get('구분', '')
            
            print(f"\n[{idx}/{len(self.law_items)}] {original_law_name} ({division})")
            
            # 첫 페이지로 전체 페이지 수 확인
            first_page = self.fetch_list_page(law_name, page=1)
            if first_page is None:
                print(f"  ⚠ 검색 실패")
                continue
            
            total_pages = self.get_total_pages(first_page)
            if total_pages == 0:
                print(f"  ✓ 입법예고 없음")
                continue
            
            print(f"  전체 페이지 수: {total_pages}")
            
            if max_pages:
                total_pages = min(total_pages, max_pages)
            
            # 날짜 기준으로 조기 종료 플래그
            stop_by_date = False
            
            # 각 페이지에서 항목 수집
            for page in range(1, total_pages + 1):
                if stop_by_date:
                    print(f"  날짜 기준에 의해 스크래핑을 중단합니다.")
                    break
                
                if max_items and len(all_items) >= max_items:
                    break
                
                print(f"  === 페이지 {page}/{total_pages} ===")
                
                soup = self.fetch_list_page(law_name, page=page)
                if soup is None:
                    continue
                
                items = self.extract_list_items(soup)
                
                if not items:
                    continue
                
                # 각 항목의 상세 정보 추출
                for i, item in enumerate(items, 1):
                    if max_items and len(all_items) >= max_items:
                        print(f"\n최대 항목 수({max_items})에 도달했습니다.")
                        break
                    
                    # 원본법령명 추가
                    item['원본법령명'] = original_law_name
                    item['검색법령명'] = law_name
                    
                    # 날짜 필터링
                    if not self.should_scrape_item(item, start_date, end_date):
                        period = item.get('period', 'N/A')
                        print(f"    ⏭ 날짜 필터에 의해 건너뜀: {item.get('title', 'N/A')[:50]}... (기간: {period})")
                        
                        # 시작일자보다 이전이면 더 이상 수집 불필요 (날짜순 정렬 가정)
                        if start_date:
                            item_date = self.parse_date_from_period(period)
                            if item_date and item_date < start_date:
                                stop_by_date = True
                                print(f"    날짜 기준({start_date.strftime('%Y-%m-%d')}) 이전 항목 발견. 스크래핑 중단.")
                                break
                        continue
                    
                    print(f"    [{len(all_items) + 1}] {item.get('title', 'N/A')}")
                    
                    # 상세 페이지 추출 (첫 번째 항목만 디버그 HTML 저장)
                    detail_url = item.get('detail_url')
                    if detail_url:
                        save_debug = (len(all_items) == 0)  # 첫 번째 항목만
                        detail = self.extract_detail_page(detail_url, save_debug=save_debug)
                        # 목록 정보와 상세 정보 병합
                        item.update(detail)
                        
                        # 상세 페이지에서 날짜 정보를 다시 확인
                        detail_period = detail.get('period', item.get('period', ''))
                        if detail_period and not self.should_scrape_item({'period': detail_period}, start_date, end_date):
                            print(f"    ⏭ 상세 페이지 날짜 필터에 의해 제외됨: {detail_period}")
                            continue
                    
                    all_items.append(item)
                    time.sleep(self.delay)
                
                if max_items and len(all_items) >= max_items:
                    break
                
                time.sleep(self.delay)
            
            time.sleep(self.delay)
        
        return all_items


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='법제처 입법예고 스크래퍼')
    parser.add_argument('--csv-path', type=str, default=None,
                       help='법령명 목록 CSV 파일 경로')
    parser.add_argument('--max-items', type=int, help='최대 항목 수')
    parser.add_argument('--max-pages', type=int, help='각 법령당 최대 페이지 수')
    parser.add_argument('--start-date', type=str, help='시작일자 (YYYY-MM-DD 형식)')
    parser.add_argument('--end-date', type=str, help='종료일자 (YYYY-MM-DD 형식)')
    parser.add_argument('--all', action='store_true', 
                       help='마지막 날짜 필터를 무시하고 전체 항목 스크래핑')
    
    args = parser.parse_args()
    
    print("=== 법제처 입법예고 스크래퍼 시작 ===\n")
    scraper = MolegScraper(delay=1.0, csv_path=args.csv_path)
    
    # 날짜 파싱
    start_date = None
    end_date = None
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"⚠ 시작일자 형식 오류: {args.start_date} (YYYY-MM-DD 형식 필요)")
    
    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"⚠ 종료일자 형식 오류: {args.end_date} (YYYY-MM-DD 형식 필요)")
    
    # 스크래핑 실행
    # 기본적으로 마지막 날짜 이후만 스크래핑 (--all 플래그가 있으면 전체 스크래핑)
    skip_date_filter = args.all
    
    if args.max_items:
        print(f"테스트 모드: 처음 {args.max_items}개 항목만 스크래핑")
        results = scraper.scrape_all(
            max_items=args.max_items,
            max_pages=args.max_pages,
            start_date=start_date,
            end_date=end_date,
            skip_date_filter=skip_date_filter
        )
    else:
        if not skip_date_filter:
            print("마지막 스크래핑 날짜 이후 항목만 스크래핑합니다.")
        results = scraper.scrape_all(
            max_pages=args.max_pages,
            start_date=start_date,
            end_date=end_date,
            skip_date_filter=skip_date_filter
        )
    
    print(f"\n=== 스크래핑 완료: {len(results)}개 항목 ===")
    
    # 결과 저장
    # 스크래핑 실행 날짜를 last_scraped_date로 사용
    last_scraped_date = time.strftime('%Y-%m-%d')
    
    # Law_LegNotice_Scraper 형식의 한글 컬럼 추가
    def parse_period_to_execution_info(period_str: str) -> tuple:
        """
        예고기간 문자열을 시행정보, 시행일, 공포일로 변환
        
        Args:
            period_str: 예고기간 문자열 (예: "2010-03-09~2010-03-29")
            
        Returns:
            (시행정보, 시행일, 공포일) 튜플
        """
        if not period_str:
            return ('', '', '')
        
        import re
        # 날짜 패턴 찾기 (YYYY-MM-DD 형식)
        date_pattern = r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})'
        dates = re.findall(date_pattern, period_str)
        
        # 시행정보와 시행일은 비워둠
        시행정보 = ''
        시행일 = ''
        
        if len(dates) >= 1:
            # 시작일(앞의 날짜)을 공포일로 설정
            start_date = dates[0]
            # 형식: "YYYY.MM.DD"
            공포일 = f"{start_date[0]}.{start_date[1].zfill(2)}.{start_date[2].zfill(2)}"
        else:
            공포일 = ''
        
        return (시행정보, 시행일, 공포일)
    
    # 각 결과 항목에 한글 컬럼 추가
    for item in results:
        # 법령명: 원본법령명 우선, 없으면 검색법령명
        if '법령명' not in item:
            item['법령명'] = item.get('원본법령명', item.get('검색법령명', ''))
        
        # 시행정보, 시행일, 공포일 추가
        period = item.get('period', '')
        시행정보, 시행일, 공포일 = parse_period_to_execution_info(period)
        item['시행정보'] = 시행정보
        item['시행일'] = 시행일
        # 공포일도 정규화 (YYYY-MM-DD 형식으로)
        item['공포일'] = scraper.normalize_date_format(공포일)
    
    output_data = {
        'url': scraper.LIST_URL,
        'last_scraped_date': last_scraped_date,  # 스크래핑 실행 날짜
        'total_count': len(results),
        'results': results
    }
    
    # JSON 저장
    json_path = scraper.json_path
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장 완료: {json_path}")
    if last_scraped_date:
        print(f"마지막 스크래핑 날짜: {last_scraped_date}")
    
    # CSV 저장
    if results:
        import csv
        
        # 모든 필드명 수집
        fieldnames = set()
        for item in results:
            fieldnames.update(item.keys())
        fieldnames = sorted(list(fieldnames))
        
        csv_path = scraper.output_dir / "csv" / "moleg_scraper.csv"
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in results:
                csv_item = {}
                for key in fieldnames:
                    value = item.get(key, '')
                    # 리스트나 딕셔너리는 JSON 문자열로 변환
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False)
                    elif value is None:
                        value = ''
                    elif not isinstance(value, str):
                        value = str(value)
                    # 줄바꿈을 공백으로 변환
                    value = value.replace('\n', ' ').replace('\r', ' ')
                    csv_item[key] = value
                writer.writerow(csv_item)
        
        print(f"CSV 저장 완료: {csv_path}")
    
    print("\n=== 완료 ===")

# ===============================
# Health Check 전용 실행 경로
# ===============================
from typing import Dict
from datetime import datetime

from common.health_schema import base_health_output
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_mapper import apply_health_error
from common.common_http import check_url_status
from common.url_health_mapper import map_urlstatus_to_health_error
from common.constants import URLStatus

def moleg_health_check() -> Dict:
    """
    법제처 입법예고 Health Check
    """

    BASE_URL = "https://www.moleg.go.kr"
    LIST_URL = "https://www.moleg.go.kr/lawinfo/molegMakingList.mo?mid=a10514020000"

    # result = {
    #     "org_name": "MOLEG",
    #     "target": "법제처 > 입법예고",
    #     "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    #     "status": "FAIL",
    #     "checks": {
    #         "list_page": {},
    #         "detail_page": {}
    #     },
    #     "error": None
    # }

    result = base_health_output(
        auth_src="법제처 > 입법예고",
        scraper_id="MOLEG_LEGNOTICE",
        target_url=LIST_URL,
    )

    scraper = None

    try:
        # ===============================
        # Scraper 초기화
        # ===============================
        scraper = MolegScraper(delay=0.5)

        # ======================================================
        # HTTP 접근성 사전 체크
        # ======================================================
        http_result = check_url_status(
            LIST_URL,
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
                target=LIST_URL,
            )
        
        # ===============================
        # 1. 목록 페이지 접근
        # ===============================
        soup = scraper.fetch_page(LIST_URL, use_selenium=False)

        if soup is None:
            result["checks"]["list_page"] = {
                "url": LIST_URL,
                "success": False,
                "count": 0
            }
            return result

        # ===============================
        # 2. 목록 1건 추출
        # ===============================
        items = scraper.extract_list_items(soup)

        if not items:
            result["checks"]["list_page"] = {
                "url": LIST_URL,
                "success": False,
                "count": 0
            }
            return result

        first_item = items[0]
        title = first_item.get("title")
        detail_url = first_item.get("detail_url")

        result["checks"]["list_page"] = {
            "url": LIST_URL,
            "success": True,
            "count": 1,
            "title": title
        }

        # ===============================
        # 3. 상세 페이지 접근
        # ===============================
        if not detail_url:
            result["checks"]["detail_page"] = {
                "url": None,
                "success": False,
                "content_length": 0
            }
            return result

        detail = scraper.extract_detail_page(detail_url)

        content = detail.get("content", "")

        if not content:
            result["checks"]["detail_page"] = {
                "url": detail_url,
                "success": False,
                "content_length": 0
            }
            return result

        result["checks"]["detail_page"] = {
            "url": detail_url,
            "success": True,
            "content_length": len(content)
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


# ==================================================
# scheduler call
# ==================================================
def run():
    main()

if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="법제처-입법예고")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Health Check만 실행하고 종료",
    )

    args = parser.parse_args()

    if args.check:
        health = moleg_health_check()
        print(json.dumps(health, ensure_ascii=False, indent=2))
        sys.exit(0)

    main()

