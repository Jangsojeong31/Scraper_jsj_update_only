"""
한국은행 스크래퍼
CSV 목록 기반으로 법규 정보 스크래핑
"""
from __future__ import annotations

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

import os
import json
import csv
import time
import re
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor
from common.file_comparator import FileComparator


class BokScraper(BaseScraper):
    """한국은행 스크래퍼 - CSV 목록 기반으로 법규 정보 수집"""
    
    BASE_URL = "https://www.bok.or.kr"
    # 검색 URL 템플릿 (검색어를 파라미터로 받음)
    SEARCH_URL_TEMPLATE = "https://www.bok.or.kr/portal/search/search/main.do?menuNo=201693&query={query}"
    DEFAULT_CSV_PATH = "BOK_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: Optional[str] = None):
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
        # CSV에서 대상 규정 목록 로드
        self.csv_path = csv_path or self.DEFAULT_CSV_PATH
        self.target_laws = self._load_target_laws(self.csv_path)
        if self.target_laws:
            print(f"✓ CSV에서 {len(self.target_laws)}개의 대상 규정을 불러왔습니다: {self.csv_path}")
        else:
            print("⚠ 대상 CSV를 찾지 못했거나 비어 있습니다. 전체 목록을 대상으로 진행합니다.")
    
    def _load_target_laws(self, csv_path: str) -> List[Dict]:
        """CSV 파일에서 스크래핑 대상 규정명을 로드한다."""
        if not csv_path:
            return []
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            csv_file = find_project_root() / csv_path
        if not csv_file.exists():
            print(f"⚠ BOK 대상 CSV를 찾을 수 없습니다: {csv_file}")
            return []

        targets: List[Dict] = []
        try:
            with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("법령명") or "").strip()
                    category = (row.get("구분") or "").strip()
                    if not name:
                        continue
                    targets.append({"law_name": name, "category": category})
        except Exception as exc:
            print(f"⚠ BOK 대상 CSV 로드 실패: {exc}")
            return []
        return targets
    
    def _normalize_title(self, text: Optional[str]) -> str:
        """비교를 위한 규정명 정규화"""
        if not text:
            return ""
        cleaned = re.sub(r"[\s\W]+", "", text)
        return cleaned.lower()
    
    def _parse_date(self, date_text: str) -> Optional[tuple]:
        """날짜 텍스트를 파싱하여 (year, month, day) 튜플로 반환
        예: "2024.01.15" -> (2024, 1, 15)
        """
        if not date_text:
            return None
        
        # 공백 제거 및 정규화
        cleaned = date_text.strip().replace(" ", "").replace("-", ".")
        
        # 날짜 패턴 찾기 (YYYY.MM.DD 또는 YYYY-MM-DD)
        date_pattern = r'(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})'
        match = re.search(date_pattern, cleaned)
        
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                return (year, month, day)
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _remove_parentheses(self, text: str) -> str:
        """타이틀에서 괄호와 그 뒤의 텍스트를 제거
        예: "규정명 (부칙)" -> "규정명"
        예: "규정명 [개정]" -> "규정명"
        """
        if not text:
            return ""
        
        # 소괄호, 대괄호, 중괄호, 전각 괄호 제거
        # 괄호부터 끝까지 제거
        patterns = [
            r'[\(（].*?[\)）]',  # 소괄호 (일반, 전각)
            r'\[.*?\]',          # 대괄호
            r'\{.*?\}',          # 중괄호
        ]
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned)
        
        # 앞뒤 공백 제거
        return cleaned.strip()
    
    def is_target_regulation(self, title: str) -> bool:
        """제목이 대상 규정인지 확인 (CSV 목록 기반)"""
        if not title or not self.target_laws:
            return True  # CSV가 없으면 모든 항목 허용
        
        title_normalized = self._normalize_title(title)
        for target in self.target_laws:
            target_normalized = self._normalize_title(target["law_name"])
            # 정규화된 이름이 일치하거나 포함 관계인지 확인
            if target_normalized == title_normalized or target_normalized in title_normalized or title_normalized in target_normalized:
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
    
    def extract_regulation_list(self, soup: BeautifulSoup, search_keyword: str = "") -> List[Dict]:
        """검색 결과 목록에서 첫 번째 항목 추출"""
        results = []
        
        # 검색 결과 영역 찾기 (메뉴나 사이드바 제외)
        search_result_containers = [
            ".bdLine.type4",  # 한국은행 법규 검색 결과 영역
            ".bdLine",  # bdLine 클래스를 가진 영역
            "div.content .bdLine",  # content 안의 bdLine
            "#searchResult",  # 검색 결과 컨테이너
            ".search-result", 
            ".search-results",
            ".result-area",
            ".result-list",
            "main .list",
            "main ul",
            ".content ul",
            "#content ul",
        ]
        
        result_container = None
        for container_selector in search_result_containers:
            container = soup.select_one(container_selector)
            if container:
                result_container = container
                print(f"  ✓ 검색 결과 영역 발견: {container_selector}")
                break
        
        # 검색 결과 영역이 없으면 전체 페이지에서 찾기
        if not result_container:
            result_container = soup
        
        # 페이지 구조에 따라 다양한 선택자 시도
        # 검색 결과 페이지는 보통 리스트 형태로 표시됨
        selectors = [
            ".bdLine.type4 ul li",  # 한국은행 법규 검색 결과 리스트
            ".bdLine ul li",  # bdLine 클래스를 가진 ul의 li
            "div.bdLine li",  # bdLine div 안의 li
            "li a[href*='view.do']",  # view.do를 포함한 링크가 있는 li
            "li a[href*='/portal/singl/law/view.do']",  # 법규 상세 페이지 링크
            "li[class*='result']",  # result 클래스를 포함한 li
            "li[class*='item']",  # item 클래스를 포함한 li
            ".search-result-list li",  # 검색 결과 리스트
            ".result-list li",
            ".search-list li",
            "ul.search-result li",
            "ul.result li",
            "li a[href*='bbs']",  # bbs를 포함한 링크가 있는 li
            "table tbody tr",  # 테이블 행
            ".list-item",
            ".law-item",
            ".regulation-item",
            "div.list li",
        ]
        
        found_items = []
        for selector in selectors:
            items = result_container.select(selector)
            if items and len(items) > 0:
                # 빈 항목이나 헤더 제외하고 실제 데이터 항목만 필터링
                valid_items = []
                for item in items:
                    # 링크가 있거나 텍스트가 있는 항목만 포함
                    link = item.select_one("a")
                    text = item.get_text(strip=True)
                    
                    # 필터링 조건:
                    # 1. 링크가 있어야 함
                    # 2. 텍스트 길이가 충분해야 함
                    # 3. 검색어와 관련이 있어야 함 (검색어가 제공된 경우)
                    # 4. view.do나 bbs를 포함한 링크여야 함 (법규 상세 페이지로 가는 링크)
                    if link:
                        href = link.get("href", "")
                        # 법규 상세 페이지 링크인지 확인
                        # /portal/singl/law/view.do 또는 /portal/bbs/.../view.do 형식
                        is_regulation_link = (
                            ("view.do" in href and ("/portal/singl/law/" in href or "/portal/bbs/" in href)) or
                            ("bbs" in href and "view.do" in href) or
                            ("/portal/singl/law/view.do" in href)
                        )
                        
                        # 메뉴나 사이드바 링크 제외 (ecos, youtube, facebook 등)
                        is_excluded = any(excluded in href.lower() for excluded in [
                            "ecos.bok.or.kr",
                            "youtube.com",
                            "facebook.com",
                            "instagram.com",
                            "twitter.com",
                            "#",
                            "javascript:",
                            "list.do",  # 목록 페이지 제외
                        ])
                        
                        if (is_regulation_link and 
                            not is_excluded and 
                            len(text) > 10 and
                            (not search_keyword or search_keyword in text or search_keyword[:5] in text)):
                            valid_items.append(item)
                
                if valid_items:
                    found_items = valid_items
                    print(f"  ✓ 선택자 '{selector}'로 {len(valid_items)}개 유효한 항목 발견")
                    # 디버깅: 처음 몇 개 항목의 링크 출력
                    for i, item in enumerate(valid_items[:3], 1):
                        link_elem = item.select_one("a[href]")
                        if link_elem:
                            href = link_elem.get("href", "")
                            title = link_elem.get_text(strip=True) or item.get_text(strip=True)[:50]
                            print(f"    [{i}] {title[:30]}... -> {href[:80]}")
                    break
        
        if not found_items:
            # 디버깅을 위해 HTML 일부 저장
            self.save_debug_html(soup, filename="debug_bok_list.html")
            print("  ⚠ 목록 항목을 찾지 못했습니다. 디버그 HTML 저장: output/debug/debug_bok_list.html")
            print("  💡 디버그 HTML을 확인하여 실제 페이지 구조를 파악해주세요.")
            return results
        
        # 첫 번째 항목만 추출
        if found_items:
            item = found_items[0]
            try:
                # 제목 추출 (다양한 방법 시도)
                title = None
                title_elem = (
                    item.select_one("span.col a span.title") or  # 한국은행 법규 검색 결과 형식
                    item.select_one("span.col a") or  # 한국은행 법규 검색 결과 형식
                    item.select_one("a span.title") or
                    item.select_one("a") or
                    item.select_one(".title") or
                    item.select_one(".result-title") or
                    item.select_one("td:first-child") or
                    item.select_one(".name") or
                    item.select_one("strong") or
                    item  # 전체 항목에서 텍스트 추출
                )
                
                if title_elem:
                    # 링크가 있으면 링크 텍스트 우선, 없으면 전체 텍스트
                    if title_elem.name == "a":
                        title = title_elem.get_text(strip=True)
                    else:
                        # 링크 텍스트를 먼저 시도
                        link_in_elem = title_elem.select_one("a")
                        if link_in_elem:
                            title = link_in_elem.get_text(strip=True)
                        else:
                            title = title_elem.get_text(strip=True)
                
                # 제목이 없으면 스킵
                if not title or len(title) < 5:
                    print(f"  ⚠ 첫 번째 항목에서 제목을 추출하지 못했습니다.")
                    return results
                
                print(f"  ✓ 첫 번째 검색 결과 발견: {title}")
                
                # 상세 링크 추출
                detail_link = ""
                # 한국은행 법규 검색 결과 형식: span.col > a
                link_elem = (
                    item.select_one("span.col a[href]") or
                    item.select_one("a[href*='view.do']") or
                    item.select_one("a[href]")
                )
                if link_elem:
                    href = link_elem.get("href", "")
                    print(f"  → 원본 href: {href}")
                    if href:
                        # 상대 경로인 경우 절대 경로로 변환
                        if href.startswith("/"):
                            detail_link = self.BASE_URL + href
                        elif href.startswith("http"):
                            detail_link = href
                        else:
                            detail_link = urljoin(self.BASE_URL, href)
                        print(f"  → 최종 상세 링크: {detail_link}")
                        
                        # 올바른 링크 형식인지 확인
                        # /portal/singl/law/view.do 또는 /portal/bbs/.../view.do 형식
                        if ("view.do" in detail_link and 
                            ("/portal/singl/law/view.do" in detail_link or 
                             "/portal/bbs/" in detail_link or 
                             "nttId" in detail_link or
                             "lawseq" in detail_link)):
                            print(f"  ✓ 올바른 법규 상세 페이지 링크 형식 확인됨")
                        else:
                            print(f"  ⚠ 경고: 예상과 다른 링크 형식입니다.")
                
                # 추가 정보 추출 (개정일, 번호 등)
                regulation_info = {
                    "title": title,
                    "regulation_name": title,
                    "organization": "한국은행",
                    "detail_link": detail_link,
                    "content": "",
                    "department": "",
                    "file_names": [],
                    "download_links": [],
                    "enactment_date": "",
                    "revision_date": "",
                }
                
                # 개정일 추출 시도 (다양한 패턴)
                date_text = None
                date_elem = (
                    item.select_one("span.fs_date") or  # 한국은행 법규 검색 결과 형식
                    item.select_one("div.col.dataInfo1 span.fs_date") or  # 한국은행 법규 검색 결과 형식
                    item.select_one(".date") or
                    item.select_one(".revision-date") or
                    item.select_one(".result-date") or
                    item.select_one("td:nth-child(3)") or
                    item.select_one("td:nth-child(2)") or
                    item.select_one("span.date") or
                    item.select_one("em.date")
                )
                
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                else:
                    # 전체 텍스트에서 날짜 패턴 찾기 (YYYY-MM-DD 형식)
                    import re
                    full_text = item.get_text()
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', full_text)
                    if date_match:
                        date_text = date_match.group(1)
                
                if date_text:
                    regulation_info["revision_date"] = date_text
                    print(f"    개정일: {date_text}")
                
                results.append(regulation_info)
                
            except Exception as e:
                print(f"  ⚠ 항목 추출 중 오류: {e}")
                import traceback
                traceback.print_exc()
        
        return results
    
    def extract_regulation_detail(self, url: str, regulation_name: str = "") -> Dict:
        """상세 페이지에서 규정 내용 추출"""
        detail_info = {
            "content": "",  # PDF에서 추출한 본문 내용
            "file_names": [],
            "download_links": [],
            "revision_date": "",
            "enactment_date": "",  # 제정일
            "department": "",  # 소관부서
        }
        
        try:
            print(f"  → 상세 페이지 접근 중: {url}")
            # 올바른 URL 형식인지 확인
            # /portal/singl/law/view.do 또는 /portal/bbs/.../view.do 형식
            if ("view.do" in url and 
                ("/portal/singl/law/view.do" in url or 
                 "/portal/bbs/" in url or 
                 "nttId" in url or
                 "lawseq" in url)):
                print(f"  ✓ 올바른 법규 상세 페이지 URL 형식 확인됨")
            else:
                print(f"  ⚠ 경고: 예상과 다른 URL 형식입니다.")
                print(f"     URL: {url}")
            
            # Selenium driver 생성 (XPath로 소관부서 추출을 위해)
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException, NoSuchElementException
            
            chrome_options = self._build_default_chrome_options()
            driver = self._create_webdriver(chrome_options)
            
            try:
                driver.get(url)
                time.sleep(2)
                
                # XPath로 소관부서 추출
                try:
                    department_xpath = "/html/body/div/div[2]/main/div[1]/form/div/div[1]/dl[3]/dd"
                    wait = WebDriverWait(driver, 10)
                    department_elem = wait.until(EC.presence_of_element_located((By.XPATH, department_xpath)))
                    department_text = department_elem.text.strip()
                    if department_text:
                        # 첫 번째 '(' 앞의 텍스트만 추출 (예: "국제총괄팀(02-759-5748)" → "국제총괄팀")
                        if '(' in department_text:
                            department_text = department_text.split('(')[0].strip()
                        detail_info["department"] = department_text
                        print(f"  ✓ 소관부서 (XPath): {department_text}")
                except (TimeoutException, NoSuchElementException):
                    print(f"  ⚠ XPath로 소관부서를 찾지 못했습니다: {department_xpath}")
                except Exception as e:
                    print(f"  ⚠ 소관부서 추출 중 오류: {e}")
                
                # BeautifulSoup으로 변환
                soup = BeautifulSoup(driver.page_source, 'html.parser')
            finally:
                driver.quit()
            
            # 첨부파일 목록 찾기: ul > li > a 구조
            # 다양한 선택자 시도
            file_list_selectors = [
                "main form div dl dd ul li a",  # 일반적인 구조
                "form div dl dd ul li a",
                "dl dd ul li a",
                "ul li a[href*='download']",
                "ul li a[href*='file']",
            ]
            
            file_links = []
            for selector in file_list_selectors:
                links = soup.select(selector)
                if links:
                    file_links = links
                    print(f"  ✓ 첨부파일 목록 발견: {len(links)}개 (셀렉터: {selector})")
                    break
            
            if not file_links:
                # 디버깅을 위해 HTML 저장
                self.save_debug_html(soup, filename="debug_bok_detail.html")
                print(f"  ⚠ 첨부파일 목록을 찾지 못했습니다. 디버그 HTML 저장: output/debug/debug_bok_detail.html")
            
            # PDF 파일 우선, 없으면 HWP 파일 찾기
            selected_file_elem = None
            file_type = None
            
            for link in file_links:
                href = link.get("href", "")
                link_text = link.get_text(strip=True)
                
                # href나 텍스트에서 파일 확장자 확인
                if href:
                    href_lower = href.lower()
                    if '.pdf' in href_lower or link_text.lower().endswith('.pdf'):
                        selected_file_elem = link
                        file_type = 'pdf'
                        print(f"  ✓ PDF 파일 발견: {link_text}")
                        break
                    elif '.hwp' in href_lower or link_text.lower().endswith('.hwp'):
                        if not selected_file_elem:  # PDF가 없을 때만 HWP 선택
                            selected_file_elem = link
                            file_type = 'hwp'
                            print(f"  ✓ HWP 파일 발견: {link_text}")
            
            if selected_file_elem:
                href = selected_file_elem.get("href", "")
                if href:
                    # 상대 경로인 경우 절대 경로로 변환
                    if href.startswith("/"):
                        file_url = self.BASE_URL + href
                    elif href.startswith("http"):
                        file_url = href
                    else:
                        file_url = urljoin(self.BASE_URL, href)
                    
                    # 파일명 추출
                    file_name = None
                    from urllib.parse import urlparse, parse_qs, unquote
                    
                    # 링크 텍스트에서 파일명 추출 시도
                    link_text = selected_file_elem.get_text(strip=True)
                    if link_text and ('.pdf' in link_text.lower() or '.hwp' in link_text.lower()):
                        # 텍스트에서 파일명 추출
                        import re
                        match = re.search(r'([^/]+\.(pdf|hwp))', link_text, re.IGNORECASE)
                        if match:
                            file_name = match.group(1)
                    
                    # href의 fileNm 파라미터에서 추출 시도
                    if not file_name:
                        try:
                            parsed_url = urlparse(href)
                            query_params = parse_qs(parsed_url.query)
                            
                            if 'fileNm' in query_params:
                                file_name = query_params['fileNm'][0]
                                file_name = unquote(file_name)
                            elif 'fileNm=' in href:
                                file_nm_part = href.split('fileNm=')[1]
                                if '&' in file_nm_part:
                                    file_name = file_nm_part.split('&')[0]
                                elif '&amp;' in file_nm_part:
                                    file_name = file_nm_part.split('&amp;')[0]
                                else:
                                    file_name = file_nm_part
                                file_name = unquote(file_name)
                        except Exception as e:
                            print(f"  ⚠ 파일명 추출 중 오류: {e}")
                    
                    # 파일명을 찾지 못한 경우 fallback
                    if not file_name:
                        if file_type == 'pdf':
                            file_name = "파일.pdf"
                        elif file_type == 'hwp':
                            file_name = "파일.hwp"
                        else:
                            file_name = "파일"
                    
                    detail_info["download_links"].append(file_url)
                    detail_info["file_names"].append(file_name)
                    print(f"  ✓ 첨부파일 다운로드: {file_name}")
                    print(f"    링크: {file_url}")
                    
                    # 파일 다운로드 및 비교
                    downloaded_file_path = self._download_and_compare_file(file_url, file_name, regulation_name=regulation_name)
                    
                    # PDF 또는 HWP 파일이면 내용 추출
                    if downloaded_file_path and downloaded_file_path.get('file_path'):
                        file_path = downloaded_file_path['file_path']
                        if file_path.lower().endswith('.pdf'):
                            print(f"  PDF 내용 추출 중...")
                            pdf_content = self.file_extractor.extract_pdf_content(file_path)
                            if pdf_content:
                                detail_info["content"] = pdf_content
                                print(f"  ✓ PDF에서 {len(pdf_content)}자 추출 완료")
                                
                                # PDF에서 제정일과 최근개정일 추출
                                extracted_info = self._extract_info_from_pdf_content(pdf_content)
                                if extracted_info.get("enactment_date"):
                                    detail_info["enactment_date"] = extracted_info["enactment_date"]
                                    print(f"  ✓ 제정일: {extracted_info['enactment_date']}")
                                if extracted_info.get("revision_date"):
                                    detail_info["revision_date"] = extracted_info["revision_date"]
                                    print(f"  ✓ 최근개정일: {extracted_info['revision_date']}")
                            else:
                                print(f"  ⚠ PDF 내용 추출 실패")
                        elif file_path.lower().endswith('.hwp'):
                            print(f"  HWP 내용 추출 중...")
                            hwp_content = self.file_extractor.extract_hwp_content(file_path)
                            if hwp_content:
                                detail_info["content"] = hwp_content
                                print(f"  ✓ HWP에서 {len(hwp_content)}자 추출 완료")
                                
                                # HWP에서 제정일과 최근개정일 추출
                                extracted_info = self._extract_info_from_pdf_content(hwp_content)
                                if extracted_info.get("enactment_date"):
                                    detail_info["enactment_date"] = extracted_info["enactment_date"]
                                    print(f"  ✓ 제정일: {extracted_info['enactment_date']}")
                                if extracted_info.get("revision_date"):
                                    detail_info["revision_date"] = extracted_info["revision_date"]
                                    print(f"  ✓ 최근개정일: {extracted_info['revision_date']}")
                            else:
                                print(f"  ⚠ HWP 내용 추출 실패")
                    else:
                        print(f"  ⚠ 첨부파일을 찾지 못했습니다.")
            
        except Exception as e:
            print(f"  ⚠ 상세 페이지 추출 실패: {e}")
            import traceback
            traceback.print_exc()
        
        return detail_info
    
    def _extract_info_from_pdf_content(self, content: str) -> Dict[str, str]:
        """PDF 내용에서 소관부서, 제정일, 최근개정일 추출"""
        result = {
            "department": "",
            "enactment_date": "",
            "revision_date": "",
        }
        
        if not content:
            return result
        
        # 제정일 패턴 찾기 (YYYY년 MM월 DD일 또는 YYYY-MM-DD 형식)
        # 예: "2023년 1월 12일", "2023-01-12", "제정일: 2023.01.12"
        # 예: "<2008. 1.24일 제 정>", "<2008.1.24일 제 정>"
        # 예: "제정개정 | 1999. 4. 3.1999. 6. 7.2000. 8. 31." (표 형식, 첫 번째 날짜가 제정일)
        date_patterns = [
            r'<(\d{4})\.\s*(\d{1,2})\.(\d{1,2})일\s*제\s*정>',  # <2008. 1.24일 제 정> 형식
            r'<(\d{4})\.(\d{1,2})\.(\d{1,2})일\s*제\s*정>',  # <2008.1.24일 제 정> 형식 (공백 없음)
            r'제정일[:\s]*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
            r'제정일[:\s]*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',
            r'제정일[:\s]*(\d{4})-(\d{1,2})-(\d{1,2})',
            r'제정[:\s]*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
            r'제정[:\s]*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',
            r'제정[:\s]*(\d{4})-(\d{1,2})-(\d{1,2})',
        ]
        
        # 표 형식 처리: "제정개정 | 1999. 4. 3.1999. 6. 7.2000. 8. 31." 형식
        # "제정개정" 텍스트를 찾고 그 다음에 나오는 첫 번째 날짜를 제정일로 사용
        if not result.get("enactment_date"):
            enactment_table_match = re.search(r'제정개정[^\d]*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.', content)
            if enactment_table_match:
                year, month, day = enactment_table_match.groups()
                result["enactment_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # 일반 패턴으로 제정일 찾기
        if not result.get("enactment_date"):
            for pattern in date_patterns:
                match = re.search(pattern, content)
                if match:
                    year, month, day = match.groups()
                    # YYYY-MM-DD 형식으로 변환
                    result["enactment_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    break
        
        # 소관부서 패턴 찾기 (마지막 개정일 부분에서 추출)
        # 예: "개정 2025. 6. 24. 국장결재 국제총괄팀- 793"
        # 예: "개정2023.12.20.총재결재 외환정보팀-1028"
        # 패턴: 개정 + 날짜 + 결재 + 팀명 + "-" + 숫자
        department_patterns = [
            r'개정\s*\d{4}\.?\s*\d{1,2}\.?\s*\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)\s*-',  # 공백 포함
            r'개정\s*\d{4}\.?\s*\d{1,2}\.?\s*\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)-',  # 공백 없음
            r'개정\d{4}\.?\d{1,2}\.?\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)\s*-',  # 공백 없음 (날짜 부분)
            r'개정\d{4}\.?\d{1,2}\.?\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)-',  # 공백 없음 (전체)
        ]
        
        # 모든 개정일 패턴을 찾아서 마지막 것을 사용
        all_matches = []
        for pattern in department_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                team_name = match.group(1).strip()
                if team_name:
                    all_matches.append((match.start(), team_name))
        
        # 마지막 개정일에서 추출한 팀명 사용
        if all_matches:
            # 위치 기준으로 정렬하여 마지막 것 선택
            all_matches.sort(key=lambda x: x[0])
            result["department"] = all_matches[-1][1]
        
        # 최근개정일 패턴 찾기
        # 예: "<2025. 2.28일 제9차 개정>", "<2025.2.28일 제9차 개정>"
        # 예: "개정 2025. 6. 24.", "개정2025.6.24."
        # 예: "개정 2000. 7.26 총재결재...", "2002. 3.18 총재결재..." (개정 생략)
        # 예: "제정개정 | 1999. 4. 3.1999. 6. 7.2000. 8. 31.2002. 1. 5." (표 형식, 모든 날짜 추출)
        revision_date_patterns = [
            r'<(\d{4})\.\s*(\d{1,2})\.(\d{1,2})일\s*제\d*차\s*개정>',  # <2025. 2.28일 제9차 개정> 형식
            r'<(\d{4})\.(\d{1,2})\.(\d{1,2})일\s*제\d*차\s*개정>',  # <2025.2.28일 제9차 개정> 형식 (공백 없음)
            r'개정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.',  # 개정 2025. 6. 24. 형식
            r'개정\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\.',  # 개정 2025.6.24. 형식
            r'개정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s+',  # 개정 2000. 7.26 총재결재... 형식
            r'개정\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s+',  # 개정 2000.7.26 총재결재... 형식
            r'^(\d{4})\.\s*(\d{1,2})\.(\d{1,2})\s+[가-힣]',  # 2002. 3.18 총재결재... 형식 (개정 생략, 줄 시작)
            r'\n(\d{4})\.\s*(\d{1,2})\.(\d{1,2})\s+[가-힣]',  # 2002. 3.18 총재결재... 형식 (개정 생략, 줄바꿈 후)
            r'개정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',  # 개정 2025. 6. 24 형식
            r'개정\s*(\d{4})\.(\d{1,2})\.(\d{1,2})',  # 개정 2025.6.24 형식
        ]
        
        # 표 형식 처리: "제정개정 | 1999. 4. 3.1999. 6. 7.2000. 8. 31.2002. 1. 5.2002. 3. 14.2004. 2. 4.2005. 3. 29.2006. 10. 13."
        # "제정개정" 텍스트를 찾고 그 다음에 나오는 모든 날짜를 추출하여 가장 최신 것을 사용
        table_dates = []
        table_match = re.search(r'제정개정[^\d]*((?:\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)+)', content)
        if table_match:
            dates_str = table_match.group(1)
            # 모든 날짜 패턴 추출 (YYYY. M. D. 형식)
            date_matches = re.finditer(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.', dates_str)
            for match in date_matches:
                year, month, day = match.groups()
                try:
                    from datetime import datetime
                    date_obj = datetime(int(year), int(month), int(day))
                    table_dates.append((match.start(), date_obj, year, month, day))
                except:
                    pass
        
        # 모든 개정일을 찾아서 가장 최신 것 사용
        all_revision_dates = []
        
        # 표 형식에서 찾은 날짜들 추가 (첫 번째는 제정일이므로 제외)
        if table_dates and len(table_dates) > 1:
            # 첫 번째는 제정일이므로 제외하고 나머지를 개정일로 사용
            for date_info in table_dates[1:]:
                all_revision_dates.append(date_info)
        
        # 일반 패턴으로 개정일 찾기
        for pattern in revision_date_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                year, month, day = match.groups()
                # 날짜를 datetime으로 변환하여 비교
                try:
                    from datetime import datetime
                    date_obj = datetime(int(year), int(month), int(day))
                    all_revision_dates.append((match.start(), date_obj, year, month, day))
                except:
                    pass
        
        # 가장 최신 개정일 선택
        if all_revision_dates:
            # 날짜 기준으로 정렬하여 가장 최신 것 선택
            all_revision_dates.sort(key=lambda x: x[1], reverse=True)
            year, month, day = all_revision_dates[0][2], all_revision_dates[0][3], all_revision_dates[0][4]
            result["revision_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # 최종 Fallback: 문서 내 모든 날짜를 스캔해 제정/최근개정 보정
        # 이미 추출된 revision_date가 있어도 더 최신 날짜가 있으면 덮어쓴다.
        date_candidates = []
        for match in re.finditer(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?', content):
            try:
                from datetime import datetime
                y, m, d = match.groups()
                date_obj = datetime(int(y), int(m), int(d))
                date_candidates.append((date_obj, y, m, d))
            except Exception:
                continue
        for match in re.finditer(r'(\d{4})-(\d{1,2})-(\d{1,2})', content):
            try:
                from datetime import datetime
                y, m, d = match.groups()
                date_obj = datetime(int(y), int(m), int(d))
                date_candidates.append((date_obj, y, m, d))
            except Exception:
                continue

        if date_candidates:
            if not result.get("enactment_date"):
                oldest = min(date_candidates, key=lambda x: x[0])
                result["enactment_date"] = f"{oldest[1]}-{oldest[2].zfill(2)}-{oldest[3].zfill(2)}"

            latest = max(date_candidates, key=lambda x: x[0])
            latest_dt, ly, lm, ld = latest

            def _parse_existing(dt_str: str):
                try:
                    from datetime import datetime
                    parts = dt_str.split("-")
                    return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    return None

            existing_rev_dt = _parse_existing(result.get("revision_date", ""))
            # 더 최신 날짜가 있으면 최근개정일 덮어쓰기
            if (existing_rev_dt is None) or (latest_dt > existing_rev_dt):
                result["revision_date"] = f"{ly}-{lm.zfill(2)}-{ld.zfill(2)}"
        
        return result
    
    def _get_safe_filename(self, filename: str, regulation_name: str = "") -> str:
        """
        파일명을 안전한 형식으로 변환 (경로에 사용 가능한 문자만)
        
        Args:
            filename: 원본 파일명
            regulation_name: 규정명 (파일명 생성용)
            
        Returns:
            안전한 파일명
        """
        import re
        # 규정명이 있으면 규정명 기반으로 파일명 생성
        if regulation_name:
            # 규정명에서 안전한 문자만 추출
            safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
            safe_reg_name = safe_reg_name.replace(' ', '_')
            # 파일 확장자 추출
            ext = Path(filename).suffix if filename else '.pdf'
            return f"{safe_reg_name}{ext}"
        else:
            # 원본 파일명에서 안전한 문자만 추출
            safe_name = re.sub(r'[^\w\s.-]', '', filename)
            return safe_name.replace(' ', '_')
    
    def _download_and_compare_file(self, file_url: str, file_name: str, regulation_name: str = "") -> Optional[Dict]:
        """
        파일 다운로드 및 이전 파일과 비교
        
        Args:
            file_url: 다운로드 URL
            file_name: 파일명
            regulation_name: 규정명 (이전 파일 매칭용)
            
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            # 안전한 파일명 생성
            safe_filename = self._get_safe_filename(file_name, regulation_name)
            
            # 새 파일 다운로드 경로 (current 디렉토리)
            new_file_path = self.current_dir / safe_filename
            
            # 이전 파일 경로 (previous 디렉토리)
            previous_file_path = self.previous_dir / safe_filename
            
            # 파일 다운로드
            print(f"  파일 다운로드 중: {file_name}")
            # FileExtractor.download_file는 (filepath, actual_filename) 튜플 반환
            downloaded_result = self.file_extractor.download_file(
                file_url,
                safe_filename,
                use_selenium=False,  # requests로 다운로드
                driver=None
            )
            
            # 튜플 언패킹
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
                    new_file_path.unlink()  # 기존 파일 삭제
                shutil.move(downloaded_path, new_file_path)
                print(f"  ✓ 파일 저장: {new_file_path}")
            
            # 이전 파일과 비교
            comparison_result = None
            if previous_file_path.exists():
                print(f"  → 이전 파일과 비교 중... (이전 파일: {previous_file_path})")
                comparison_result = self.file_comparator.compare_and_report(
                    str(new_file_path),
                    str(previous_file_path),
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
    
    def crawl_regulations(self) -> List[Dict]:
        """
        법규정보 - 규정 스크래핑
        CSV 목록 기반으로 각 규정명을 검색어로 사용하여 수집
        """
        # 스크래퍼 시작 시 current를 previous로 백업 (이전 실행 결과를 이전 버전으로)
        self._backup_current_to_previous()
        # 이전 실행의 diff 파일 정리
        self._clear_diffs_directory()
        
        print(f"\n=== 한국은행 법규 스크래핑 시작 ===")
        if not self.target_laws:
            print("⚠ CSV 목록이 없습니다.")
            return []
        
        print(f"대상 규정: {len(self.target_laws)}개")
        for i, target in enumerate(self.target_laws, 1):
            print(f"  {i}. {target['law_name']}")
        print()
        
        results = []
        
        try:
            # 각 규정명을 검색어로 사용하여 검색 및 추출
            for idx, target in enumerate(self.target_laws, 1):
                regulation_name = target["law_name"]
                print(f"\n[{idx}/{len(self.target_laws)}] {regulation_name}")
                
                # 검색어를 URL 인코딩
                query_encoded = quote(regulation_name)
                search_url = self.SEARCH_URL_TEMPLATE.format(query=query_encoded)
                
                print(f"  검색 URL: {search_url}")
                
                # Selenium으로 검색 결과 페이지 접근
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.common.exceptions import TimeoutException, NoSuchElementException
                
                # Selenium driver 생성
                chrome_options = self._build_default_chrome_options()
                driver = self._create_webdriver(chrome_options)
                
                detail_link = None
                title = None
                
                try:
                    driver.get(search_url)
                    
                    # 페이지 로딩 대기
                    time.sleep(2)

                    # 디버깅 HTML 저장 (첫 번째 검색만)
                    if idx == 1:
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        self.save_debug_html(soup, filename="debug_bok_search.html")
                
                    # 검색 결과 목록에서 모든 항목 찾기 및 등록일 비교
                    try:
                        wait = WebDriverWait(driver, 10)
                        
                        # 검색 결과 목록 컨테이너 찾기 (여러 방법 시도)
                        list_items = []
                        list_selectors = [
                            ("CSS", "#frm > div.tsh-main > div.search-main > ul > li"),
                            ("CSS", "div.search-main ul li"),
                            ("CSS", ".search-main ul li"),
                            ("CSS", "ul.search-list li"),
                            ("CSS", ".bdLine.type4 ul li"),
                        ]
                        
                        for method, selector in list_selectors:
                            try:
                                if method == "CSS":
                                    list_items = driver.find_elements(By.CSS_SELECTOR, selector)
                                if list_items:
                                    print(f"  ✓ 검색 결과 목록 발견 ({method}): {len(list_items)}개 항목")
                                    break
                            except Exception:
                                continue
                        
                        if not list_items:
                            print(f"  ⚠ 검색 결과 목록을 찾지 못했습니다.")
                            detail_link = None
                            title = None
                        else:
                            # 각 항목에서 등록일 추출 및 비교
                            items_with_dates = []
                            
                            normalized_target = self._normalize_title(regulation_name)
                            
                            for item_idx, li_item in enumerate(list_items, 1):
                                try:
                                    # 링크 요소 찾기
                                    link_elem = None
                                    try:
                                        link_elem = li_item.find_element(By.TAG_NAME, "a")
                                    except Exception:
                                        # a 태그가 li 내부에 있을 수 있음
                                        try:
                                            link_elem = li_item.find_element(By.CSS_SELECTOR, "a")
                                        except Exception:
                                            pass
                                    
                                    if not link_elem:
                                        continue
                                    
                                    # 제목 추출 (우선 위치 정보 span.location 시도)
                                    item_title = ""
                                    title_selectors = [
                                        "span.location",
                                        "span.title",
                                        ".location",
                                    ]
                                    for t_sel in title_selectors:
                                        try:
                                            t_elem = link_elem.find_element(By.CSS_SELECTOR, t_sel)
                                            item_title = t_elem.text.strip()
                                            if item_title:
                                                break
                                        except Exception:
                                            continue
                                    if not item_title:
                                        item_title = link_elem.text.strip()
                                    
                                    # 괄호와 그 뒤의 텍스트 제거 (비교를 위해)
                                    item_title_cleaned = self._remove_parentheses(item_title)
                                    
                                    # 등록일 찾기 (여러 방법 시도)
                                    date_text = None
                                    date_selectors = [
                                        "span.schDesc span.date",
                                        "span.date",
                                        ".date",
                                        "span.schDesc > span.date",
                                    ]
                                    
                                    for date_selector in date_selectors:
                                        try:
                                            date_elem = li_item.find_element(By.CSS_SELECTOR, date_selector)
                                            date_text = date_elem.text.strip()
                                            if date_text:
                                                break
                                        except Exception:
                                            continue
                                    
                                    # 링크 URL 추출
                                    item_link = link_elem.get_attribute("href")
                                    if item_link:
                                        if item_link.startswith("/"):
                                            item_link = self.BASE_URL + item_link
                                        elif not item_link.startswith("http"):
                                            item_link = urljoin(self.BASE_URL, item_link)
                                    
                                    if date_text:
                                        parsed_date = self._parse_date(date_text)
                                        if parsed_date:
                                            items_with_dates.append({
                                                'index': item_idx,
                                                'title': item_title,
                                                'title_cleaned': item_title_cleaned,
                                                'link': item_link,
                                                'date': parsed_date,
                                                'date_text': date_text,
                                                'element': link_elem
                                            })
                                            print(f"  → 항목 {item_idx}: {item_title[:50]}... (등록일: {date_text})")
                                        else:
                                            print(f"  ⚠ 항목 {item_idx}: 날짜 파싱 실패 ({date_text})")
                                    else:
                                        # 등록일이 없는 경우도 링크만 저장
                                        if item_link:
                                            items_with_dates.append({
                                                'index': item_idx,
                                                'title': item_title,
                                                'title_cleaned': item_title_cleaned,
                                                'link': item_link,
                                                'date': None,
                                                'date_text': '',
                                                'element': link_elem
                                            })
                                            print(f"  → 항목 {item_idx}: {item_title[:50]}... (등록일 없음)")
                                
                                except Exception as e:
                                    print(f"  ⚠ 항목 {item_idx} 처리 중 오류: {e}")
                                    continue
                            
                            # 가장 최근 날짜이면서 제목이 검색어와 일치하는 항목 우선 선택
                            if items_with_dates:
                                def title_matches(item_title_cleaned: str) -> bool:
                                    norm = self._normalize_title(item_title_cleaned)
                                    return normalized_target and (norm == normalized_target or normalized_target in norm or norm in normalized_target)

                                matching_items = [item for item in items_with_dates if title_matches(item.get('title_cleaned', item.get('title', '')))]

                                if not matching_items:
                                    print(f"  ⚠ 검색어와 일치하는 제목이 없습니다. 규정명으로만 빈 결과를 추가합니다.")
                                    detail_link = None
                                    title = None
                                else:
                                    items_with_valid_dates = [item for item in matching_items if item['date'] is not None]
                                    
                                    if items_with_valid_dates:
                                        selected_item = max(items_with_valid_dates, key=lambda x: x['date'])
                                        print(f"  ✓ 가장 최근 등록일(제목 일치) 항목 선택: {selected_item['title'][:50]}... (등록일: {selected_item['date_text']})")
                                    else:
                                        selected_item = matching_items[0]
                                        print(f"  ⚠ 등록일 정보가 없어 첫 번째 일치 항목 선택: {selected_item['title'][:50]}...")
                                    
                                    title = selected_item['title']
                                    detail_link = selected_item['link']
                                    
                                    # 선택된 항목 클릭
                                    print(f"  → 선택된 검색 결과 클릭 중...")
                                    selected_item['element'].click()
                                    
                                    # 새 페이지 로딩 대기
                                    time.sleep(2)
                                    
                                    # 현재 URL 가져오기 (클릭 후 이동한 페이지)
                                    current_url = driver.current_url
                                    print(f"  → 이동한 페이지 URL: {current_url}")
                                    
                                    # 클릭 후 이동한 URL을 detail_link로 사용
                                    if current_url and current_url != search_url:
                                        detail_link = current_url
                            else:
                                print(f"  ⚠ 검색 결과 항목을 찾지 못했습니다.")
                                detail_link = None
                                title = None
                    
                    except TimeoutException:
                        print(f"  ⚠ 검색 결과 목록 로딩 시간 초과")
                        detail_link = None
                        title = None
                    except Exception as e:
                        print(f"  ⚠ 검색 결과 처리 중 오류: {e}")
                        import traceback
                        traceback.print_exc()
                        detail_link = None
                        title = None
                    
                    if not detail_link:
                        print(f"  ⚠ 검색 결과에서 규정을 찾지 못했습니다.")
                        # 빈 항목으로 추가
                        empty_item = {
                            "title": regulation_name,
                            "regulation_name": regulation_name,
                            "organization": "한국은행",
                            "target_name": regulation_name,
                            "target_category": target.get("category", ""),
                            "detail_link": "",
                            "content": "",
                            "department": "",
                            "file_names": [],
                            "download_links": [],
                            "enactment_date": "",
                            "revision_date": "",
                        }
                        results.append(empty_item)
                        continue
                    
                    # 상세 정보 추출
                    matched_regulation = {
                        "title": regulation_name,
                        "regulation_name": regulation_name,
                        "organization": "한국은행",
                        "target_name": regulation_name,
                        "target_category": target.get("category", ""),
                        "detail_link": detail_link,
                        "content": "",
                        "department": "",
                        "file_names": [],
                        "download_links": [],
                        "enactment_date": "",
                        "revision_date": "",
                    }
                    
                    if detail_link:
                        print(f"  상세 페이지 접근: {detail_link}")
                        detail_info = self.extract_regulation_detail(detail_link, regulation_name=regulation_name)
                        matched_regulation.update(detail_info)
                    else:
                        print(f"  ⚠ 상세 링크가 없습니다.")
                    
                    results.append(matched_regulation)
                    
                finally:
                    # Selenium driver 종료
                    try:
                        driver.quit()
                    except Exception as e:
                        print(f"  ⚠ Driver 종료 중 오류: {e}")
                
                time.sleep(self.delay)
            
        except Exception as e:
            print(f"✗ 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def _filter_regulations_by_targets(self, regulation_list: List[Dict]) -> List[Dict]:
        """CSV 목록에 포함된 규정만 순서대로 반환한다."""
        if not self.target_laws:
            return regulation_list

        normalized_tree: Dict[str, List[Dict]] = {}
        for reg in regulation_list:
            reg_name = reg.get("regulation_name") or reg.get("title", "")
            key = self._normalize_title(reg_name)
            if not key:
                continue
            normalized_tree.setdefault(key, []).append(reg)

        selected_regulations: List[Dict] = []
        missing_targets: List[str] = []

        for target in self.target_laws:
            target_name = target["law_name"]
            key = self._normalize_title(target_name)
            matches = normalized_tree.get(key)
            if matches and len(matches) > 0:
                # 같은 이름의 규정이 여러 개 있을 수 있으므로 첫 번째 사용
                reg = dict(matches[0])  # 딕셔너리 복사
                reg["target_name"] = target_name
                reg["target_category"] = target.get("category", "")
                if target.get("law_name"):
                    reg["regulation_name"] = target["law_name"]
                selected_regulations.append(reg)
            else:
                missing_targets.append(target_name)

        if missing_targets:
            print(f"  ⚠ CSV에 있으나 목록에서 찾지 못한 규정: {len(missing_targets)}개")
            for name in missing_targets[:5]:
                print(f"     - {name}")
            if len(missing_targets) > 5:
                print("     ...")
            print(f"     (찾지 못한 항목은 결과에 빈 내용으로 포함됩니다)")

        return selected_regulations


def save_bok_results(records: List[Dict], crawler: Optional[BokScraper] = None):
    """JSON 및 CSV로 한국은행 법규 데이터를 저장한다.
    
    Args:
        records: 스크래핑된 법규정보 리스트
        crawler: BokScraper 인스턴스 (CSV의 모든 항목을 포함하기 위해 사용)
    """
    # CSV의 모든 항목을 포함하도록 정렬 (CSV 순서 유지)
    if crawler and crawler.target_laws:
        # CSV 항목 순서대로 정렬하기 위한 딕셔너리 생성
        records_dict = {}
        for item in records:
            reg_name = item.get("target_name") or item.get("regulation_name") or item.get("title", "")
            if reg_name:
                records_dict[reg_name] = item
        
        # CSV 순서대로 정렬된 결과 생성
        ordered_records = []
        missing_count = 0
        for target in crawler.target_laws:
            target_name = target["law_name"]
            if target_name in records_dict:
                ordered_records.append(records_dict[target_name])
            else:
                # CSV에 있지만 결과에 없는 경우 빈 항목 추가
                missing_count += 1
                empty_item: Dict[str, str] = {
                    "title": target_name,
                    "regulation_name": target_name,
                    "organization": "한국은행",
                    "target_name": target_name,
                    "target_category": target.get("category", ""),
                    "content": "",  # 빈 본문
                    "department": "",
                    "file_names": [],
                    "download_links": [],
                    "enactment_date": "",
                    "revision_date": "",
                }
                ordered_records.append(empty_item)
                print(f"디버깅: 찾지 못한 항목 추가 - {target_name}")
        
        if missing_count > 0:
            print(f"디버깅: 총 {missing_count}개 항목을 빈 본문으로 추가했습니다.")
        
        records = ordered_records
    
    if not records:
        print("저장할 법규 데이터가 없습니다.")
        return
    
    # 출력 디렉토리 생성
    json_dir = os.path.join("output", "json")
    csv_dir = os.path.join("output", "csv")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)
    
    # 날짜 정규화를 위한 scraper 인스턴스
    scraper = crawler if crawler else BokScraper()
    
    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    for idx, item in enumerate(records, 1):
        # 여러 첨부파일을 세미콜론으로 구분
        file_names_str = "; ".join(item.get("file_names", [])) if item.get("file_names") else ""
        download_links_str = "; ".join(item.get("download_links", [])) if item.get("download_links") else ""
        
        # 본문 내용 처리 (개행 유지, 4000자 제한)
        content = item.get("content", "") or ""
        # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if len(content) > 4000:
            content = content[:4000]
        
        law_item = {
            "번호": str(idx),  # 순번으로 번호 생성
            "규정명": item.get("regulation_name", item.get("title", "")),
            "기관명": item.get("organization", "한국은행"),
            "본문": content,
            "제정일": scraper.normalize_date_format(item.get("enactment_date", "")),
            "최근 개정일": scraper.normalize_date_format(item.get("revision_date", "")),
            "소관부서": item.get("department", ""),
            "파일 다운로드 링크": download_links_str,
            "파일 이름": file_names_str,
        }
        law_results.append(law_item)
    
    # JSON 저장 (한글 필드명으로)
    json_path = os.path.join(json_dir, "bok_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": BokScraper.SEARCH_URL_TEMPLATE,
                "total_count": len(law_results),
                "results": law_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n✓ JSON 저장 완료: {json_path}")
    
    # CSV 저장 (정리된 law_results 사용)
    csv_headers = [
        "번호",
        "규정명",
        "기관명",
        "본문",
        "제정일",
        "최근 개정일",
        "소관부서",
        "파일 다운로드 링크",
        "파일 이름",
    ]
    csv_path = os.path.join(csv_dir, "bok_scraper.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for law_item in law_results:
            writer.writerow(law_item)
    print(f"✓ CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="한국은행 법규정보 스크래퍼 (CSV 목록 기반)")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="대상 규정 목록 CSV 경로 (기본: BOK_Scraper/input/list.csv)",
    )
    args = parser.parse_args()
    
    scraper = BokScraper(csv_path=args.csv)
    results = scraper.crawl_regulations()
    
    print(f"\n총 {len(results)}개의 법규정보를 수집했습니다.")
    save_bok_results(results, crawler=scraper)
