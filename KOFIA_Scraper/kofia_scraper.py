"""
금융투자협회 스크래퍼
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
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common.base_scraper import BaseScraper


class KofiaScraper(BaseScraper):
    """금융투자협회 - 법규정보시스템 스크래퍼"""
    
    BASE_URL = "https://law.kofia.or.kr"
    LIST_URL = "https://law.kofia.or.kr/service/law/lawCurrentMain.do"
    
    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 트리 구조에서 규정 링크 추출
    # ------------------------------------------------------------------
    def extract_tree_links(self, driver: webdriver.Chrome) -> List[Dict]:
        """
        왼쪽 트리 iframe에서 모든 규정 링크를 추출한다.
        CSS Selector: #webfx-tree-object-*-anchor 패턴 사용
        """
        links: List[Dict] = []

        try:
            # 왼쪽 트리 iframe으로 전환
            tree_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#tree01")
            driver.switch_to.frame(tree_iframe)
            time.sleep(2)  # iframe 로딩 대기

            # 트리를 모두 펼치기 (모든 링크를 보이게 하기 위해)
            try:
                # 방법 1: allFolderOpen() 함수 호출
                driver.execute_script("""
                    try {
                        if (typeof allFolderOpen === 'function') {
                            allFolderOpen();
                        }
                    } catch(e) { console.log('allFolderOpen error:', e); }
                """)
                time.sleep(1)
                
                # 방법 2: tree1.expandChildren() 호출
                driver.execute_script("""
                    try {
                        if (typeof tree1 !== 'undefined' && typeof tree1.expandChildren === 'function') {
                            tree1.expandChildren();
                        }
                    } catch(e) { console.log('tree1.expandChildren error:', e); }
                """)
                time.sleep(1)
                
                # 방법 3: 모든 트리 항목을 재귀적으로 펼치기
                driver.execute_script("""
                    try {
                        // 모든 트리 아이템 찾기
                        var allItems = [];
                        function collectTreeItems(node) {
                            if (!node) return;
                            // WebFXTreeItem의 경우
                            if (node.items) {
                                for (var i = 0; i < node.items.length; i++) {
                                    collectTreeItems(node.items[i]);
                                }
                            }
                            // DOM 요소의 경우
                            var anchors = document.querySelectorAll('a[id^="webfx-tree-object-"]');
                            for (var i = 0; i < anchors.length; i++) {
                                var anchor = anchors[i];
                                var parent = anchor.parentElement;
                                // 접혀있는 항목인지 확인하고 펼치기
                                if (parent && parent.className && parent.className.indexOf('closed') !== -1) {
                                    // 클릭하여 펼치기
                                    var img = anchor.querySelector('img');
                                    if (img && img.src && img.src.indexOf('folder') !== -1) {
                                        anchor.click();
                                    }
                                }
                            }
                        }
                        // tree1부터 시작
                        if (typeof tree1 !== 'undefined') {
                            collectTreeItems(tree1);
                        }
                        // DOM에서 직접 찾기
                        var folders = document.querySelectorAll('a[id^="webfx-tree-object-"][href*="javascript"]');
                        for (var i = 0; i < folders.length; i++) {
                            var folder = folders[i];
                            var img = folder.querySelector('img');
                            if (img && (img.src.indexOf('folder') !== -1 || img.src.indexOf('cbook') !== -1)) {
                                // 접혀있는 폴더면 펼치기
                                var parent = folder.parentElement;
                                if (parent && (parent.className.indexOf('closed') !== -1 || 
                                    getComputedStyle(parent).display === 'none')) {
                                    folder.click();
                                }
                            }
                        }
                    } catch(e) { console.log('expand all error:', e); }
                """)
                time.sleep(3)  # 트리 펼치기 대기 (더 긴 대기)
                
                # 스크롤하여 모든 요소가 로드되도록
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                
                print(f"  트리 펼치기 시도 완료")
            except Exception as e:
                print(f"  ⚠ 트리 펼치기 실패 (계속 진행): {e}")

            # 트리 구조에서 모든 링크 추출 - webfx-tree-object-*-anchor 패턴
            # 링크 수가 안정화될 때까지 여러 번 시도
            tree_link_selectors = [
                "a[id^='webfx-tree-object-']",
                "[id^='webfx-tree-object-'][id$='-anchor']",
            ]

            all_links = []
            prev_count = 0
            max_attempts = 5  # 최대 5번 시도
            
            for attempt in range(max_attempts):
                current_links = []
                for selector in tree_link_selectors:
                    try:
                        found_links = driver.find_elements(By.CSS_SELECTOR, selector)
                        if found_links:
                            current_links = found_links
                            break
                    except Exception as e:
                        continue
                
                current_count = len(current_links)
                print(f"  시도 {attempt + 1}/{max_attempts}: {current_count}개 링크 발견")
                
                # 링크 수가 증가하지 않으면 종료
                if current_count > prev_count:
                    all_links = current_links
                    prev_count = current_count
                    time.sleep(1)  # 추가 로딩 대기
                elif current_count == prev_count and current_count > 0:
                    # 링크 수가 같고 0보다 크면 안정화된 것으로 간주
                    all_links = current_links
                    break
                else:
                    # 링크 수가 줄어들었거나 같으면 이전 결과 사용
                    if all_links:
                        break
                    all_links = current_links
                    prev_count = current_count
                    time.sleep(1)
            
            # 중복 제거 (같은 ID를 가진 링크가 여러 번 나타날 수 있음)
            seen_ids = set()
            unique_links = []
            for link in all_links:
                try:
                    link_id = link.get_attribute("id") or ""
                    if link_id and link_id not in seen_ids:
                        seen_ids.add(link_id)
                        unique_links.append(link)
                    elif not link_id:
                        # ID가 없으면 텍스트로 구분
                        link_text = link.text.strip()
                        if link_text and link_text not in seen_ids:
                            seen_ids.add(link_text)
                            unique_links.append(link)
                except:
                    continue
            
            all_links = unique_links
            print(f"  최종: {len(all_links)}개 링크 (중복 제거 후)")

            # 링크 정보 추출 - 모든 링크를 수집 (depth 필터링 제거)
            for link_element in all_links:
                try:
                    text = link_element.text.strip()
                    element_id = link_element.get_attribute("id") or ""
                    # href와 onclick 모두 확인 (실제로는 href에 JavaScript가 있을 수 있음)
                    href = link_element.get_attribute("href") or ""
                    onclick = link_element.get_attribute("onclick") or ""
                    # href나 onclick 중 하나에 JavaScript 코드가 있음
                    js_code = href if href.startswith("javascript:") else onclick

                    # 규정명이 있는 링크만 수집 (빈 텍스트나 너무 짧은 것 제외)
                    # depth에 상관없이 모든 링크 수집 (나중에 본문 확인으로 필터링)
                    if text and len(text) > 2:
                        item: Dict[str, str] = {
                            "title": text,
                            "regulation_name": text,
                            "organization": "금융투자협회",
                            "tree_element_id": element_id,  # 클릭할 요소 ID 저장
                            "tree_onclick": js_code,  # href 또는 onclick 저장
                            "detail_link": "",
                            "content": "",
                            "department": "",
                            "file_names": [],  # 여러 첨부파일 지원
                            "download_links": [],  # 여러 첨부파일 링크 지원
                            "enactment_date": "",
                            "revision_date": "",
                        }
                        links.append(item)
                except Exception as e:
                    print(f"  ⚠ 링크 추출 중 오류: {e}")
                    continue

            # 메인 프레임으로 복귀
            driver.switch_to.default_content()

            print(f"  총 {len(links)}개의 규정 링크 추출 완료")

        except Exception as e:
            print(f"⚠ 트리 링크 추출 실패: {e}")
            import traceback
            traceback.print_exc()
            try:
                driver.switch_to.default_content()
            except:
                pass

        return links

    # ------------------------------------------------------------------
    # 트리 링크 클릭 및 콘텐츠 추출
    # ------------------------------------------------------------------
    def click_tree_link_and_extract(
        self, driver: webdriver.Chrome, item: Dict
    ) -> Optional[BeautifulSoup]:
        """
        트리 링크를 클릭하고 오른쪽 iframe에서 내용을 추출한다.
        """
        try:
            # 왼쪽 트리 iframe으로 전환
            tree_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#tree01")
            driver.switch_to.frame(tree_iframe)
            time.sleep(1)

            # 요소 ID로 링크 찾기 및 클릭
            element_id = item.get("tree_element_id", "")
            if element_id:
                try:
                    # CSS Selector로 요소 찾기
                    link_element = driver.find_element(By.CSS_SELECTOR, f"#{element_id}")
                    driver.execute_script("arguments[0].click();", link_element)
                    time.sleep(2)  # 콘텐츠 로딩 대기
                except Exception as e:
                    print(f"  ⚠ 요소 클릭 실패 ({element_id}): {e}")
                    # 메인 프레임으로 복귀
                    driver.switch_to.default_content()
                    return None

            # 메인 프레임으로 복귀
            driver.switch_to.default_content()

            # 오른쪽 콘텐츠 iframe 확인
            time.sleep(2)  # iframe 로딩 대기
            try:
                # 첫 번째 iframe (iframe01)로 전환
                content_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#iframe01")
                driver.switch_to.frame(content_iframe)
                time.sleep(2)

                # iframe01 내부에서 소관부서(#lawbtn1) 및 첨부파일(#lawbtn) 추출 (iframe01에 직접 있음)
                iframe01_soup = BeautifulSoup(driver.page_source, "lxml")
                
                # 디버깅: iframe01 HTML 저장 (본문이 있는 첫 번째 항목만)
                # #lawFullContent가 있는 경우에만 저장 (본문이 있는 페이지)
                if not hasattr(self, '_iframe01_debug_saved'):
                    # #lawbtn이 있는지 확인 (본문이 있는 페이지인지 확인)
                    if iframe01_soup.select_one("#lawbtn"):
                        self.save_debug_html(iframe01_soup, filename="debug_kofia_iframe01.html")
                        self._iframe01_debug_saved = True
                        print(f"  디버깅: iframe01 HTML 저장 완료 (본문 페이지)")
                
                department_info = self._extract_department_from_iframe01(iframe01_soup)
                file_info = self._extract_files_from_iframe01(iframe01_soup)
                
                # #lawFullContent는 iframe 태그 자체이므로 iframe으로 찾기
                try:
                    # #lawFullContent iframe 찾기
                    law_full_content_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#lawFullContent")
                    print(f"  ✓ #lawFullContent iframe 발견")
                    
                    # #lawFullContent iframe으로 전환
                    driver.switch_to.frame(law_full_content_iframe)
                    time.sleep(2)
                    print(f"  ✓ #lawFullContent iframe으로 전환 완료")
                    
                    # 이제 iframe 내부에서 #lawcontent div 찾기
                    # iframe 내용 추출
                    soup = BeautifulSoup(driver.page_source, "lxml")
                    
                    # 소관부서 및 첨부파일 정보를 soup에 추가 (나중에 extract_content_from_iframe에서 사용)
                    if department_info:
                        soup.department_info = department_info
                    if file_info:
                        soup.file_info = file_info
                    
                    # 디버깅: 최종 HTML에서 본문 요소 확인
                    lawcontent_div = soup.select_one("#lawcontent")
                    if lawcontent_div:
                        text_len = len(lawcontent_div.get_text(strip=True))
                        print(f"  ✓ #lawcontent div 발견 (텍스트 길이: {text_len}자)")
                    else:
                        print(f"  ⚠ #lawcontent div를 찾지 못함")
                        # body 확인
                        body = soup.select_one("body")
                        if body:
                            text_len = len(body.get_text(strip=True))
                            print(f"  디버깅: body 발견 (텍스트 길이: {text_len}자)")
                    
                    # 모든 iframe에서 복귀
                    driver.switch_to.default_content()
                    return soup
                except Exception as e:
                    # #lawFullContent iframe을 찾지 못한 경우
                    print(f"  ⚠ #lawFullContent iframe을 찾지 못함: {e}")
                    # 현재 iframe에서 모든 iframe 찾기
                    all_iframes = driver.find_elements(By.CSS_SELECTOR, "iframe")
                    print(f"  현재 iframe 내부의 iframe 개수: {len(all_iframes)}")
                    if all_iframes:
                        # 첫 번째 iframe으로 전환 시도
                        driver.switch_to.frame(all_iframes[0])
                        time.sleep(2)
                        print(f"  ✓ 첫 번째 iframe으로 전환 완료")
                        
                        # iframe 내용 추출
                        soup = BeautifulSoup(driver.page_source, "lxml")
                        # 소관부서 및 첨부파일 정보 추가
                        if department_info:
                            soup.department_info = department_info
                        if file_info:
                            soup.file_info = file_info
                        driver.switch_to.default_content()
                        return soup
                    else:
                        # iframe이 없으면 현재 iframe01의 내용 사용
                        soup = BeautifulSoup(driver.page_source, "lxml")
                        # 소관부서 및 첨부파일 정보 추가
                        if department_info:
                            soup.department_info = department_info
                        if file_info:
                            soup.file_info = file_info
                        driver.switch_to.default_content()
                        return soup
                
            except Exception as e:
                print(f"  ⚠ 콘텐츠 iframe 접근 실패: {e}")
                import traceback
                traceback.print_exc()
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                return None

        except Exception as e:
            print(f"  ⚠ 링크 클릭 및 추출 실패: {e}")
            import traceback
            traceback.print_exc()
            try:
                driver.switch_to.default_content()
            except:
                pass
            return None

    # ------------------------------------------------------------------
    # iframe01에서 소관부서 추출 (iframe01에 직접 있음)
    # ------------------------------------------------------------------
    def _extract_department_from_iframe01(self, soup: BeautifulSoup) -> Optional[str]:
        """
        iframe01 내부에서 소관부서(#lawbtn1) 추출
        """
        if soup is None:
            return None
        
        # CSS Selector 시도
        department_element = soup.select_one("#lawbtn1 > table > tbody > tr > td:nth-child(3) > div")
        
        # CSS Selector로 못 찾은 경우 단계별로 확인
        if not department_element:
            # #lawbtn1 요소 자체 확인
            lawbtn1 = soup.select_one("#lawbtn1")
            if lawbtn1:
                # table 내부 확인
                table = lawbtn1.select_one("table")
                if table:
                    rows = table.select("tbody > tr")
                    if rows:
                        # 첫 번째 행의 3번째 셀 확인
                        first_row = rows[0]
                        cells = first_row.select("td")
                        if len(cells) >= 3:
                            third_cell = cells[2]  # 0-based index, 3번째는 [2]
                            div = third_cell.select_one("div")
                            if div:
                                department_element = div
        
        # XPath로도 시도 (lxml 사용)
        if not department_element:
            try:
                from lxml import etree
                # BeautifulSoup을 문자열로 변환 후 lxml로 파싱
                html_str = str(soup)
                tree = etree.HTML(html_str.encode('utf-8'))
                xpath_result = tree.xpath('//*[@id="lawbtn1"]/table/tbody/tr/td[3]/div/text()')
                if xpath_result:
                    department_text = ' '.join(xpath_result).strip()
                    if department_text:
                        # 가상 객체 생성
                        class MockElement:
                            def get_text(self, strip=True):
                                return department_text.strip() if strip else department_text
                        department_element = MockElement()
            except Exception as e:
                pass  # XPath 실패는 무시
        
        if department_element:
            department_text = department_element.get_text(strip=True)
            # '운영부서:자율규제기획부' 형태에서 콜론 뒤만 추출
            if ':' in department_text:
                return department_text.split(':', 1)[1].strip()
            else:
                return department_text
        
        return None

    # ------------------------------------------------------------------
    # iframe01에서 첨부파일 추출 (iframe01에 직접 있음)
    # ------------------------------------------------------------------
    def _extract_files_from_iframe01(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        iframe01 내부에서 첨부파일(#lawbtn) 추출
        - HWP 파일: #lawbtn > ul.btn > li:nth-child(3) > a
        - PDF 파일: #lawbtn > ul.btn > li:nth-child(4) > a
        """
        if soup is None:
            return None
        
        file_info = {
            "file_names": [],
            "download_links": [],
        }
        
        # 디버깅: #lawbtn 요소 확인
        lawbtn = soup.select_one("#lawbtn")
        if not lawbtn:
            print(f"  ⚠ #lawbtn 요소를 찾지 못함")
            return None
        
        print(f"  ✓ #lawbtn 요소 발견")
        
        # ul.btn 확인
        ul_btn = lawbtn.select_one("ul.btn")
        if not ul_btn:
            print(f"  ⚠ ul.btn 요소를 찾지 못함")
            # 다른 선택자 시도
            ul_btn = lawbtn.select_one("ul")
            if ul_btn:
                print(f"  ✓ ul 요소 발견 (class: {ul_btn.get('class', [])})")
        
        if ul_btn:
            # 모든 li 요소 확인
            li_elements = ul_btn.select("li")
            print(f"  디버깅: ul 내부의 li 개수: {len(li_elements)}")
            for idx, li in enumerate(li_elements, 1):
                a_tag = li.select_one("a")
                if a_tag:
                    href = a_tag.get("href", "").strip()
                    text = a_tag.get_text(strip=True)
                    print(f"    li[{idx}]: {text[:50]}... (href: {href[:50] if href else '없음'}...)")
        else:
            li_elements = []

        if not li_elements:
            # ul이 없을 경우 lawbtn 내부의 a 태그를 직접 확인
            li_elements = lawbtn.select("li")

        for idx, li in enumerate(li_elements, 1):
            anchor = li.select_one("a")
            if not anchor:
                continue

            href = (anchor.get("href") or "").strip()
            if not href:
                continue

            href_lower = href.lower()
            if href_lower.startswith("javascript"):
                continue

            full_href = href if href_lower.startswith("http") else urljoin(self.BASE_URL, href)
            parsed = urlparse(full_href)

            if "download.do" not in parsed.path:
                continue

            query = parse_qs(parsed.query)
            gubun_values = [val for vals in query.get("gubun", []) for val in vals.split(",")]

            file_type = None  # (label, extension)
            if any(val == "101" for val in gubun_values):
                file_type = ("HWP", "hwp")
            elif any(val == "106" for val in gubun_values):
                file_type = ("PDF", "pdf")
            else:
                # gubun 파라미터가 없거나 예상과 다르면 스킵
                continue

            name = anchor.get_text(strip=True)
            if not name:
                img = anchor.select_one("img")
                if img:
                    name = (img.get("alt") or img.get("title") or "").strip()

            if not name:
                name = (anchor.get("title") or "").strip()

            if not name:
                filename_match = re.search(r'[^/]+\.(hwp|pdf)$', full_href, re.IGNORECASE)
                if filename_match:
                    name = filename_match.group(0)
                else:
                    name = f"파일.{file_type[1]}"

            file_info["file_names"].append(name)
            file_info["download_links"].append(full_href)
            print(f"  ✓ {file_type[0]} 파일 추출: {name} (href: {full_href[:60]}...)")

        if file_info["download_links"]:
            return file_info

        return None

    # ------------------------------------------------------------------
    # 콘텐츠 iframe에서 정보 추출
    # ------------------------------------------------------------------
    def extract_content_from_iframe(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        콘텐츠 iframe에서 본문, 담당부서, 날짜 등을 추출한다.
        CSS Selector 기반으로만 요소를 조회한다.
        """
        info = {
            "content": "",
            "department": "",
            "file_names": [],  # 여러 첨부파일 지원
            "download_links": [],  # 여러 첨부파일 링크 지원
            "enactment_date": "",
            "revision_date": "",
        }

        if soup is None:
            return info

        # 본문 내용 추출 - #lawcontent 우선 확인 (#lawFullContent iframe 내부에 있음)
        content_selectors = [
            "#lawcontent",  # #lawFullContent iframe 내부의 div
            "#lawFullContent",
            ".lawcon",
            ".lawFullContent",
            "#Content",
            ".content",
        ]
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if text and len(text) > 20:
                    info["content"] = text
                    print(f"  ✓ 본문 추출 성공 (셀렉터: {selector}, {len(text)}자)")
                    break

        # 담당부서 추출 - iframe01에서 추출한 정보 사용
        # soup 객체에 department_info 속성이 있으면 사용 (iframe01에서 추출한 것)
        if hasattr(soup, 'department_info') and soup.department_info:
            info["department"] = soup.department_info
            print(f"  ✓ 소관부서 추출: {info['department']}")
        else:
            # fallback: 현재 soup에서 직접 찾기 시도 (혹시 모를 경우)
            department_element = soup.select_one("#lawbtn1 > table > tbody > tr > td:nth-child(3) > div")
            if department_element:
                department_text = department_element.get_text(strip=True)
                if ':' in department_text:
                    info["department"] = department_text.split(':', 1)[1].strip()
                else:
                    info["department"] = department_text
                print(f"  ✓ 소관부서 추출 (fallback): {info['department']}")
            else:
                # 다른 방법 시도
                for row in soup.select("table tr"):
                    cells = row.select("td, th")
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        if "담당부서" in label or "소관부서" in label or "운영부서" in label:
                            # 콜론 뒤만 추출
                            if ':' in value:
                                info["department"] = value.split(':', 1)[1].strip()
                            else:
                                info["department"] = value
                            break

        # 날짜 추출 - #his_sel > option:nth-child(1)
        date_element = soup.select_one("#his_sel > option:nth-child(1)")
        if date_element:
            date_text = date_element.get_text(strip=True)
            # 날짜 텍스트에서 제정일/개정일 추출
            enactment, revision = self.extract_dates_from_text(date_text)
            if not info["enactment_date"]:
                info["enactment_date"] = enactment
            if not info["revision_date"]:
                info["revision_date"] = revision

        # 본문에서도 날짜 추출 시도 (날짜 셀렉터에서 못 찾은 경우)
        if not info["enactment_date"] or not info["revision_date"]:
            enactment, revision = self.extract_dates_from_text(info["content"])
            if not info["enactment_date"]:
                info["enactment_date"] = enactment
            if not info["revision_date"]:
                info["revision_date"] = revision

        # 첨부파일 추출 - iframe01에서 추출한 정보 사용
        # soup 객체에 file_info 속성이 있으면 사용 (iframe01에서 추출한 것)
        if hasattr(soup, 'file_info') and soup.file_info:
            info["file_names"] = soup.file_info.get("file_names", [])
            info["download_links"] = soup.file_info.get("download_links", [])
            if info["file_names"]:
                print(f"  ✓ 첨부파일 추출: {len(info['file_names'])}개 (iframe01에서)")
        else:
            # fallback: 현재 soup에서 직접 찾기 시도 (혹시 모를 경우)
            # 하지만 본문의 별표/서식 파일은 제외해야 하므로 여기서는 찾지 않음
            pass

        return info

    # ------------------------------------------------------------------
    # 스크래핑 메인
    # ------------------------------------------------------------------
    def crawl_law_info(
        self,
        limit: int = 0,
        download_files: bool = False,
    ) -> List[Dict]:
        """
        법규정보시스템 스크래핑
        URL: https://law.kofia.or.kr/service/law/lawCurrentMain.do
        
        트리 구조에서 규정을 선택하여 스크래핑하는 방식
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
            print(f"⚠ Selenium 드라이버 생성 실패: {exc}")
            return all_results

        try:
            # 메인 페이지 접근
            driver.get(self.LIST_URL)
            time.sleep(3)  # 페이지 및 iframe 로딩 대기

            # 디버그 HTML 저장
            main_soup = BeautifulSoup(driver.page_source, "lxml")
            self.save_debug_html(main_soup, filename="debug_kofia_list.html")

            print("\n=== 트리 구조에서 규정 링크 추출 ===")
            tree_links = self.extract_tree_links(driver)
            print(f"트리에서 {len(tree_links)}개의 규정 링크를 발견했습니다.")

            if not tree_links:
                print("⚠ 트리에서 규정 링크를 찾지 못했습니다.")
                # 트리 iframe 직접 접근 시도
                try:
                    tree_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#tree01")
                    driver.switch_to.frame(tree_iframe)
                    time.sleep(2)
                    tree_soup = BeautifulSoup(driver.page_source, "lxml")
                    driver.switch_to.default_content()
                    
                    # 트리 iframe HTML 저장
                    self.save_debug_html(tree_soup, filename="debug_kofia_tree.html")
                    print("트리 iframe HTML 저장: output/debug/debug_kofia_tree.html")
                except:
                    pass

            # 제한 적용
            if limit > 0:
                tree_links = tree_links[:limit]

            print(f"\n=== 규정 내용 추출 시작 (총 {len(tree_links)}개) ===")
            print(f"※ 본문 내용이 있는 항목만 저장합니다.\n")
            
            for idx, item in enumerate(tree_links, 1):
                print(f"[{idx}/{len(tree_links)}] {item.get('title', 'N/A')[:50]}... 처리 중")

                # 트리 링크 클릭 및 콘텐츠 추출
                content_soup = self.click_tree_link_and_extract(driver, item)

                if content_soup:
                    # 디버그 HTML 저장 (첫 번째 페이지만)
                    self.save_debug_html(content_soup)

                    # 콘텐츠에서 정보 추출
                    content_info = self.extract_content_from_iframe(content_soup)
                    item.update(content_info)

                    # 본문 내용이 있는지 확인 (20자 이상이면 본문이 있다고 판단)
                    has_content = content_info.get("content") and len(content_info.get("content", "").strip()) > 20
                    
                    if has_content:
                        content_preview = content_info["content"][:100].replace("\n", " ")
                        print(f"  ✓ 본문 추출 완료 ({len(content_info['content'])}자): {content_preview}...")
                        
                        if content_info.get("department"):
                            print(f"  ✓ 담당부서: {content_info['department']}")

                        if content_info.get("file_names") and len(content_info["file_names"]) > 0:
                            file_count = len(content_info["file_names"])
                            print(f"  ✓ 첨부파일: {file_count}개")
                            for i, file_name in enumerate(content_info["file_names"][:3], 1):  # 처음 3개만 출력
                                print(f"    - {file_name}")
                            if file_count > 3:
                                print(f"    ... 외 {file_count - 3}개")
                        
                        # 본문이 있는 항목만 결과에 추가
                        all_results.append(item)
                        print(f"  ✓ 저장 대상으로 추가됨")
                    else:
                        print(f"  ⚠ 본문 내용 없음 (디렉토리 또는 빈 페이지) - 건너뜀")
                else:
                    print(f"  ✗ 콘텐츠 추출 실패 - 건너뜀")

                time.sleep(1)  # 요청 간 대기

        except Exception as e:
            print(f"✗ 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if driver:
                driver.quit()
                print("Selenium 드라이버 종료 완료")

        return all_results

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


def save_kofia_results(records: List[Dict]):
    """JSON 및 CSV로 금융투자협회 법규정보 데이터를 저장한다."""
    if not records:
        print("저장할 법규정보 데이터가 없습니다.")
        return

    import json
    import csv

    # JSON 저장 - output/json 디렉토리에 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)

    json_path = os.path.join(json_dir, "kofia_law.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": KofiaScraper.LIST_URL,
                "total_count": len(records),
                "results": records,
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
    csv_path = os.path.join(csv_dir, "kofia_law.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for item in records:
            # 여러 첨부파일 처리
            file_names = item.get("file_names", [])
            download_links = item.get("download_links", [])
            
            # 하위 호환성: 기존 file_name, download_link도 확인
            if not file_names and item.get("file_name"):
                file_names = [item.get("file_name")]
            if not download_links and item.get("download_link"):
                download_links = [item.get("download_link")]
            
            # 여러 첨부파일을 세미콜론으로 구분하여 저장
            file_names_str = "; ".join(file_names) if file_names else ""
            download_links_str = "; ".join(download_links) if download_links else ""
            
            writer.writerow(
                {
                    "규정명": item.get("regulation_name", item.get("title", "")),
                    "기관명": item.get("organization", "금융투자협회"),
                    "본문": (item.get("content", "") or "").replace("\n", " "),
                    "제정일": item.get("enactment_date", ""),
                    "최근 개정일": item.get("revision_date", ""),
                    "소관부서": item.get("department", ""),
                    "첨부파일링크": download_links_str,
                    "첨부파일이름": file_names_str,
                }
            )
    print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="금융투자협회 법규정보시스템 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="파일 다운로드를 건너뜁니다.",
    )
    args = parser.parse_args()

    crawler = KofiaScraper()
    results = crawler.crawl_law_info(limit=args.limit, download_files=not args.no_download)

    print(f"\n총 {len(results)}개의 법규정보를 수집했습니다.")
    save_kofia_results(results)
