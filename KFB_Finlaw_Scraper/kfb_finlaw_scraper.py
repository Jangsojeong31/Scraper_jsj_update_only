"""
은행연합회 금융관련법규 스크래퍼
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


class KfbFinlawScraper(BaseScraper):
    """은행연합회 금융관련법규 스크래퍼"""

    BASE_URL = "https://www.kfb.or.kr"
    LIST_URL = "https://www.kfb.or.kr/publicdata/data_finlaw.php"

    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 리스트 페이지 파싱
    # ------------------------------------------------------------------
    def extract_table_data(self, soup: BeautifulSoup) -> List[Dict]:
        """
        금융관련법규 테이블에서 목록 데이터를 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        """
        results: List[Dict] = []

        if soup is None:
            return results

        table = soup.select_one("#Content table") or soup.select_one("table")
        if not table:
            print("⚠ 금융관련법규 테이블을 찾지 못했습니다.")
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

            # 첨부 파일 링크 (있다면)
            attachment_cell = row.select_one("td:nth-child(3)") or row.select_one("td:last-child")

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
    def extract_detail_info(self, soup: BeautifulSoup, content_max_length: int = 0) -> Dict[str, str]:
        """
        상세 페이지에서 본문, 담당부서, 파일명을 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        
        Args:
            soup: BeautifulSoup 객체
            content_max_length: 본문 최대 글자수 (0이면 전체, 지정하면 앞에서 N자까지만 가져오기)
        """
        info = {
            "content": "",
            "department": "",
            "file_name": "",
        }

        if soup is None:
            return info

        # 본문 추출 (KFB 사이트 + law.go.kr 사이트 모두 지원)
        # law.go.kr 사이트는 #lawService iframe 내부에 있음
        content_selectors = [
            # law.go.kr 사이트 iframe 내부 선택자 (우선순위 높음)
            "#contentBody",
            "#center",
            "#lawContent",
            ".lawContent",
            "#pDetail",
            ".pDetail",
            "#conts",
            ".conts",
            "#content",
            ".content",
            "div#contentBody",
            "div#center",
            "div#lawContent",
            "div.lawContent",
            "div#pDetail",
            "div.pDetail",
            # KFB 사이트 선택자
            "#Content > div > div.contentArea > div.conInfoArea > div.panViewArea.mt30 > ul.viewInfo > li.txt",
            "#Content ul.viewInfo li.txt",
            ".conInfoArea ul.viewInfo li.txt",
            "ul.viewInfo li.txt",
            "#Content .viewInfo li.txt",
        ]
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if text and len(text) > 20 and "홈 >" not in text[:20]:
                    # content_max_length가 지정되어 있으면 앞에서 N자까지만 가져오기
                    if content_max_length > 0 and len(text) > content_max_length:
                        info["content"] = text[:content_max_length]
                        print(f"      ✓ 본문 추출 성공 (선택자: {selector}, 원본: {len(text)}자, 잘림: {content_max_length}자)")
                    else:
                        info["content"] = text
                        print(f"      ✓ 본문 추출 성공 (선택자: {selector}, 길이: {len(text)}자)")
                    break
            else:
                # 디버깅: 선택자를 찾지 못한 경우 로그 출력 (첫 번째 페이지만)
                if not info["content"] and selector == content_selectors[0]:
                    print(f"      ⚠ 선택자 '{selector}'를 찾지 못했습니다.")
        
        # CSS Selector로 찾지 못한 경우 XPath로 시도 (#center)
        if not info["content"]:
            try:
                from lxml import etree
                # BeautifulSoup을 lxml로 변환
                html_str = str(soup)
                tree = etree.HTML(html_str)
                center_elements = tree.xpath('//*[@id="center"]')
                if center_elements:
                    element = center_elements[0]
                    text = " ".join(element.itertext()).strip()
                    if text and len(text) > 20 and "홈 >" not in text[:20]:
                        # content_max_length가 지정되어 있으면 앞에서 N자까지만 가져오기
                        if content_max_length > 0 and len(text) > content_max_length:
                            info["content"] = text[:content_max_length]
                            print(f"      ✓ 본문 추출 성공 (XPath: //*[@id='center'], 원본: {len(text)}자, 잘림: {content_max_length}자)")
                        else:
                            info["content"] = text
                            print(f"      ✓ 본문 추출 성공 (XPath: //*[@id='center'], 길이: {len(text)}자)")
            except Exception as e:
                # XPath 실패 시 무시하고 계속 진행
                pass
        
        # 여전히 찾지 못한 경우 더 넓은 범위에서 시도
        if not info["content"]:
            # body 전체에서 본문 같은 부분 찾기
            body = soup.select_one("body")
            if body:
                # 스크립트, 스타일, 주석 제거
                for script in body.select("script, style, noscript"):
                    script.decompose()
                text = body.get_text(" ", strip=True)
                # 너무 짧거나 너무 길면 제외
                if 50 < len(text) < 100000:
                    # content_max_length가 지정되어 있으면 앞에서 N자까지만 가져오기
                    if content_max_length > 0 and len(text) > content_max_length:
                        info["content"] = text[:content_max_length]
                        print(f"      ✓ 본문 추출 성공 (body 전체, 원본: {len(text)}자, 잘림: {content_max_length}자)")
                    else:
                        info["content"] = text
                        print(f"      ✓ 본문 추출 성공 (body 전체, 길이: {len(text)}자)")

        # 담당부서 추출 (law.go.kr iframe 내부 우선)
        # law.go.kr 사이트: #conScroll > div.cont_subtit > p > a > span:nth-child(2)
        department_element = soup.select_one("#conScroll > div.cont_subtit > p > a > span:nth-child(2)")
        if department_element:
            info["department"] = department_element.get_text(strip=True)
            print(f"      ✓ 소관부서 추출 성공 (law.go.kr iframe): {info['department']}")
        else:
            # fallback: #conScroll > div.subtit2
            department_element = soup.select_one("#conScroll > div.subtit2")
            if department_element:
                department_text = department_element.get_text(strip=True)
                # 콤마로 분리해서 앞부분만 가져오기 (전화번호 제거)
                if "," in department_text:
                    info["department"] = department_text.split(",")[0].strip()
                else:
                    info["department"] = department_text
                print(f"      ✓ 소관부서 추출 성공 (law.go.kr iframe fallback): {info['department']}")
            else:
                # KFB 사이트 선택자 (fallback)
                for item in soup.select("ul.viewInfo li.item"):
                    label = item.select_one("span.type01")
                    value = item.select_one("span.type02")
                    if not label or not value:
                        continue
                    label_text = label.get_text(strip=True)
                    if "담당부서" in label_text or "소관부서" in label_text:
                        info["department"] = value.get_text(strip=True)
                        print(f"      ✓ 소관부서 추출 성공 (KFB 사이트): {info['department']}")
                        break

        # 파일명 추출
        file_anchor = soup.select_one("ul.viewInfo li.file a")
        if file_anchor:
            info["file_name"] = file_anchor.get_text(strip=True)

        return info

    # ------------------------------------------------------------------
    # 두 번째 목록 페이지 가져오기
    # ------------------------------------------------------------------
    def fetch_second_level_list(
        self,
        driver: webdriver.Chrome,
        item: Dict,
        detail_link: str,
    ) -> Optional[BeautifulSoup]:
        """
        첫 번째 목록 항목을 클릭하여 두 번째 목록 페이지를 가져온다.
        JavaScript 링크인 경우 실제 DOM 요소를 찾아서 클릭한다.
        """
        try:
            link_lower = detail_link.lower()
            if link_lower.startswith("javascript"):
                # JavaScript 링크인 경우 실제 요소를 찾아서 클릭
                number = self._extract_number(detail_link)
                if number:
                    # 방법 1: href에 readRun(숫자)가 포함된 링크 찾기
                    try:
                        link_element = driver.find_element(
                            By.XPATH, 
                            f"//a[contains(@href, 'readRun({number})') or contains(@onclick, 'readRun({number})')]"
                        )
                        driver.execute_script("arguments[0].click();", link_element)
                        time.sleep(2)
                        return BeautifulSoup(driver.page_source, "lxml")
                    except:
                        # 방법 2: CSS Selector로 시도
                        try:
                            link_element = driver.find_element(
                                By.CSS_SELECTOR,
                                f"a[href*='readRun({number})'], a[onclick*='readRun({number})']"
                            )
                            driver.execute_script("arguments[0].click();", link_element)
                            time.sleep(2)
                            return BeautifulSoup(driver.page_source, "lxml")
                        except:
                            # 방법 3: JavaScript 함수가 페이지에 있는지 확인 후 실행
                            try:
                                # 페이지에 readRun 함수가 있는지 확인
                                has_readrun = driver.execute_script("return typeof readRun !== 'undefined';")
                                if has_readrun:
                                    driver.execute_script(f"readRun({number});")
                                    time.sleep(2)
                                    return BeautifulSoup(driver.page_source, "lxml")
                                else:
                                    print(f"    ⚠ readRun 함수가 페이지에 정의되어 있지 않습니다.")
                                    return None
                            except Exception as e:
                                print(f"    ⚠ JavaScript 실행 실패: {e}")
                                return None
                else:
                    # 다른 JavaScript 함수인 경우 직접 실행 시도
                    js_code = detail_link.replace("Javascript:", "").replace("javascript:", "")
                    try:
                        driver.execute_script(js_code)
                        time.sleep(2)
                        return BeautifulSoup(driver.page_source, "lxml")
                    except:
                        return None
            else:
                # 일반 URL인 경우
                driver.get(detail_link)
                time.sleep(2)
                return BeautifulSoup(driver.page_source, "lxml")
        except Exception as exc:
            print(f"  ✗ 두 번째 목록 페이지 이동 실패: {detail_link} - {exc}")
            return None

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
    def crawl_finlaw(
        self,
        limit: int = 0,
        download_files: bool = False,
        content_max_length: int = 0,
    ) -> List[Dict]:
        """
        금융관련법규 스크래핑
        URL: https://www.kfb.or.kr/publicdata/data_finlaw.php

        Args:
            limit: 첫 번째 목록에서 가져올 개수 제한 (0=전체)
            download_files: 파일 다운로드 여부
            content_max_length: 본문 최대 글자수 (0이면 전체, 지정하면 앞에서 N자까지만 가져오기)
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
            driver = webdriver.Chrome(options=chrome_options)
            print("Selenium 드라이버 생성 완료")
        except Exception as exc:
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}")
            driver = None

        if not driver:
            print("⚠ Selenium이 필요하지만 생성하지 못했습니다.")
            return all_results

        try:
            # 첫 페이지 가져오기
            if not self._open_with_driver(driver, self.LIST_URL):
                return all_results

            soup = BeautifulSoup(driver.page_source, "lxml")
            self.save_debug_html(soup)

            # 첫 페이지 데이터 추출 (페이지네이션 없음)
            first_page_items = self.extract_table_data(soup)
            all_results.extend(first_page_items)
            print(f"첫 번째 목록: {len(first_page_items)}개 항목 추출")

            # limit 적용: 첫 번째 목록에서만 limit 적용
            if limit > 0:
                all_results = all_results[:limit]
                print(f"첫 번째 목록 limit 적용: {limit}개 항목만 처리 (전체: {len(first_page_items)}개)")

            # 2단계 목록 구조 처리: 첫 번째 목록 → 두 번째 목록 → 상세 페이지
            print("\n=== 2단계 목록 구조 처리 시작 ===")
            final_results: List[Dict] = []
            
            # 첫 번째 목록 페이지로 다시 이동 (링크 클릭을 위해)
            driver.get(self.LIST_URL)
            time.sleep(2)
            
            for idx, first_level_item in enumerate(all_results, start=1):
                first_detail_link = first_level_item.get("detail_link", "")
                if not first_detail_link:
                    print(f"[{idx}/{len(all_results)}] 첫 번째 목록 항목에 링크 없음 - {first_level_item.get('title','')}")
                    continue

                print(f"\n[{idx}/{len(all_results)}] 첫 번째 목록 항목 처리: {first_level_item.get('title','')[:50]}...")
                
                # 첫 번째 목록 페이지로 다시 이동 (각 항목 클릭 전에)
                if idx > 1:
                    driver.get(self.LIST_URL)
                    time.sleep(2)
                
                # 첫 번째 목록 항목 클릭하여 두 번째 목록 페이지 가져오기
                second_list_soup = self.fetch_second_level_list(driver, first_level_item, first_detail_link)
                if not second_list_soup:
                    print(f"  ⚠ 두 번째 목록 페이지를 가져오지 못했습니다.")
                    continue

                # 디버깅: 두 번째 목록 페이지 HTML 저장 (첫 번째만)
                if idx == 1:
                    self.save_debug_html(second_list_soup, filename="debug_kfb_finlaw_second_list.html")

                # 두 번째 목록에서 항목 추출 (페이지네이션 없음)
                second_level_items = self.extract_table_data(second_list_soup)
                print(f"  ✓ 두 번째 목록에서 {len(second_level_items)}개 항목 발견")

                # 두 번째 목록의 각 항목에 대해 상세 페이지 처리
                for second_idx, second_item in enumerate(second_level_items, 1):
                    second_detail_link = second_item.get("detail_link", "")
                    if not second_detail_link:
                        print(f"    [{second_idx}/{len(second_level_items)}] 두 번째 목록 항목에 링크 없음 - {second_item.get('title','')}")
                        continue

                    print(f"    [{second_idx}/{len(second_level_items)}] 상세 페이지 처리: {second_item.get('title','')[:50]}...")
                    
                    # 상세 페이지 가져오기 (일반 URL이면 직접 접근)
                    if second_detail_link.startswith("http"):
                        # law.go.kr 같은 외부 링크는 직접 접근
                        driver.get(second_detail_link)
                        time.sleep(3)  # iframe 로딩 대기 시간 증가
                        
                        # #lawService iframe으로 전환하여 본문 추출
                        detail_soup = None
                        try:
                            # #lawService iframe 찾기
                            law_service_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#lawService")
                            driver.switch_to.frame(law_service_iframe)
                            time.sleep(2)  # iframe 내부 로딩 대기
                            
                            # iframe 내부 HTML 가져오기
                            iframe_html = driver.page_source
                            detail_soup = BeautifulSoup(iframe_html, "lxml")
                            
                            # 디버깅: 첫 번째 상세 페이지만 HTML 저장
                            if idx == 1 and second_idx == 1:
                                self.save_debug_html(detail_soup, filename="debug_kfb_finlaw_detail_iframe.html")
                                print(f"      디버그 HTML 저장 (iframe): output/debug/debug_kfb_finlaw_detail_iframe.html")
                            
                            # default_content로 복귀
                            driver.switch_to.default_content()
                        except Exception as e:
                            print(f"      ⚠ iframe 전환 실패: {e}")
                            # iframe 전환 실패 시 메인 페이지에서 추출 시도
                            driver.switch_to.default_content()
                            detail_soup = BeautifulSoup(driver.page_source, "lxml")
                    else:
                        # JavaScript 링크인 경우
                        detail_soup = self.fetch_detail_with_driver(driver, second_item, second_detail_link)
                    if not detail_soup:
                        if second_detail_link.lower().startswith("javascript"):
                            print(f"      ⚠ JavaScript 링크는 requests로 처리할 수 없어 건너뜁니다: {second_detail_link}")
                            continue
                        detail_soup = self.fetch_page(second_detail_link)

                    if not detail_soup:
                        print(f"      ✗ 상세 페이지를 가져오지 못했습니다.")
                        continue
                    
                    # 상세 페이지에서 정보 추출
                    detail_info = self.extract_detail_info(detail_soup, content_max_length=content_max_length)
                    
                    # 규정명: "1뎁스 제목>2뎁스 제목" 형태
                    first_title = first_level_item.get("title", "").strip()
                    second_title = second_item.get("title", "").strip()
                    regulation_name = f"{first_title}>{second_title}" if first_title and second_title else second_title
                    
                    # 최종 결과 항목 생성 (첫 번째 목록 정보 + 두 번째 목록 정보 + 상세 정보)
                    final_item = {
                        "no": second_item.get("no", ""),
                        "title": second_item.get("title", ""),
                        "regulation_name": regulation_name,
                        "organization": "은행연합회",
                        "content": detail_info.get("content", ""),
                        "department": detail_info.get("department", ""),
                        "file_name": detail_info.get("file_name", ""),
                        "file_download_link": second_item.get("download_link", ""),
                        "enactment_date": "",
                        "revision_date": "",
                    }

                    # 날짜 추출
                    enactment, revision = self.extract_dates_from_text(final_item.get("content", ""))
                    final_item["enactment_date"] = enactment
                    final_item["revision_date"] = revision

                    final_results.append(final_item)
                    
                    if detail_info.get("content"):
                        content_preview = detail_info.get("content", "")[:100].replace("\n", " ")
                        print(f"      ✓ 본문 추출 완료 ({len(detail_info.get('content', ''))}자): {content_preview}...")
                    else:
                        print(f"      ⚠ 본문 추출 실패")

            # 최종 결과를 all_results로 교체
            all_results = final_results
            print(f"\n=== 2단계 목록 구조 처리 완료: 총 {len(all_results)}개 항목 추출 ===")

        finally:
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


def save_finlaw_results(records: List[Dict]):
    """JSON 및 CSV로 금융관련법규 데이터를 저장한다."""
    if not records:
        print("저장할 금융관련법규 데이터가 없습니다.")
        return

    import json
    import csv

    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    for item in records:
        law_item = {
            "번호": item.get("no", ""),
            "규정명": item.get("regulation_name", ""),
            "기관명": item.get("organization", "은행연합회"),
            "본문": item.get("content", ""),
            "제정일": item.get("enactment_date", ""),
            "최근 개정일": item.get("revision_date", ""),
            "소관부서": item.get("department", ""),
            "파일 다운로드 링크": item.get("file_download_link", ""),
            "파일 이름": item.get("file_name", ""),
        }
        law_results.append(law_item)
    
    # JSON 저장 (한글 필드명으로) - output/json 디렉토리에 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)

    json_path = os.path.join(json_dir, "kfb_finlaw_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": "https://www.kfb.or.kr/publicdata/data_finlaw.php",
                "total_count": len(law_results),
                "results": law_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"JSON 저장 완료: {json_path}")

    # CSV 저장 - output/csv 디렉토리에 저장
    csv_dir = os.path.join("output", "csv")
    os.makedirs(csv_dir, exist_ok=True)

    csv_path = os.path.join(csv_dir, "kfb_finlaw_scraper.csv")
    
    # 헤더 정의 (번호, 규정명, 기관명, 본문, 제정일, 최근 개정일, 소관부서, 파일 다운로드 링크, 파일 이름)
    headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 다운로드 링크", "파일 이름"]

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for law_item in law_results:
            # CSV 저장 시 본문의 줄바꿈 처리
            csv_item = law_item.copy()
            csv_item["본문"] = csv_item.get("본문", "").replace("\n", " ").replace("\r", " ")
            writer.writerow(csv_item)
    print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="은행연합회 금융관련법규 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="첫 번째 목록에서 가져올 개수 제한 (0=전체)")
    parser.add_argument("--content", type=int, default=0, help="본문 최대 글자수 (0이면 전체, 지정하면 앞에서 N자까지만 가져오기, 기본값: 0)")
    args = parser.parse_args()
    
    scraper = KfbFinlawScraper()
    results = scraper.crawl_finlaw(limit=args.limit, content_max_length=args.content)
    print(f"\n추출된 데이터: {len(results)}개")
    save_finlaw_results(results)

