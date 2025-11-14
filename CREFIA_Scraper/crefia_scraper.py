"""
여신금융협회 스크래퍼
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
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import os
from common.base_scraper import BaseScraper


class CrefiaScraper(BaseScraper):
    """여신금융협회 스크래퍼"""
    
    BASE_URL = "https://www.crefia.or.kr"
    LIST_URL = "https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx"
    
    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
    
    def extract_list_items(self, soup: BeautifulSoup) -> List[Dict]:
        """
        자율규제 현황 페이지에서 카테고리별 목록 항목을 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        """
        results: List[Dict] = []
        
        if soup is None:
            return results
        
        # 디버그 HTML 저장
        self.save_debug_html(soup, filename="debug_crefia_list.html")
        
        # 카테고리 컨테이너 찾기: #contents > div.cont_box_wrap > div
        category_containers = soup.select("#contents > div.cont_box_wrap > div")
        print(f"카테고리 컨테이너 수: {len(category_containers)}개")
        
        item_count = 0
        category_idx = 0
        
        for container in category_containers:
            # div.left와 div.right 모두 확인 (일부 카테고리는 right에 있음)
            left_right_containers = container.select("div.left, div.right")
            
            for lr_container in left_right_containers:
                # 카테고리 타이틀 찾기: div > div.title.dia_bul > h4
                category_title_elem = lr_container.select_one("div > div.title.dia_bul > h4")
                if not category_title_elem:
                    # 다른 패턴 시도
                    category_title_elem = lr_container.select_one("div.title.dia_bul > h4, h4")
                
                if not category_title_elem:
                    continue
                
                category_idx += 1
                category_title = category_title_elem.get_text(strip=True)
                print(f"\n[{category_idx}] 카테고리: {category_title}")
                
                # 카테고리 목록 찾기: div > div.list_box
                list_box = lr_container.select_one("div > div.list_box")
                if not list_box:
                    # 다른 패턴 시도
                    list_box = lr_container.select_one("div.list_box")
                
                if not list_box:
                    print(f"  ⚠ 목록 박스를 찾지 못했습니다.")
                    continue
                
                # 목록 내부의 링크 찾기: ul > li > a
                links = list_box.select("ul > li > a")
                print(f"  링크 수: {len(links)}개")
                
                for link_idx, link in enumerate(links, 1):
                    # 제목은 <p> 태그 안에 있음
                    title_elem = link.select_one("p")
                    text = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
                    
                    if not text:
                        continue
                    
                    # onclick 속성에서 파일명 추출
                    onclick = link.get("onclick", "").strip()
                    file_name = ""
                    download_url = ""
                    
                    if onclick and "fn_downloadFile" in onclick:
                        # fn_downloadFile('파일명.hwp', 'selfRegulation') 형태에서 파일명 추출
                        import re
                        match = re.search(r"fn_downloadFile\s*\(\s*['\"]([^'\"]+)['\"]", onclick)
                        if match:
                            file_name = match.group(1)
                            # 다운로드 URL 구성 (일반적인 패턴)
                            # 실제 URL은 사이트 구조에 따라 다를 수 있으므로 확인 필요
                            download_url = f"{self.BASE_URL}/portal/infocenter/regulation/downloadFile.xx?fileName={file_name}&category=selfRegulation"
                            print(f"    [{link_idx}] 파일명 추출: {file_name[:60]}...")
                    
                    # href 속성도 확인 (onclick이 없는 경우)
                    href = link.get("href", "").strip()
                    if not download_url and href:
                        # 메뉴나 네비게이션 링크 제외
                        if any(skip in href.lower() for skip in ["#", "javascript:", "mailto:", "tel:"]):
                            continue
                        
                        # 상대 경로를 절대 경로로 변환
                        if href.startswith("/"):
                            download_url = urljoin(self.BASE_URL, href)
                        elif href.startswith("http"):
                            download_url = href
                        else:
                            download_url = urljoin(self.LIST_URL, href)
                    
                    item: Dict[str, str] = {
                        "no": str(item_count + 1),
                        "title": text,
                        "regulation_name": text,
                        "organization": "여신금융협회",
                        "category": category_title,
                        "detail_link": download_url,  # 다운로드 링크를 detail_link로도 저장
                        "file_download_link": download_url,
                        "file_name": file_name if file_name else text,  # 파일명이 있으면 사용, 없으면 제목 사용
                        "content": "",
                        "enactment_date": "",
                        "revision_date": "",
                        "department": "",
                    }
                    
                    results.append(item)
                    item_count += 1
                    
                    if link_idx <= 3:  # 처음 3개만 상세 출력
                        print(f"    [{link_idx}] {text[:50]}... -> {file_name[:60] if file_name else '파일명 없음'}")
        
        print(f"\n총 {len(results)}개 항목 추출 완료")
        return results
    
    def crawl_self_regulation_status(self, limit: int = 0) -> List[Dict]:
        """
        자율규제 현황 스크래핑
        URL: https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx
        
        Args:
            limit: 가져올 개수 제한 (0=전체)
        """
        driver: Optional[webdriver.Chrome] = None
        
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--lang=ko-KR")
            driver = webdriver.Chrome(options=chrome_options)
            print("Selenium 드라이버 생성 완료")
        except Exception as exc:
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}")
            driver = None
        
        if not driver:
            print("⚠ Selenium이 필요하지만 생성하지 못했습니다.")
            return []
        
        try:
            print(f"\n페이지 접속: {self.LIST_URL}")
            driver.get(self.LIST_URL)
            time.sleep(3)  # 페이지 로딩 대기
            
            soup = BeautifulSoup(driver.page_source, "lxml")
            
            # 목록 추출
            results = self.extract_list_items(soup)
            
            # limit 적용
            if limit > 0:
                results = results[:limit]
                print(f"limit 적용: {limit}개 항목만 처리 (전체: {len(results)}개)")
            
        finally:
            if driver:
                driver.quit()
        
        return results
    
    def crawl_self_regulation_notice(self) -> List[Dict]:
        """
        자율규제 제·개정 공고 스크래핑
        """
        # URL이 제공되지 않았으므로 실제 URL 확인 필요
        results = []
        # TODO: 실제 페이지 구조에 맞춰 데이터 추출 구현
        return results


def save_crefia_results(records: List[Dict]):
    """JSON 및 CSV로 여신금융협회 자율규제 현황 데이터를 저장한다."""
    if not records:
        print("저장할 데이터가 없습니다.")
        return
    
    import json
    import csv
    
    # JSON 저장 - output/json 디렉토리에 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)
    
    json_path = os.path.join(json_dir, "crefia_self_regulation.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장 완료: {json_path}")
    
    # CSV 저장 - output/csv 디렉토리에 저장
    csv_dir = os.path.join("output", "csv")
    os.makedirs(csv_dir, exist_ok=True)
    
    csv_path = os.path.join(csv_dir, "crefia_self_regulation.csv")
    
    # 헤더 정의 (kfb_crawler.py와 동일)
    headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 다운로드 링크", "파일 이름"]
    
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for item in records:
            row_data = {
                "번호": item.get("no", ""),
                "규정명": item.get("regulation_name", ""),
                "기관명": item.get("organization", "여신금융협회"),
                "본문": item.get("content", "").replace("\n", " ").replace("\r", " "),
                "제정일": item.get("enactment_date", ""),
                "최근 개정일": item.get("revision_date", ""),
                "소관부서": item.get("department", ""),
                "파일 다운로드 링크": item.get("file_download_link", ""),
                "파일 이름": item.get("file_name", ""),
            }
            writer.writerow(row_data)
    print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="여신금융협회 자율규제 현황 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    args = parser.parse_args()
    
    crawler = CrefiaScraper()
    results = crawler.crawl_self_regulation_status(limit=args.limit)
    print(f"\n추출된 데이터: {len(results)}개")
    save_crefia_results(results)

