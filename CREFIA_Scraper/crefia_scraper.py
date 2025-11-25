"""
여신금융협회 스크래퍼 (Option 1 적용, FileExtractor 통합)
"""
import sys
from pathlib import Path
import os
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin
import re
import json
import csv

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# 프로젝트 루트 찾기 (common 모듈 import 위해)
def find_project_root():
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

from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor  # FileExtractor import

# ---------------- Selenium 다운로드 유틸 ----------------
def init_selenium(download_dir: str) -> webdriver.Chrome:
    os.makedirs(download_dir, exist_ok=True)
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 필요 시 활성화
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=ko-KR")
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=chrome_options)
    return driver


# ---------------- 스크래퍼 클래스 ----------------
class CrefiaScraper(BaseScraper):
    """여신금융협회 스크래퍼"""
    
    BASE_URL = "https://www.crefia.or.kr"
    LIST_URL = "https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx"
    
    #--------------------------------------
    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        self.file_extractor = FileExtractor(download_dir=self.download_dir)
        print("다운로드 폴더 내용:", os.listdir(self.download_dir))
    
    # ---------------- 목록 추출 ----------------
    def extract_list_items(self, soup: BeautifulSoup, driver: webdriver.Chrome) -> List[Dict]:
        results: List[Dict] = []
        if soup is None:
            return results
        
        self.save_debug_html(soup, filename="debug_crefia_list.html")
        
        category_containers = soup.select("#contents > div.cont_box_wrap > div")
        print(f"카테고리 컨테이너 수: {len(category_containers)}개")
        
        item_count = 0
        category_idx = 0
        
        for container in category_containers:
            left_right_containers = container.select("div.left, div.right")
            
            for lr_container in left_right_containers:
                category_title_elem = lr_container.select_one("div > div.title.dia_bul > h4") \
                                    or lr_container.select_one("div.title.dia_bul > h4, h4")
                
                if not category_title_elem:
                    continue
                
                category_idx += 1
                category_title = category_title_elem.get_text(strip=True)
                print(f"\n[{category_idx}] 카테고리: {category_title}")

                if category_title in ["표준약관", "리스·할부·신기술", "공시", "신용카드", "모집인 관련", "광고심의 및 사후보고약관 심사"]:
                    print(f"  ⚠ '{category_title}' 카테고리는 스킵합니다.")
                    continue
                
                list_box = lr_container.select_one("div > div.list_box") or lr_container.select_one("div.list_box")
                if not list_box:
                    print(f"  ⚠ 목록 박스를 찾지 못했습니다.")
                    continue
                
                # ---- BeautifulSoup에서 링크 텍스트 추출 ----
                links = list_box.select("ul > li > a")
                link_texts = []
                for link in links:
                    title_elem = link.select_one("p")
                    text = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
                    if text:
                        link_texts.append(text)

                print(f"  링크 수: {len(link_texts)}개")
                
                # ---- Selenium으로 실제 클릭 ----
                for link_idx, text in enumerate(link_texts, 1):
                    try:
                        selenium_link = driver.find_element(By.LINK_TEXT, text)
                    except:
                        print(f"  ⚠ Selenium에서 '{text}' 링크를 찾지 못함")
                        continue

                    file_name = ""
                    download_url = ""
                    content = ""

                    # 다운로드 감지
                    before = set(os.listdir(self.download_dir))
                    print(f"📥 다운로드 시작: {text}")
                    driver.execute_script("arguments[0].click();", selenium_link)

                    downloaded_file = None
                    timeout = 40
                    start_time = time.time()

                    while time.time() - start_time < timeout:
                        after = set(os.listdir(self.download_dir))
                        new_files = after - before

                        if new_files:
                            downloaded_file = list(new_files)[0]
                            if not downloaded_file.endswith(".crdownload"):
                                break
                        time.sleep(1)

                    if downloaded_file is None:
                        print(f"❌ 다운로드 실패 또는 시간 초과: {text}")
                        continue

                    filepath = os.path.join(self.download_dir, downloaded_file)
                    print(f"✅ 다운로드 완료: {filepath}")

                    # FileExtractor로 내용 추출
                    try:
                        content = self.file_extractor.extract_hwp_content(filepath)
                        content = content[:50]
                    except Exception as e:
                        content = f"파일 읽기 실패: {str(e)}"

                    print(f"\n📄 {text} 파일 내용 일부:\n{content}\n")
                    
                    item: Dict[str, str] = {
                        "no": str(item_count + 1),
                        "title": text,
                        "regulation_name": text,
                        "organization": "여신금융협회",
                        "category": category_title,
                        "detail_link": download_url,
                        "file_download_link": download_url,
                        "file_name": file_name if file_name else text,
                        "content": content,
                        "enactment_date": "",
                        "revision_date": "",
                        "department": "",
                    }
                    
                    results.append(item)
                    item_count += 1
                    
                    if link_idx <= 3:
                        print(f"    [{link_idx}] {text[:50]}... -> {file_name[:60] if file_name else '파일명 없음'}")
        
        print(f"\n총 {len(results)}개 항목 추출 완료")
        return results
    
    # ---------------- 크롤링 ----------------
    def crawl_self_regulation_status(self, limit: int = 0) -> List[Dict]:
        driver: Optional[webdriver.Chrome] = None
        try:
            driver = init_selenium(self.download_dir)
            print("Selenium 드라이버 생성 완료")
        except Exception as exc:
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}")
            return []
        
        try:
            print(f"\n페이지 접속: {self.LIST_URL}")
            driver.get(self.LIST_URL)
            time.sleep(3)
            
            soup = BeautifulSoup(driver.page_source, "lxml")
            results = self.extract_list_items(soup, driver)
            
            if limit > 0:
                results = results[:limit]
                print(f"limit 적용: {limit}개 항목만 처리 (전체: {len(results)}개)")
            
        finally:
            if driver:
                driver.quit()
        
        return results
    
    def crawl_self_regulation_notice(self) -> List[Dict]:
        """자율규제 제·개정 공고 (미구현)"""
        return []

# ---------------- 저장 함수 ----------------
def save_crefia_results(records: List[Dict]):
    if not records:
        print("저장할 데이터가 없습니다.")
        return
    
    law_results = []
    for item in records:
        law_item = {
            "번호": item.get("no", ""),
            "규정명": item.get("regulation_name", ""),
            "기관명": item.get("organization", "여신금융협회"),
            "본문": item.get("content", ""),
            "제정일": item.get("enactment_date", ""),
            "최근 개정일": item.get("revision_date", ""),
            "소관부서": item.get("department", ""),
            "파일 다운로드 링크": item.get("file_download_link", ""),
            "파일 이름": item.get("file_name", ""),
        }
        law_results.append(law_item)
    
    # JSON 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)
    json_path = os.path.join(json_dir, "crefia_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": "https://www.crefia.or.kr/publicdata/reform_info.php",
            "total_count": len(law_results),
            "results": law_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장 완료: {json_path}")
    
    # CSV 저장
    csv_dir = os.path.join("output", "csv")
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "crefia_scraper.csv")
    headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 다운로드 링크", "파일 이름"]
    
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for law_item in law_results:
            csv_item = law_item.copy()
            csv_item["본문"] = csv_item.get("본문", "").replace("\n", " ").replace("\r", " ")
            writer.writerow(csv_item)
    print(f"CSV 저장 완료: {csv_path}")

# ---------------- 실행 ----------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="여신금융협회 자율규제 현황 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    args = parser.parse_args()
    
    crawler = CrefiaScraper()
    results = crawler.crawl_self_regulation_status(limit=args.limit)
    print(f"\n추출된 데이터: {len(results)}개")
    save_crefia_results(results)
