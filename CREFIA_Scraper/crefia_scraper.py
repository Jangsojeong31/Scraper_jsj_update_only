"""
여신금융협회 스크래퍼
"""
import sys
from pathlib import Path
import os
import time
from typing import List, Dict, Optional
import json
import csv
import re
import requests

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
from common.file_extractor import FileExtractor
from data_scraper import extract_data_from_text, extract_dates_from_filename

# ---------------- Selenium 다운로드 유틸 ----------------
def init_selenium(download_dir: str, headless: bool = False, scraper=None) -> webdriver.Chrome:
    """
    Selenium 드라이버 초기화
    
    Args:
        download_dir: 다운로드 디렉토리 경로
        headless: 헤드리스 모드 사용 여부 (다운로드 시 False 권장)
        scraper: BaseScraper 인스턴스 (폐쇄망 환경 대응을 위해 _create_webdriver 사용)
    """
    download_dir_abs = os.path.abspath(download_dir)
    os.makedirs(download_dir_abs, exist_ok=True)
    print(f"다운로드 디렉토리: {download_dir_abs}")
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
        print("⚠ 헤드리스 모드 활성화 (다운로드 문제 가능)")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=ko-KR")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    prefs = {
        "download.default_directory": download_dir_abs,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # 폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용 (SeleniumManager 우회)
    if scraper and hasattr(scraper, '_create_webdriver'):
        driver = scraper._create_webdriver(chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver


# ---------------- 스크래퍼 클래스 ----------------
class CrefiaScraper(BaseScraper):
    """여신금융협회 스크래퍼"""
    
    BASE_URL = "https://www.crefia.or.kr"
    LIST_URL = "https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx"
    
    def __init__(self, delay: float = 1.0, cleanup_downloads: bool = False, clean_downloads: bool = False):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
            cleanup_downloads: 다운로드된 파일을 내용 추출 후 삭제할지 여부
            clean_downloads: 크롤링 시작 전 downloads 폴더를 정리할지 여부
        """
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        # BaseScraper의 session을 FileExtractor에 전달
        self.file_extractor = FileExtractor(
            download_dir=self.download_dir,
            session=self.session
        )
        self.cleanup_downloads = cleanup_downloads
        self.clean_downloads = clean_downloads
        
        if self.clean_downloads:
            self._clean_downloads_folder()
        
        print("다운로드 폴더 내용:", os.listdir(self.download_dir))
    
    def _clean_downloads_folder(self):
        """downloads 폴더의 모든 파일 삭제"""
        try:
            files = os.listdir(self.download_dir)
            if files:
                print(f"🗑️ downloads 폴더 정리 중... ({len(files)}개 파일)")
                for file in files:
                    file_path = os.path.join(self.download_dir, file)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"  ⚠ 파일 삭제 실패: {file} - {e}")
                print("✅ downloads 폴더 정리 완료")
            else:
                print("📂 downloads 폴더가 비어있습니다.")
        except Exception as e:
            print(f"⚠ downloads 폴더 정리 중 오류: {e}")
    
    # ---------------- 목록 추출 ----------------
    def extract_list_items(
        self, soup: BeautifulSoup, driver: webdriver.Chrome, limit: int = 0
    ) -> List[Dict]:
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
                # div.right 또는 div.left 안에 여러 div.cont_box가 있을 수 있음
                # 각 cont_box를 개별적으로 처리
                cont_boxes = lr_container.select("div.cont_box")
                
                for cont_box in cont_boxes:
                    # 카테고리 제목 찾기 (여러 방법 시도)
                    category_title_elem = (
                        cont_box.select_one("div.title.dia_bul > h4") or
                        cont_box.select_one(".title.dia_bul > h4") or
                        cont_box.select_one("div.title > h4") or
                        cont_box.select_one("h4")
                    )
                    
                    if not category_title_elem:
                        continue
                    
                    category_idx += 1
                    category_title = category_title_elem.get_text(strip=True)
                    print(f"\n[{category_idx}] 카테고리: {category_title}")

                    skip_categories = [
                        "표준약관", 
                    ]
                    if category_title in skip_categories:
                        print(f"  ⚠ '{category_title}' 카테고리는 스킵합니다.")
                        continue
                    
                    # list_box 찾기 (여러 방법 시도)
                    list_box = (
                        cont_box.select_one("div.list_box") or
                        cont_box.select_one(".list_box")
                    )
                    if not list_box:
                        print("  ⚠ 목록 박스를 찾지 못했습니다.")
                        continue
                    
                    # ---- BeautifulSoup에서 링크 텍스트 및 onclick 정보 추출 ----
                    links = list_box.select("ul > li > a")
                    link_data = []  # (text, filename, file_type) 튜플 리스트
                    for link in links:
                        title_elem = link.select_one("p")
                        text = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
                        if text:
                            # onclick 속성에서 파일명과 타입 추출
                            onclick = link.get("onclick", "")
                            filename = ""
                            file_type = "selfRegulation"  # 기본값
                            if onclick:
                                # fn_downloadFile('파일명.hwp', 'selfRegulation') 형식 파싱
                                match = re.search(
                                    r"fn_downloadFile\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                                    onclick
                                )
                                if match:
                                    filename = match.group(1)
                                    file_type = match.group(2)
                                    print(f"  📎 onclick에서 추출: 파일명={filename}, 타입={file_type}")
                            link_data.append((text, filename, file_type))

                    print(f"  링크 수: {len(link_data)}개")
                    
                    # ---- Selenium으로 실제 클릭 ----
                    for link_idx, (text, filename, file_type) in enumerate(link_data, 1):
                        # limit 체크 (0이면 전체 처리)
                        if limit > 0 and item_count >= limit:
                            print(f"  ⚠ limit({limit}개) 도달, 처리 중단")
                            break
                        # 링크 찾기 (여러 방법 시도)
                        selenium_link = None
                        try:
                            # 방법 1: LINK_TEXT로 찾기
                            selenium_link = driver.find_element(By.LINK_TEXT, text)
                            print(f"  ✓ LINK_TEXT로 링크 찾음: {text}")
                        except Exception:
                            try:
                                # 방법 2: 부분 텍스트로 찾기
                                selenium_link = driver.find_element(
                                    By.PARTIAL_LINK_TEXT, text
                                )
                                print(f"  ✓ PARTIAL_LINK_TEXT로 링크 찾음: {text}")
                            except Exception:
                                try:
                                    # 방법 3: XPath로 찾기
                                    xpath = f"//a[contains(text(), '{text}')]"
                                    selenium_link = driver.find_element(By.XPATH, xpath)
                                    print(f"  ✓ XPath로 링크 찾음: {text}")
                                except Exception as e:
                                    print(f"  ⚠ 모든 방법으로 '{text}' 링크를 찾지 못함: {e}")
                                    continue

                        # onclick에서 파일명 재확인 (Selenium에서)
                        if not filename:
                            try:
                                selenium_onclick = selenium_link.get_attribute("onclick")
                                if selenium_onclick:
                                    match = re.search(
                                        r"fn_downloadFile\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                                        selenium_onclick
                                    )
                                    if match:
                                        filename = match.group(1)
                                        file_type = match.group(2)
                                        print(f"  📎 Selenium에서 재추출: 파일명={filename}, 타입={file_type}")
                            except Exception as e:
                                print(f"  ⚠ onclick 재확인 실패: {e}")

                        # 다운로드 URL 구성
                        # 패턴: /common/downloadFile.do?fileName=<파일명(UTF-8 인코딩)>&fileType=selfRegulation&keyNum=&date=&pFileEnc=
                        download_url = ""
                        file_name = filename  # 저장할 파일명
                        if filename:
                            try:
                                from urllib.parse import quote
                                # 파일명을 UTF-8로 인코딩
                                encoded_filename = quote(
                                    filename, encoding='utf-8'
                                )
                                download_url = (
                                    f"{self.BASE_URL}/common/downloadFile.do"
                                    f"?fileName={encoded_filename}"
                                    f"&fileType={file_type}"
                                    f"&keyNum="
                                    f"&date="
                                    f"&pFileEnc="
                                )
                                print(f"  📎 다운로드 URL 구성: {download_url}")
                            except Exception as e:
                                print(f"  ⚠ URL 구성 실패: {e}")
                        else:
                            print("  ⚠ 파일명을 찾을 수 없어 URL 구성 불가")

                        content = ""
                        downloaded_file = None
                        filepath = None

                        # 방법 1: URL로 직접 다운로드 시도
                        if download_url and filename:
                            filepath = os.path.join(self.download_dir, filename)
                            
                            # 이미 같은 파일이 존재하는지 확인
                            if os.path.exists(filepath):
                                print(f"  ⏭️ 파일이 이미 존재합니다: {filename} (건너뜀)")
                                downloaded_file = filename
                                if not file_name:
                                    file_name = filename
                            else:
                                print(f"📥 방법 1: URL로 다운로드 시도: {text}")
                                print(f"  📎 다운로드 URL: {download_url}")
                                
                                try:
                                    # 간단한 GET 요청으로 다운로드
                                    response = requests.get(download_url, timeout=15)
                                    
                                    if response.status_code == 200:
                                        with open(filepath, "wb") as f:
                                            f.write(response.content)
                                        print(f"  ✅ 파일 저장 완료: {filepath}")
                                        downloaded_file = filename
                                        if not file_name:
                                            file_name = filename
                                    else:
                                        print(f"  ⚠ 다운로드 실패: {response.status_code}, {response.text[:200]}")
                                except Exception as e:
                                    print(f"  ⚠ URL 다운로드 중 오류: {e}")

                        # 방법 2: driver 클릭으로 다운로드 (방법 1 실패 시)
                        if not downloaded_file:
                            print(f"📥 방법 2: driver 클릭으로 다운로드: {text}")
                            
                            # 다운로드 감지
                            download_dir_abs = os.path.abspath(self.download_dir)
                            print(f"  📂 다운로드 디렉토리: {download_dir_abs}")
                            before = set(os.listdir(self.download_dir))
                            print(f"  📋 다운로드 전 파일 수: {len(before)}개")
                            
                            # 클릭 전 현재 URL 저장
                            current_url = driver.current_url
                            
                            try:
                                # 클릭 실행
                                driver.execute_script("arguments[0].click();", selenium_link)
                                time.sleep(2)  # 클릭 후 초기 대기
                                
                                # 페이지 이동 확인
                                new_url = driver.current_url
                                if new_url != current_url:
                                    print(f"  ⚠ 페이지 이동 발생: {current_url} -> {new_url}")
                                    # 원래 페이지로 돌아가기
                                    driver.back()
                                    time.sleep(2)
                            except Exception as e:
                                print(f"  ⚠ 클릭 실패: {e}")

                            timeout = 40
                            start_time = time.time()
                            crdownload_count = 0

                            while time.time() - start_time < timeout:
                                after = set(os.listdir(self.download_dir))
                                new_files = after - before

                            if new_files:
                                for new_file in new_files:
                                    print(f"  🔍 새 파일 발견: {new_file}")
                                    if new_file.endswith(".crdownload"):
                                        crdownload_count += 1
                                        print(f"  ⏳ 다운로드 진행 중... ({crdownload_count}초)")
                                    else:
                                        # 이미 같은 파일명이 존재하는지 확인
                                        new_file_path = os.path.join(self.download_dir, new_file)
                                        if filename and os.path.exists(os.path.join(self.download_dir, filename)):
                                            # 기대한 파일명과 다를 수 있으므로, 새로 다운로드된 파일은 유지
                                            downloaded_file = new_file
                                            print(f"  ✅ 다운로드 완료 파일: {downloaded_file}")
                                        else:
                                            downloaded_file = new_file
                                            print(f"  ✅ 다운로드 완료 파일: {downloaded_file}")
                                        break
                                    
                                    if downloaded_file:
                                        break
                                else:
                                    elapsed = int(time.time() - start_time)
                                    if elapsed % 5 == 0:  # 5초마다 로그
                                        print(f"  ⏳ 다운로드 대기 중... ({elapsed}초)")
                                
                                time.sleep(1)

                            if downloaded_file is None:
                                print(f"❌ driver 클릭 다운로드도 실패: {text}")
                                print(f"  📋 다운로드 후 파일 수: {len(after) if 'after' in locals() else len(before)}개")
                                # .crdownload 파일이 남아있는지 확인
                                crdownload_files = [
                                    f for f in os.listdir(self.download_dir)
                                    if f.endswith(".crdownload")
                                ]
                                if crdownload_files:
                                    print(f"  ⚠ 미완료 다운로드 파일 발견: {crdownload_files}")
                                continue

                            filepath = os.path.join(self.download_dir, downloaded_file)
                            # onclick에서 추출한 파일명이 없으면 다운로드된 파일명 사용
                            if not file_name:
                                file_name = downloaded_file
                            print(f"  ✅ driver 클릭 다운로드 완료: {filepath}")
                            print(f"  📝 저장할 파일명: {file_name}")

                        # FileExtractor로 내용 추출
                        content = ""
                        enactment_date = ""
                        revision_date = ""
                        department = ""
                        
                        # 1단계: 파일명에서 날짜 추출 시도
                        filename_enactment = ""
                        filename_revision = ""
                        if file_name:
                            filename_enactment, filename_revision = extract_dates_from_filename(file_name)
                            if filename_enactment:
                                print(f"  📅 제정일 추출 (파일명): {filename_enactment}")
                            if filename_revision:
                                print(f"  📅 최근 개정일 추출 (파일명): {filename_revision}")
                        
                        try:
                            full_content = self.file_extractor.extract_hwp_content(filepath)
                            original_length = len(full_content)
                            
                            # 2단계: 파일 내용에서 데이터 추출
                            extract_text = full_content[:1000] if full_content else ""
                            
                            if extract_text:
                                content_enactment, content_revision, content_department = extract_data_from_text(extract_text)
                                
                                # 파일명 데이터를 우선 사용 (파일명과 다를 경우 파일명 우선)
                                if filename_enactment:
                                    if content_enactment and filename_enactment != content_enactment:
                                        print(f"  ⚠ 제정일 불일치 - 파일명: {filename_enactment}, 파일내용: {content_enactment} (파일명 사용)")
                                    enactment_date = filename_enactment
                                    print(f"  📅 제정일 추출 (파일명): {enactment_date}")
                                elif content_enactment:
                                    enactment_date = content_enactment
                                    print(f"  📅 제정일 추출 (파일내용, 파일명 없음): {enactment_date}")
                                
                                if filename_revision:
                                    if content_revision and filename_revision != content_revision:
                                        print(f"  ⚠ 개정일 불일치 - 파일명: {filename_revision}, 파일내용: {content_revision} (파일명 사용)")
                                    revision_date = filename_revision
                                    print(f"  📅 최근 개정일 추출 (파일명): {revision_date}")
                                elif content_revision:
                                    revision_date = content_revision
                                    print(f"  📅 최근 개정일 추출 (파일내용, 파일명 없음): {revision_date}")
                                
                                if content_department:
                                    department = content_department
                                    print(f"  🏢 소관부서 추출: {department}")
                                
                                if not enactment_date and not revision_date and not department:
                                    print("  ⚠ 파일명과 파일내용(500자) 모두에서 제정일/개정일/소관부서를 찾지 못했습니다.")
                            else:
                                # 파일 내용을 읽을 수 없는 경우 파일명에서 추출한 값 사용
                                if filename_enactment:
                                    enactment_date = filename_enactment
                                if filename_revision:
                                    revision_date = filename_revision
                            
                            # content를 1000자로 제한
                            content = full_content[:1000]
                            print(f"\n📄 {text} 파일 내용 추출 완료 "
                                  f"(원본: {original_length}자, 저장: {len(content)}자)")
                        except Exception as e:
                            content = f"파일 읽기 실패: {str(e)}"
                            print(f"  ⚠ 파일 읽기 실패: {e}")
                            # 파일 읽기 실패 시 파일명에서 추출한 값 사용
                            if filename_enactment:
                                enactment_date = filename_enactment
                            if filename_revision:
                                revision_date = filename_revision

                        # 다운로드된 파일 정리 (옵션)
                        if self.cleanup_downloads:
                            try:
                                os.remove(filepath)
                                print(f"  🗑️ 다운로드 파일 삭제: {file_name}")
                            except Exception as e:
                                print(f"  ⚠ 파일 삭제 실패: {e}")

                        item: Dict[str, str] = {
                            "no": str(item_count + 1),
                            "title": text,
                            "regulation_name": text,
                            "organization": "여신금융협회",
                            "category": category_title,
                            "detail_link": download_url,
                            "file_download_link": download_url,
                            "file_name": file_name,
                            "content": content,
                            "enactment_date": enactment_date,
                            "revision_date": revision_date,
                            "department": department,
                        }
                        
                        results.append(item)
                        item_count += 1
                        
                        print(f"    [{link_idx}] {text[:50]}... -> {file_name[:60]}")
                        
                        # delay 적용 (서버 부하 방지)
                        if link_idx < len(link_data):
                            time.sleep(self.delay)
        
        print(f"\n총 {len(results)}개 항목 추출 완료")
        return results
    
    # ---------------- 크롤링 ----------------
    def crawl_self_regulation_status(self, limit: int = 0, headless: bool = False) -> List[Dict]:
        """
        자율규제 현황 크롤링
        
        Args:
            limit: 가져올 개수 제한 (0=전체)
            headless: 헤드리스 모드 사용 여부 (다운로드 시 False 권장)
        """
        driver: Optional[webdriver.Chrome] = None
        try:
            driver = init_selenium(self.download_dir, headless=headless, scraper=self)
            print("Selenium 드라이버 생성 완료")
        except Exception as exc:
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}")
            return []
        
        try:
            print(f"\n페이지 접속: {self.LIST_URL}")
            driver.get(self.LIST_URL)
            time.sleep(3)
            
            soup = BeautifulSoup(driver.page_source, "lxml")
            results = self.extract_list_items(soup, driver, limit=limit)
            
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
    
    # 날짜 정규화를 위한 임시 BaseScraper 인스턴스 생성
    temp_scraper = CrefiaScraper()
    
    law_results = []
    for item in records:
        law_item = {
            "번호": item.get("no", ""),
            "규정명": item.get("regulation_name", ""),
            "기관명": item.get("organization", "여신금융협회"),
            "본문": item.get("content", ""),
            "제정일": temp_scraper.normalize_date_format(item.get("enactment_date", "")),
            "최근 개정일": temp_scraper.normalize_date_format(item.get("revision_date", "")),
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
            "url": CrefiaScraper.LIST_URL,
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
    parser = argparse.ArgumentParser(
        description="여신금융협회 자율규제 현황 스크래퍼"
    )

    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")

    parser.add_argument(
        "--cleanup", action="store_true",
        help="다운로드된 파일을 내용 추출 후 삭제"
    )
    
    parser.add_argument(
        "--clean-downloads", action="store_true",
        help="크롤링 시작 전 downloads 폴더의 모든 파일 삭제"
    )
    
    args = parser.parse_args()
    
    crawler = CrefiaScraper(cleanup_downloads=args.cleanup, clean_downloads=args.clean_downloads)
    results = crawler.crawl_self_regulation_status(limit=args.limit)
    print(f"\n추출된 데이터: {len(results)}개")
    save_crefia_results(results)
