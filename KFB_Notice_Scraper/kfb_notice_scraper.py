"""
은행연합회 자율규제 제정·개정 예고 스크래퍼
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
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common.base_scraper import BaseScraper


class KfbNoticeScraper(BaseScraper):
    """은행연합회 자율규제 제정·개정 예고 스크래퍼"""

    BASE_URL = "https://www.kfb.or.kr"
    LIST_URL = "https://www.kfb.or.kr/publicdata/reform_notice.php"

    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 리스트 페이지 파싱
    # ------------------------------------------------------------------
    def extract_table_data(self, soup: BeautifulSoup) -> List[Dict]:
        """
        공지 테이블에서 목록 데이터를 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        """
        results: List[Dict] = []

        if soup is None:
            return results

        table = soup.select_one("#Content table") or soup.select_one("table")
        if not table:
            print("⚠ 공지 테이블을 찾지 못했습니다.")
            return results

        rows = table.select("tbody > tr")
        if not rows:
            rows = [row for row in table.select("tr") if row.select("td")]

        for row in rows:
            cells = row.select("td")
            if len(cells) < 2:
                continue

            item: Dict[str, str] = {}

            # 번호
            number_text = cells[0].get_text(strip=True)
            if not number_text:
                continue
            item["no"] = number_text

            # 제목 및 상세 링크
            title_link = row.select_one("td.title > a") or row.select_one("td:nth-child(2) > a")
            if title_link:
                item["title"] = title_link.get_text(strip=True)
                href = title_link.get("href", "").strip()
                if href.startswith("javascript:"):
                    item["detail_link"] = href
                elif href.startswith("http"):
                    item["detail_link"] = href
                else:
                    item["detail_link"] = urljoin(self.BASE_URL, href)
            else:
                fallback_title = row.select_one("td.title") or row.select_one("td:nth-child(2)")
                item["title"] = fallback_title.get_text(strip=True) if fallback_title else ""
                item["detail_link"] = ""

            item["regulation_name"] = item.get("title", "")
            item["organization"] = "은행연합회"

            # 날짜 (마지막 셀에 있다고 가정)
            date_cell = cells[-1]
            item["posted_date"] = date_cell.get_text(strip=True)

            department_cell = row.select_one("td:nth-child(5)")
            department_text = department_cell.get_text(strip=True) if department_cell else ""
            item["department"] = department_text

            # 첨부 파일 링크 (있다면)
            attachment_cell = row.select_one("td:nth-child(6)") or row.select_one("td:last-child")

            download_link = ""
            if attachment_cell:
                download_anchor = attachment_cell.select_one("a[href]")
                if download_anchor:
                    href = download_anchor.get("href", "").strip()
                    if href.startswith("http"):
                        download_link = href
                    else:
                        download_link = urljoin(self.BASE_URL, href)
            item["download_link"] = download_link

            item.setdefault("enactment_date", "")
            item.setdefault("revision_date", "")

            results.append(item)

        return results

    # ------------------------------------------------------------------
    # 페이지네이션 파싱
    # ------------------------------------------------------------------
    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """
        페이지네이션 영역에서 총 페이지 수를 추출한다.
        항상 CSS Selector만 사용한다.
        """
        if soup is None:
            return 1

        max_page = 1
        pagination_selectors = [
            "div.pageArea",
            "div.paging",
            "div.pagination",
            "#pageArea",
            "#paging",
            ".pageArea",
            ".paging",
            ".pagination",
        ]

        pagination = None
        for selector in pagination_selectors:
            pagination = soup.select_one(selector)
            if pagination:
                break

        if pagination:
            page_links = pagination.select("a[href]")
            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    max_page = max(max_page, int(text))

                href = link.get("href", "").strip()
                if not href:
                    continue

                if "pageRun(" in href:
                    number = self._extract_number(href)
                    if number:
                        max_page = max(max_page, number)
                elif "page=" in href:
                    number = self._extract_number(href)
                    if number:
                        max_page = max(max_page, number)

        if max_page == 1:
            for link in soup.select("a[href]"):
                href = link.get("href", "").strip()
                if not href:
                    continue
                if "pageRun(" in href or "page=" in href:
                    number = self._extract_number(href)
                    if number:
                        max_page = max(max_page, number)

        return max_page if max_page > 0 else 1

    @staticmethod
    def _extract_number(href: str) -> Optional[int]:
        import re

        match = re.search(r"(?:readRun\(|pageRun\(|page=)(\d+)", href, re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # 상세 페이지 파싱
    # ------------------------------------------------------------------
    def extract_detail_info(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        상세 페이지에서 본문, 담당부서, 파일명을 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        """
        info = {
            "content": "",
            "department": "",
            "file_name": "",
        }

        if soup is None:
            return info

        content_selectors = [
            "#Content > div > div.contentArea > div.conInfoArea > div.panViewArea.mt30 > ul.viewInfo > li.txt",
            "#Content ul.viewInfo li.txt",
            ".conInfoArea ul.viewInfo li.txt",
            "ul.viewInfo li.txt",
            "#Content .viewInfo li.txt",
        ]
        for selector in content_selectors:
            candidate = soup.select_one(selector)
            if candidate:
                text = candidate.get_text(" ", strip=True)
                if text and "홈 >" not in text[:20]:
                    info["content"] = text
                    break

        for item in soup.select("ul.viewInfo li.item"):
            label = item.select_one("span.type01")
            value = item.select_one("span.type02")
            if not label or not value:
                continue
            label_text = label.get_text(strip=True)
            if "담당부서" in label_text or "소관부서" in label_text:
                info["department"] = value.get_text(strip=True)
                break

        file_anchor = soup.select_one("ul.viewInfo li.file a")
        if file_anchor:
            info["file_name"] = file_anchor.get_text(strip=True)

        return info

    # ------------------------------------------------------------------
    # 상세 페이지 요청
    # ------------------------------------------------------------------
    def fetch_detail_with_driver(
        self,
        driver: webdriver.Chrome,
        item: Dict,
        detail_link: str,
    ) -> Optional[BeautifulSoup]:
        """
        JavaScript 링크(readRun) 등을 처리하기 위해 Selenium을 사용한다.
        """
        try:
            link_lower = detail_link.lower()
            if link_lower.startswith("javascript"):
                number = self._extract_number(detail_link)
                if number:
                    driver.execute_script(f"readRun({number});")
                    time.sleep(2)
                    return BeautifulSoup(driver.page_source, "lxml")
                driver.execute_script(detail_link.replace("Javascript:", "").replace("javascript:", ""))
                time.sleep(2)
                return BeautifulSoup(driver.page_source, "lxml")
            else:
                driver.get(detail_link)
                time.sleep(2)
                return BeautifulSoup(driver.page_source, "lxml")
        except Exception as exc:
            print(f"  ✗ 상세 페이지 이동 실패: {detail_link} - {exc}")
            return None

    # ------------------------------------------------------------------
    # 스크래핑 메인
    # ------------------------------------------------------------------
    def crawl_notice(
        self,
        limit: int = 0,
        download_files: bool = False,
    ) -> List[Dict]:
        """
        자율규제 제정·개정 예고 목록을 스크래핑한다.
        """
        all_results: List[Dict] = []
        driver: Optional[webdriver.Chrome] = None

        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--lang=ko-KR")
            prefs = {
                "download.default_directory": os.path.abspath(self.download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            }
            chrome_options.add_experimental_option("prefs", prefs)
            driver = webdriver.Chrome(options=chrome_options)
            print("Selenium 드라이버 생성 완료")
        except Exception as exc:
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}, requests로 계속 진행합니다.")
            driver = None

        soup = (
            BeautifulSoup(driver.page_source, "lxml")
            if driver and self._open_with_driver(driver, self.LIST_URL)
            else self.fetch_page(self.LIST_URL)
        )

        if not soup:
            print("⚠ 첫 페이지를 가져오지 못했습니다.")
            if driver:
                driver.quit()
            return all_results

        total_pages = self.get_total_pages(soup)
        print(f"총 페이지 수: {total_pages}")

        seen_numbers = set()
        first_page_items = self.extract_table_data(soup)
        for item in first_page_items:
            number = item.get("no")
            if number and number not in seen_numbers:
                seen_numbers.add(number)
                all_results.append(item)

        print(
            f"페이지 1/{total_pages} 완료: {len(first_page_items)}개 추출 "
            f"(누적: {len(all_results)}개)"
        )

        if total_pages > 1 and driver:
            print(f"\n=== 페이지네이션 스크래핑 시작 (총 {total_pages}페이지) ===")
            for page_num in range(2, total_pages + 1):
                page_soup = self._navigate_to_page(driver, page_num)
                if not page_soup:
                    continue

                page_items = self.extract_table_data(page_soup)
                new_items = []
                for item in page_items:
                    number = item.get("no")
                    if number and number not in seen_numbers:
                        seen_numbers.add(number)
                        new_items.append(item)
                        all_results.append(item)

                print(
                    f"  페이지 {page_num}/{total_pages} 완료: "
                    f"{len(new_items)}개 추출 (누적: {len(all_results)}개)"
                )

                if limit and len(all_results) >= limit:
                    break
        elif total_pages > 1:
            print("⚠ Selenium이 없어 추가 페이지를 처리하지 못했습니다.")

        if limit:
            all_results = all_results[:limit]

        print("\n=== 상세 페이지 정보 수집 ===")
        for idx, item in enumerate(all_results, start=1):
            detail_link = item.get("detail_link", "")
            if not detail_link:
                print(f"[{idx}/{len(all_results)}] 상세 링크 없음 - {item.get('title','')}")
                item["content"] = ""
                item["department"] = ""
                item["file_name"] = ""
                item["organization"] = "은행연합회"
                item["regulation_name"] = item.get("title", "")
                continue

            print(f"[{idx}/{len(all_results)}] 상세 페이지 처리 중: {detail_link}")
            detail_soup = None

            if driver:
                detail_soup = self.fetch_detail_with_driver(driver, item, detail_link)
            if not detail_soup:
                if detail_link.lower().startswith("javascript"):
                    print(f"  ⚠ JavaScript 링크는 requests로 처리할 수 없어 건너뜁니다: {detail_link}")
                    item.setdefault("content", "")
                    item.setdefault("department", item.get("department", ""))
                    item.setdefault("file_name", "")
                    continue
                detail_soup = self.fetch_page(detail_link)

            # 디버깅: 첫 번째 상세 페이지만 HTML 저장 (공통 메서드 사용)
            self.save_debug_html(detail_soup)
            
            detail_info = self.extract_detail_info(detail_soup)
            item.update(detail_info)

            if item.get("download_link") and not item.get("file_download_link"):
                item["file_download_link"] = item["download_link"]
            if "download_link" in item and "file_download_link" not in item:
                item["file_download_link"] = item["download_link"]

            item["organization"] = "은행연합회"
            item["regulation_name"] = item.get("title", "")

            enactment, revision = self.extract_dates_from_text(item.get("content", ""))
            item["enactment_date"] = enactment
            item["revision_date"] = revision

        if driver:
            driver.quit()

        return all_results

    # ------------------------------------------------------------------
    # 내부 유틸리티
    # ------------------------------------------------------------------
    def _open_with_driver(self, driver: webdriver.Chrome, url: str) -> bool:
        try:
            driver.get(url)
            time.sleep(2)
            return True
        except Exception as exc:
            print(f"⚠ Selenium으로 페이지를 열지 못했습니다: {exc}")
            return False

    def _navigate_to_page(self, driver: webdriver.Chrome, page_num: int) -> Optional[BeautifulSoup]:
        """페이지 번호를 이용해 Selenium으로 페이지 이동"""
        strategies = [
            ("XPATH", lambda: driver.find_element(By.XPATH, f"//a[normalize-space(text())='{page_num}']")),
            ("SCRIPT", lambda: driver.execute_script(f"pageRun({page_num});")),
            ("DIRECT", lambda: driver.get(f"{self.LIST_URL}?page={page_num}")),
        ]

        for name, action in strategies:
            try:
                if name == "XPATH":
                    element = action()
                    driver.execute_script("arguments[0].click();", element)
                else:
                    action()
                time.sleep(2)
                return BeautifulSoup(driver.page_source, "lxml")
            except Exception as exc:
                print(f"  방법 {name} 실패 ({page_num}페이지): {exc}")
                continue
        return None

    def extract_dates_from_text(self, text: str) -> Tuple[str, str]:
        import re

        if not text:
            return "", ""

        enactment_date = ""
        revision_date = ""

        enactment_patterns = [
            r"제\s*정\s*(\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}[일.]?)",
            r"(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})\s*제\s*정",
            r"제\s*정\s*일\s*[:：]?\s*(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})",
        ]
        revision_patterns = [
            r"개\s*정\s*(\d{4}[.\-년]\s*\d{1,2}[.\-월]\s*\d{1,2}[일.]?)",
            r"(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})\s*개\s*정",
            r"최근\s*개\s*정\s*일\s*[:：]?\s*(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})",
            r"최종\s*개\s*정\s*일\s*[:：]?\s*(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})",
        ]

        def normalize(date_str: str) -> str:
            cleaned = re.sub(r"[년월일]", ".", date_str)
            cleaned = cleaned.replace(" ", "").replace("-", ".")
            cleaned = cleaned.strip(".")
            parts = [p for p in cleaned.split(".") if p]
            if len(parts) >= 3:
                return f"{parts[0]}.{int(parts[1])}.{int(parts[2])}."
            return cleaned

        for pattern in enactment_patterns:
            match = re.search(pattern, text)
            if match:
                enactment_date = normalize(match.group(1))
                break

        for pattern in revision_patterns:
            matches = list(re.finditer(pattern, text))
            if matches:
                revision_date = normalize(matches[-1].group(1))
                break

        return enactment_date, revision_date


def save_notice_results(records: List[Dict]):
    """JSON 및 CSV로 예고 데이터를 저장한다."""
    if not records:
        print("저장할 예고 데이터가 없습니다.")
        return

    import json
    import csv

    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    for item in records:
        law_item = {
            "규정명": item.get("regulation_name", item.get("title", "")),
            "기관명": item.get("organization", "은행연합회"),
            "본문": item.get("content", ""),
            "제정일": item.get("enactment_date", ""),
            "최근 개정일": item.get("revision_date", ""),
            "소관부서": item.get("department", ""),
            "첨부파일링크": item.get("file_download_link", item.get("download_link", "")),
            "첨부파일이름": item.get("file_name", ""),
        }
        law_results.append(law_item)
    
    # JSON 저장 (한글 필드명으로) - output/json 디렉토리에 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)

    json_path = os.path.join(json_dir, "kfb_notice_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": KfbNoticeScraper.LIST_URL,
                "total_count": len(law_results),
                "results": law_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"JSON 저장 완료: {json_path}")

    csv_headers = [
        "규정명",
        "기관명",
        "본문",
        "제정일",
        "최근 개정일",
        "소관부서",
        "첨부파일링크",
        "첨부파일이름",
    ]
    # CSV 저장 - output/csv 디렉토리에 저장
    csv_dir = os.path.join("output", "csv")
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "kfb_notice_scraper.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for law_item in law_results:
            # CSV 저장 시 본문의 줄바꿈 처리
            csv_item = law_item.copy()
            csv_item["본문"] = csv_item.get("본문", "").replace("\n", " ").replace("\r", " ")
            writer.writerow(csv_item)
    print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="은행연합회 자율규제 제정·개정 예고 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="파일 다운로드를 건너뜁니다.",
    )
    args = parser.parse_args()

    scraper = KfbNoticeScraper()
    results = scraper.crawl_notice(limit=args.limit, download_files=not args.no_download)

    print(f"\n총 {len(results)}개의 예고 데이터를 수집했습니다.")
    save_notice_results(results)

