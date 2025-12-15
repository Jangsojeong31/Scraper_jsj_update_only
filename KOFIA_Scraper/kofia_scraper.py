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
import csv
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor
from common.file_comparator import FileComparator


class KofiaScraper(BaseScraper):
    """금융투자협회 - 법규정보시스템 스크래퍼"""
    
    BASE_URL = "https://law.kofia.or.kr"
    LIST_URL = "https://law.kofia.or.kr/service/law/lawCurrentMain.do"
    DEFAULT_CSV_PATH = "KOFIA_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: Optional[str] = None):
        super().__init__(delay)
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        self.downloads_dir = self.output_dir / "downloads"
        self.previous_dir = self.downloads_dir / "previous"
        self.current_dir = self.downloads_dir / "current"
        
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.previous_dir.mkdir(parents=True, exist_ok=True)
        self.current_dir.mkdir(parents=True, exist_ok=True)
        
        # FileExtractor 초기화 (current 디렉토리 사용)
        self.file_extractor = FileExtractor(download_dir=str(self.current_dir), session=self.session)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=str(self.downloads_dir))
        
        # 하위 호환성을 위해 기존 download_dir도 유지
        self.download_dir = str(self.downloads_dir)
        
        self.csv_path = csv_path or self.DEFAULT_CSV_PATH
        self.target_laws = self._load_target_laws(self.csv_path)
        self.target_lookup = {
            self._normalize_title(item["law_name"]): item
            for item in self.target_laws
            if item.get("law_name")
        }
        if self.target_laws:
            print(f"✓ CSV에서 {len(self.target_laws)}개의 대상 규정을 불러왔습니다: {self.csv_path}")
        else:
            print("⚠ 대상 CSV를 찾지 못했거나 비어 있습니다. 트리 전체를 대상으로 진행합니다.")

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
    # CSV 대상 규정 로드 및 필터링
    # ------------------------------------------------------------------
    def _load_target_laws(self, csv_path: str) -> List[Dict]:
        """
        CSV 파일에서 스크래핑 대상 규정명을 로드한다.
        기대 컬럼: 구분, 법령명
        """
        if not csv_path:
            return []
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            csv_file = find_project_root() / csv_path
        if not csv_file.exists():
            print(f"⚠ KOFIA 대상 CSV를 찾을 수 없습니다: {csv_file}")
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
            print(f"⚠ KOFIA 대상 CSV 로드 실패: {exc}")
            return []
        return targets

    def _normalize_title(self, text: Optional[str]) -> str:
        """비교를 위한 규정명 정규화"""
        if not text:
            return ""
        cleaned = re.sub(r"[\s\W]+", "", text)
        return cleaned.lower()

    def _filter_tree_links_by_targets(self, tree_links: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """
        CSV 대상 목록에 포함된 규정만 순서대로 반환한다.
        Returns:
            (선택된 링크 리스트, 매칭 실패한 규정명 리스트)
        """
        if not self.target_laws:
            return tree_links, []

        normalized_tree: Dict[str, List[Dict]] = {}
        # 디버깅: 트리에서 추출한 이름들을 저장
        tree_names_map: Dict[str, str] = {}  # 정규화된 키 -> 원본 이름
        
        for link in tree_links:
            original_name = link.get("regulation_name") or link.get("title", "")
            key = self._normalize_title(original_name)
            if not key:
                continue
            normalized_tree.setdefault(key, []).append(link)
            if key not in tree_names_map:
                tree_names_map[key] = original_name

        selected_links: List[Dict] = []
        missing_targets: List[str] = []
        # 디버깅: 매칭 실패한 항목의 유사한 이름 찾기
        missing_with_similar: List[Tuple[str, List[str]]] = []

        for target in self.target_laws:
            target_name = target["law_name"]
            key = self._normalize_title(target_name)
            matches = normalized_tree.get(key)
            if matches and len(matches) > 0:
                # 같은 이름의 링크가 여러 개 있을 수 있으므로 첫 번째 사용
                # 링크를 복사해서 사용 (원본은 유지하여 중복 항목도 처리 가능)
                original_link = matches[0]
                link = dict(original_link)  # 딕셔너리 복사
                if target.get("law_name"):
                    link["regulation_name"] = target["law_name"]
                link["target_name"] = target["law_name"]
                link["target_category"] = target.get("category", "")
                selected_links.append(link)
                # 첫 번째 링크를 제거하지 않고 유지 (중복 항목 처리)
                # matches.pop(0) 대신 그대로 두어서 같은 이름이 여러 번 나와도 처리 가능
            else:
                missing_targets.append(target_name)
                # 유사한 이름 찾기 (부분 문자열 매칭)
                similar_names = []
                target_normalized = key
                for tree_key, tree_original in tree_names_map.items():
                    # 정규화된 이름이 정확히 일치하는지 확인
                    if target_normalized == tree_key:
                        similar_names.append(tree_original)
                if similar_names:
                    missing_with_similar.append((target_name, similar_names[:3]))  # 최대 3개만

        # 디버깅: 매칭 실패한 항목과 유사한 이름 출력
        if missing_with_similar:
            print(f"\n⚠ 매칭 실패한 항목과 정확히 일치하는 트리 이름 (이미 사용됨):")
            for target_name, similar in missing_with_similar:
                print(f"  CSV: {target_name}")
                print(f"    트리 이름 (이미 사용됨): {similar}")
                print(f"    → CSV에 중복 항목이 있어서 이미 매칭된 링크를 재사용합니다.")
                print()

        return selected_links, missing_targets

    # ------------------------------------------------------------------
    # 파일 다운로드 및 비교
    # ------------------------------------------------------------------
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
        diffs_dir = self.downloads_dir / "diffs"
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
    
    def _download_file_by_clicking_button(
        self, driver: webdriver.Chrome, button_selector: str, file_name: str, 
        file_type: str, regulation_name: str = ""
    ) -> Optional[Dict]:
        """버튼 클릭을 통해 파일 다운로드 및 이전 파일과 비교
        Args:
            driver: Selenium WebDriver
            button_selector: 다운로드 버튼 CSS 선택자 (iframe01 내부 기준)
            file_name: 파일명
            file_type: 파일 타입 (hwp/pdf)
            regulation_name: 규정명 (이전 파일 매칭용)
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            import shutil
            
            # 파일 확장자
            ext = f".{file_type}" if file_type else ".pdf"
            
            # 안전한 파일명 생성 (규정명 + 확장자만 사용, 중복 허용)
            if regulation_name:
                safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                safe_filename = f"{safe_reg_name}{ext}"
            else:
                base_name = re.sub(r'[^\w\s.-]', '', file_name).replace(' ', '_')
                if not base_name.endswith(ext):
                    base_name = base_name.rsplit('.', 1)[0] if '.' in base_name else base_name
                    safe_filename = f"{base_name}{ext}"
                else:
                    safe_filename = base_name
            
            # 새 파일 다운로드 경로 (current 디렉토리)
            new_file_path = self.current_dir / safe_filename
            
            # 이전 파일 경로 (previous 디렉토리)
            previous_file_path = self.previous_dir / safe_filename
            
            # iframe01로 전환하여 버튼 클릭
            print(f"  → 파일 다운로드 중: {file_name}")
            try:
                # iframe01로 전환
                driver.switch_to.default_content()
                content_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#iframe01")
                driver.switch_to.frame(content_iframe)
                time.sleep(1)
                
                # 버튼 찾기 및 클릭
                download_button = driver.find_element(By.CSS_SELECTOR, button_selector)
                driver.execute_script("arguments[0].click();", download_button)
                print(f"  ✓ 다운로드 버튼 클릭 완료")
                
                # 다운로드 완료 대기 (최대 30초)
                time.sleep(3)  # 초기 대기
                max_wait = 30
                waited = 0
                while waited < max_wait:
                    # 다운로드 디렉토리에서 파일 확인
                    downloaded_files = list(self.current_dir.glob("*"))
                    # .crdownload 파일이 있으면 아직 다운로드 중
                    crdownload_files = [f for f in downloaded_files if f.name.endswith('.crdownload')]
                    if not crdownload_files:
                        # 다운로드 완료된 파일 찾기
                        downloaded_file = None
                        for f in downloaded_files:
                            if f.is_file() and not f.name.endswith('.crdownload'):
                                # 최근 수정된 파일이면 다운로드된 파일일 가능성
                                if not downloaded_file or f.stat().st_mtime > downloaded_file.stat().st_mtime:
                                    downloaded_file = f
                        if downloaded_file:
                            break
                    time.sleep(1)
                    waited += 1
                
                # 메인 프레임으로 복귀
                driver.switch_to.default_content()
                
                # 다운로드된 파일 찾기
                downloaded_file = None
                downloaded_files = list(self.current_dir.glob("*"))
                for f in downloaded_files:
                    if f.is_file() and not f.name.endswith('.crdownload'):
                        if not downloaded_file or f.stat().st_mtime > downloaded_file.stat().st_mtime:
                            downloaded_file = f
                
                if not downloaded_file or not downloaded_file.exists():
                    print(f"  ⚠ 파일 다운로드 실패 (파일을 찾을 수 없음)")
                    return None
                
                # 다운로드한 파일을 최종 파일명으로 이동/이름 변경
                if str(downloaded_file) != str(new_file_path):
                    if new_file_path.exists():
                        new_file_path.unlink()
                    shutil.move(downloaded_file, new_file_path)
                    print(f"  ✓ 파일 저장: {new_file_path}")
                else:
                    print(f"  ✓ 파일 저장 완료: {new_file_path}")
                
            except Exception as e:
                print(f"  ⚠ 버튼 클릭 실패: {e}")
                import traceback
                traceback.print_exc()
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                return None
            
            # 이전 파일과 비교
            comparison_result = None
            if previous_file_path.exists():
                print(f"  → 이전 파일과 비교 중...")
                comparison_result = self.file_comparator.compare_and_report(
                    str(new_file_path),
                    str(previous_file_path),
                    save_diff=True
                )
                
                if comparison_result['changed']:
                    print(f"  ✓ 파일 변경 감지: {comparison_result['diff_summary']}")
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
                dates_info = self._extract_dates_from_iframe01(iframe01_soup)
                
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
                    
                    # 소관부서, 첨부파일, 날짜 정보를 soup에 추가 (나중에 extract_content_from_iframe에서 사용)
                    if department_info:
                        soup.department_info = department_info
                    if file_info:
                        soup.file_info = file_info
                    if dates_info:
                        soup.dates_info = dates_info
                    
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
                        # 소관부서, 첨부파일, 날짜 정보 추가
                        if department_info:
                            soup.department_info = department_info
                        if file_info:
                            soup.file_info = file_info
                        if dates_info:
                            soup.dates_info = dates_info
                        driver.switch_to.default_content()
                        return soup
                    else:
                        # iframe이 없으면 현재 iframe01의 내용 사용
                        soup = BeautifulSoup(driver.page_source, "lxml")
                        # 소관부서, 첨부파일, 날짜 정보 추가
                        if department_info:
                            soup.department_info = department_info
                        if file_info:
                            soup.file_info = file_info
                        if dates_info:
                            soup.dates_info = dates_info
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
    # iframe01에서 날짜 추출 (iframe01에 직접 있음)
    # ------------------------------------------------------------------
    def _extract_dates_from_iframe01(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        iframe01 내부에서 날짜(#his_sel) 추출
        """
        if soup is None:
            return None
        
        dates_info = {
            "enactment_date": "",
            "revision_date": "",
        }
        
        # #his_sel 요소 찾기
        his_sel = soup.select_one("#his_sel")
        if his_sel:
            # 모든 옵션 가져오기
            options = his_sel.select("option")
            if options:
                print(f"  디버깅: #his_sel에서 {len(options)}개 옵션 발견")
                for idx, opt in enumerate(options, 1):
                    opt_text = opt.get_text(strip=True)
                    opt_value = opt.get("value", "")
                    opt_selected = opt.get("selected")
                    print(f"    옵션 {idx}: '{opt_text}' (value: {opt_value}, selected: {opt_selected})")
                
                # 선택된 옵션 찾기 (selected 속성이 있거나 첫 번째 옵션)
                selected_option = None
                for opt in options:
                    if opt.get("selected") or opt.get("value") == his_sel.get("value"):
                        selected_option = opt
                        break
                # 선택된 옵션이 없으면 첫 번째 옵션 사용
                if not selected_option and options:
                    selected_option = options[0]
                
                # 옵션 개수에 따라 처리
                if len(options) == 1:
                    # 값이 하나라면 그게 제정일
                    date_text = options[0].get_text(strip=True)
                    dates_info["enactment_date"] = self._normalize_date_text(date_text)
                    print(f"  ✓ 제정일 추출: {dates_info['enactment_date']} (원본: '{date_text}')")
                elif len(options) > 1:
                    # 값이 여러개라면
                    # 가장 마지막 값이 제정일
                    last_option = options[-1]
                    last_date_text = last_option.get_text(strip=True)
                    dates_info["enactment_date"] = self._normalize_date_text(last_date_text)
                    print(f"  ✓ 제정일 추출 (마지막 옵션): {dates_info['enactment_date']} (원본: '{last_date_text}')")
                    
                    # 선택되어있는(또는 첫 번째) 값이 최근 개정일
                    if selected_option:
                        selected_date_text = selected_option.get_text(strip=True)
                        dates_info["revision_date"] = self._normalize_date_text(selected_date_text)
                        print(f"  ✓ 최근 개정일 추출 (선택된 옵션): {dates_info['revision_date']} (원본: '{selected_date_text}')")
            else:
                print(f"  ⚠ #his_sel에서 옵션을 찾지 못했습니다.")
        else:
            print(f"  ⚠ #his_sel 요소를 찾지 못했습니다.")
        
        return dates_info if dates_info["enactment_date"] or dates_info["revision_date"] else None
    
    # ------------------------------------------------------------------
    # iframe01에서 첨부파일 추출 (iframe01에 직접 있음)
    # ------------------------------------------------------------------
    def _extract_files_from_iframe01(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        iframe01 내부에서 첨부파일(#lawbtn) 정보 추출 (버튼 정보만, 링크는 저장하지 않음)
        - HWP 파일: #lawbtn > ul.btn > li:nth-child(3) > a
        - PDF 파일: #lawbtn > ul.btn > li:nth-child(4) > a
        """
        if soup is None:
            return None
        
        file_info = {
            "file_names": [],
            "file_types": [],  # 파일 타입 (hwp/pdf)
            "file_buttons": [],  # 버튼 선택자 정보
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

            # 버튼 선택자 생성 (iframe01 내부에서의 위치)
            button_selector = f"#lawbtn > ul.btn > li:nth-child({idx}) > a"
            
            file_info["file_names"].append(name)
            file_info["file_types"].append(file_type[1])
            file_info["file_buttons"].append(button_selector)
            print(f"  ✓ {file_type[0]} 파일 발견: {name}")

        if file_info["file_names"]:
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
            "file_types": [],  # 파일 타입 (hwp/pdf)
            "file_buttons": [],  # 버튼 선택자 정보
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
                # 개행 유지하면서 추출
                text = element.get_text(separator="\n", strip=True)
                if text and len(text) > 20:
                    # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                    text = text.replace("\r\n", "\n").replace("\r", "\n")
                    # 1000자 제한
                    if len(text) > 1000:
                        text = text[:1000]
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

        # 날짜 추출 - iframe01에서 추출한 정보 사용
        # soup 객체에 dates_info 속성이 있으면 사용 (iframe01에서 추출한 것)
        if hasattr(soup, 'dates_info') and soup.dates_info:
            if soup.dates_info.get("enactment_date"):
                info["enactment_date"] = soup.dates_info["enactment_date"]
            if soup.dates_info.get("revision_date"):
                info["revision_date"] = soup.dates_info["revision_date"]
            print(f"  ✓ 날짜 정보 추출 (iframe01에서): 제정일={info.get('enactment_date', '')}, 최근 개정일={info.get('revision_date', '')}")

        # 첨부파일 추출 - iframe01에서 추출한 정보 사용
        # soup 객체에 file_info 속성이 있으면 사용 (iframe01에서 추출한 것)
        if hasattr(soup, 'file_info') and soup.file_info:
            info["file_names"] = soup.file_info.get("file_names", [])
            info["file_types"] = soup.file_info.get("file_types", [])
            info["file_buttons"] = soup.file_info.get("file_buttons", [])
            if info["file_names"]:
                print(f"  ✓ 첨부파일 발견: {len(info['file_names'])}개 (iframe01에서)")
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
        content_limit: int = 0,
    ) -> List[Dict]:
        """
        법규정보시스템 스크래핑
        URL: https://law.kofia.or.kr/service/law/lawCurrentMain.do
        
        트리 구조에서 규정을 선택하여 스크래핑하는 방식
        
        Args:
            limit: 가져올 개수 제한 (0=전체)
            download_files: 파일 다운로드 여부
            content_limit: 본문 길이 제한 (0=제한 없음, 문자 수)
        """
        # 스크래퍼 시작 시 current를 previous로 백업 (이전 실행 결과를 이전 버전으로)
        self._backup_current_to_previous()
        # 이전 실행의 diff 파일 정리
        self._clear_diffs_directory()
        
        all_results: List[Dict] = []
        driver: Optional[webdriver.Chrome] = None

        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--lang=ko-KR")
            # Chrome 다운로드 디렉토리 설정 (current 디렉토리)
            prefs = {
                "download.default_directory": os.path.abspath(str(self.current_dir)),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True,  # PDF를 외부에서 열기
                "safebrowsing.enabled": True,
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.automatic_downloads": 1
            }
            chrome_options.add_experimental_option("prefs", prefs)
            # 폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용 (SeleniumManager 우회)
            driver = self._create_webdriver(chrome_options)
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

            missing_targets: List[str] = []
            if self.target_laws:
                tree_links, missing_targets = self._filter_tree_links_by_targets(tree_links)
                print(f"CSV 대상과 매칭된 규정: {len(tree_links)}개")
                if missing_targets:
                    print(f"⚠ CSV에 있으나 트리에서 찾지 못한 규정: {len(missing_targets)}개")
                    for name in missing_targets[:5]:
                        print(f"   - {name}")
                    if len(missing_targets) > 5:
                        print("   ...")
                    print(f"   (찾지 못한 항목은 결과에 빈 내용으로 포함됩니다)")

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
                display_name = item.get("target_name") or item.get("regulation_name") or item.get("title") or "N/A"
                print(f"[{idx}/{len(tree_links)}] {display_name[:50]}... 처리 중")

                # 트리 링크 클릭 및 콘텐츠 추출
                content_soup = self.click_tree_link_and_extract(driver, item)

                if content_soup:
                    # 디버그 HTML 저장 (첫 번째 페이지만)
                    self.save_debug_html(content_soup)

                    # 콘텐츠에서 정보 추출
                    content_info = self.extract_content_from_iframe(content_soup)
                    
                    # 본문 길이 제한 적용 (1000자로 제한, 개행 유지)
                    if content_info.get("content"):
                        content = content_info["content"]
                        # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                        content = content.replace("\r\n", "\n").replace("\r", "\n")
                        # 1000자 제한 (content_limit이 있으면 그것도 고려하되, 최대 1000자)
                        max_length = min(1000, content_limit) if content_limit > 0 else 1000
                        if len(content) > max_length:
                            original_length = len(content)
                            content = content[:max_length]
                            if original_length > max_length:
                                print(f"  ⚠ 본문 길이 제한 적용: {original_length}자 → {max_length}자")
                        content_info["content"] = content
                    
                    item.update(content_info)
                    
                    # 파일 다운로드 및 비교
                    if download_files and content_info.get("file_names"):
                        regulation_name = item.get("target_name") or item.get("regulation_name") or item.get("title", "")
                        file_names = content_info.get("file_names", [])
                        file_types = content_info.get("file_types", [])
                        file_buttons = content_info.get("file_buttons", [])
                        
                        # 여러 첨부파일 다운로드
                        for file_idx, (file_name, file_type, button_selector) in enumerate(zip(file_names, file_types, file_buttons)):
                            if button_selector:
                                print(f"  → 첨부파일 다운로드 중 [{file_idx + 1}/{len(file_names)}]: {file_name}")
                                comparison_result = self._download_file_by_clicking_button(
                                    driver,
                                    button_selector,
                                    file_name,
                                    file_type,
                                    regulation_name=regulation_name
                                )
                                if comparison_result:
                                    print(f"  ✓ 파일 다운로드 완료: {file_name}")
                                else:
                                    print(f"  ⚠ 파일 다운로드 실패: {file_name}")

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
                        # 본문이 없거나 짧은 경우에도 결과에 추가 (본문은 빈 문자열로 유지)
                        # 이렇게 하면 save_kofia_results에서 찾지 못한 항목과 구분 가능
                        all_results.append(item)
                        print(f"  ⚠ 본문 내용 없음 (디렉토리 또는 빈 페이지) - 빈 본문으로 저장")
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

    def _normalize_date_text(self, date_text: str) -> str:
        """
        날짜 텍스트를 정규화된 형식으로 변환
        예: "2008. 12. 30" -> "2008-12-30"
        """
        import re
        
        if not date_text:
            return ""
        
        # 공백 제거 및 정규화
        cleaned = re.sub(r"[년월일]", ".", date_text)
        cleaned = cleaned.replace(" ", "").replace("-", ".")
        cleaned = cleaned.strip(".")
        
        # 날짜 부분 추출 (숫자와 점만)
        parts = [p for p in cleaned.split(".") if p and p.isdigit()]
        if len(parts) >= 3:
            # YYYY-MM-DD 형식으로 변환
            year = parts[0]
            month = str(int(parts[1])).zfill(2)  # 월을 2자리로 (01, 02, ...)
            day = str(int(parts[2])).zfill(2)  # 일을 2자리로 (01, 02, ...)
            return f"{year}-{month}-{day}"
        elif len(parts) >= 2:
            # YYYY-MM 형식
            year = parts[0]
            month = str(int(parts[1])).zfill(2)
            return f"{year}-{month}"
        elif len(parts) >= 1:
            # YYYY 형식
            return parts[0]
        
        return cleaned


def save_kofia_results(records: List[Dict], crawler: Optional[KofiaScraper] = None):
    """JSON 및 CSV로 금융투자협회 법규정보 데이터를 저장한다.
    
    Args:
        records: 스크래핑된 법규정보 리스트
        crawler: KofiaScraper 인스턴스 (CSV의 모든 항목을 포함하기 위해 사용)
    """
    import json
    import csv

    # CSV의 모든 항목을 포함하도록 정렬 (CSV 순서 유지)
    if crawler and crawler.target_laws:
        # CSV 항목 순서대로 정렬하기 위한 딕셔너리 생성
        records_dict = {}
        for item in records:
            # target_name을 우선적으로 사용, 없으면 regulation_name, title 순서로 확인
            reg_name = item.get("target_name") or item.get("regulation_name") or item.get("title", "")
            if reg_name:
                records_dict[reg_name] = item
        
        print(f"디버깅: records_dict에 {len(records_dict)}개 항목이 있습니다.")
        print(f"디버깅: CSV에는 {len(crawler.target_laws)}개 항목이 있습니다.")
        
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
                    "organization": "금융투자협회",
                    "target_name": target_name,
                    "target_category": target.get("category", ""),
                    "content": "",  # 빈 본문
                    "department": "",
                    "file_names": [],
                    "enactment_date": "",
                    "revision_date": "",
                }
                ordered_records.append(empty_item)
                print(f"디버깅: 찾지 못한 항목 추가 - {target_name}")
        
        if missing_count > 0:
            print(f"디버깅: 총 {missing_count}개 항목을 빈 본문으로 추가했습니다.")
        
        records = ordered_records

    if not records:
        print("저장할 법규정보 데이터가 없습니다.")
        return

    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    for item in records:
        # 여러 첨부파일 처리
        file_names = item.get("file_names", [])
        
        # 하위 호환성: 기존 file_name도 확인
        if not file_names and item.get("file_name"):
            file_names = [item.get("file_name")]
        
        # 여러 첨부파일을 세미콜론으로 구분하여 저장
        file_names_str = "; ".join(file_names) if file_names else ""
        
        law_item = {
            "규정명": item.get("regulation_name", item.get("title", "")),
            "기관명": item.get("organization", "금융투자협회"),
            "본문": item.get("content", ""),
            "제정일": item.get("enactment_date", ""),
            "최근 개정일": item.get("revision_date", ""),
            "소관부서": item.get("department", ""),
            "첨부파일이름": file_names_str,
        }
        law_results.append(law_item)
    
    # JSON 저장 (한글 필드명으로) - output/json 디렉토리에 저장
    json_dir = os.path.join("output", "json")
    os.makedirs(json_dir, exist_ok=True)

    json_path = os.path.join(json_dir, "kofia_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": KofiaScraper.LIST_URL,
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
        "첨부파일이름",
    ]
    # CSV 저장 - output/csv 디렉토리에 저장
    csv_dir = os.path.join("output", "csv")
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "kofia_scraper.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for law_item in law_results:
            # 본문 내용 처리 (개행 유지, 1000자 제한)
            content = law_item.get("본문", "") or ""
            # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            if len(content) > 1000:
                content = content[:1000]
            
            csv_item = law_item.copy()
            csv_item["본문"] = content
            writer.writerow(csv_item)
    print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="금융투자협회 법규정보시스템 스크래퍼")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="대상 규정 목록 CSV 경로 (기본: KOFIA_Scraper/input/list.csv)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="파일 다운로드를 건너뜁니다.",
    )
    parser.add_argument(
        "--content",
        type=int,
        default=0,
        help="본문 길이 제한 (0=제한 없음, 문자 수)",
    )
    args = parser.parse_args()

    crawler = KofiaScraper(csv_path=args.csv)
    results = crawler.crawl_law_info(
        limit=args.limit,
        download_files=not args.no_download,
        content_limit=args.content,
    )

    print(f"\n총 {len(results)}개의 법규정보를 수집했습니다.")
    save_kofia_results(results, crawler=crawler)
