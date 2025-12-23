"""
한국거래소 스크래퍼
"""
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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

from common.base_scraper import BaseScraper  # noqa: E402  pylint: disable=wrong-import-position
from common.file_comparator import FileComparator  # noqa: E402  pylint: disable=wrong-import-position


class KrxScraper(BaseScraper):
    """한국거래소 - KRX법무포탈 스크래퍼"""
    
    BASE_URL = "https://rule.krx.co.kr"
    MAIN_URL = f"{BASE_URL}/out/index.do"
    SEARCH_URL = f"{BASE_URL}/web/search.do"
    RELATIVE_LIST_PATH = Path("input") / "list.csv"
    JSON_FILENAME = "krx_scraper.json"
    CSV_FILENAME = "krx_scraper.csv"
    
    def __init__(self, delay: float = 1.0, content_all: bool = False):
        super().__init__(delay)
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        (self.output_dir / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "csv").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "downloads").mkdir(parents=True, exist_ok=True)
        # previous와 current 디렉토리 설정
        self.previous_dir = self.output_dir / "downloads" / "previous"
        self.current_dir = self.output_dir / "downloads" / "current"
        self.previous_dir.mkdir(parents=True, exist_ok=True)
        self.current_dir.mkdir(parents=True, exist_ok=True)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=str(self.output_dir / "downloads"))
        # 본문 전체 가져오기 플래그
        self.content_all = content_all
    
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
    
    def _find_previous_file(self, file_name: str) -> Optional[Path]:
        """previous 디렉토리에서 같은 파일명의 파일 찾기
        Args:
            file_name: 찾을 파일명
        Returns:
            이전 파일 경로 또는 None
        """
        previous_file = self.previous_dir / file_name
        if previous_file.exists():
            return previous_file
        return None
    
    def crawl_krx_legal_portal(self) -> List[Dict]:
        """
        KRX법무포탈 스크래핑
        URL: https://rule.krx.co.kr/out/index.do
        """
        # 스크래퍼 시작 시 current를 previous로 백업 (이전 실행 결과를 이전 버전으로)
        self._backup_current_to_previous()
        # 이전 실행의 diff 파일 정리
        self._clear_diffs_directory()
        
        keywords = self._load_filter_keywords()
        if not keywords:
            print("⚠ 필터링할 키워드가 없습니다. CSV 파일을 확인해주세요.")
            return []
        
        # Chrome 옵션에 다운로드 디렉토리 설정 (current 디렉토리)
        chrome_options = self._build_default_chrome_options()
        download_dir = str(self.current_dir)
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,  # PDF를 외부에서 열기
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        driver = self._create_webdriver(chrome_options)
        wait = WebDriverWait(driver, 15)
        results: List[Dict] = []
        
        try:
            for keyword in keywords:
                keyword_results = self._search_keyword_and_collect(driver, wait, keyword)
                results.extend(keyword_results)
        finally:
            driver.quit()
        
        # 번호를 순차적으로 재매기기
        for idx, record in enumerate(results, start=1):
            record["번호"] = str(idx)
        
        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta = {
            "url": self.MAIN_URL,
            "crawled_at": crawled_at,
            "keyword_count": len(keywords),
            "result_count": len(results),
        }
        self._save_outputs(results, meta)
        return results
    
    def _load_filter_keywords(self) -> List[str]:
        """input/list.csv에서 규정명을 읽어 필터 키워드 목록을 작성"""
        csv_path = self.base_dir / self.RELATIVE_LIST_PATH
        if not csv_path.exists():
            print(f"⚠ 필터 CSV 파일이 존재하지 않습니다: {csv_path}")
            return []
        
        keywords = []
        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            if "법령명" not in reader.fieldnames:
                print("⚠ CSV 파일에 '법령명' 컬럼이 필요합니다.")
                return []
            for row in reader:
                keyword = (row.get("법령명") or "").strip()
                if keyword:
                    keywords.append(keyword)
        print(f"CSV에서 {len(keywords)}개의 키워드를 불러왔습니다.")
        return keywords
    
    def _open_main_page(self, driver, wait) -> None:
        """메인 페이지 진입"""
        driver.get(self.MAIN_URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#mainSchTxt")))
        print("메인 페이지 진입 완료")
    
    def _perform_search(self, driver, wait, keyword: str) -> None:
        """메인 검색창에 키워드 입력 후 결과 페이지로 이동"""
        self._open_main_page(driver, wait)
        main_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#mainSchTxt")))
        main_input.clear()
        main_input.send_keys(keyword)
        
        current_handle = driver.current_window_handle
        existing_handles = set(driver.window_handles)
        try:
            search_button = driver.find_element(By.CSS_SELECTOR, "#mainSchBtn")
            # 요소가 가려져 있을 수 있으므로 JavaScript 클릭 시도
            try:
                search_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", search_button)
        except NoSuchElementException:
            # 버튼이 없으면 ENTER 키 사용
            main_input.send_keys(Keys.ENTER)
        
        # 검색 결과 페이지 로딩 대기 (동일 창 또는 새 창)
        try:
            wait.until(lambda d: "search.do" in d.current_url)
        except TimeoutException:
            try:
                WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > len(existing_handles))
                new_handle = next(h for h in driver.window_handles if h not in existing_handles)
                driver.switch_to.window(new_handle)
            except Exception:
                raise
        
        if "search.do" not in driver.current_url:
            wait.until(lambda d: "search.do" in d.current_url)
        
        print("검색 결과 페이지 진입 완료")
        self._switch_to_results_frame(driver, wait)
    
    def _switch_to_results_frame(self, driver, wait) -> None:
        """검색 결과가 담긴 iframe으로 전환"""
        try:
            driver.switch_to.default_content()
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "workPage")))
        except Exception as e:
            print(f"  ⚠ iframe 전환 실패: {e}")
            # 예외 발생 시에도 계속 진행
    
    def _search_keyword_and_collect(self, driver, wait, keyword: str) -> List[Dict]:
        """키워드 검색 후 목록을 추출"""
        print(f"\n▶ 검색 키워드: {keyword}")
        results: List[Dict] = []
        
        # 메인 페이지에서 검색 수행 후 결과 페이지에서 후속 처리
        self._perform_search(driver, wait, keyword)

        # iframe 내부로 전환해 결과 테이블 접근
        self._switch_to_results_frame(driver, wait)

        # 검색 결과 로딩 대기
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#law_rule li dl")))
        entries = driver.find_elements(By.CSS_SELECTOR, "#law_rule li dl")
        if not entries:
            print(" - 검색 결과 없음")
            return results
        
        # 첫 번째 항목만 처리
        try:
            entry = entries[0]
            title_el = entry.find_element(By.CSS_SELECTOR, "dt")
            title_text = title_el.text.strip()
            onclick = title_el.get_attribute("onclick") or ""
            book_id = self._parse_book_id(onclick)
            
            meta_spans = entry.find_elements(By.CSS_SELECTOR, "dd span")
            doc_type = meta_spans[0].text.strip() if len(meta_spans) > 0 else ""
            revised_date_raw = meta_spans[1].text.strip() if len(meta_spans) > 1 else ""
            department = meta_spans[2].text.strip() if len(meta_spans) > 2 else ""
            
            # 날짜 포맷팅
            revised_date = self._format_date(revised_date_raw)
            
            # 클릭 전 창 핸들 저장 (iframe 컨텍스트에서)
            current_handles_before = set(driver.window_handles)
            
            # onclick 속성에서 goToView 함수 파라미터 추출 (이미 위에서 읽음)
            print(f"  → onclick 속성: {onclick}")
            
            # goToView 함수 직접 호출 시도
            if "goToView" in onclick:
                # goToView('rule', '210025251', 'N') 형태에서 파라미터 추출
                import re
                matches = re.findall(r"goToView\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", onclick)
                if matches:
                    gbn, pk1, pk2 = matches[0]
                    print(f"  → goToView 호출: gbn={gbn}, pk1={pk1}, pk2={pk2}")
                    # JavaScript로 goToView 함수 직접 호출
                    driver.execute_script(f"goToView('{gbn}', '{pk1}', '{pk2}');")
                else:
                    # 정규식으로 파싱 실패 시 onclick 직접 실행
                    driver.execute_script(onclick)
            else:
                # onclick이 없으면 일반 클릭
                driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
                try:
                    title_el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", title_el)
            
            # 클릭 후 잠시 대기 (새 창이 열릴 시간)
            time.sleep(3)
            
            # iframe에서 나와서 새 창 확인
            driver.switch_to.default_content()
            detail_text, download_link, file_name, revision_reason, promulgation_date, enforcement_date, revision_content = self._extract_detail(driver, wait, current_handles_before, keyword)
            
            # KFB_Scraper와 동일한 컬럼 구조로 매핑
            record = {
                "번호": "",  # 나중에 순차적으로 재매기기됨
                "규정명": title_text,
                "기관명": "한국거래소",
                "본문": detail_text,
                "제정일": "",  # KRX에서는 제정일 정보가 별도로 제공되지 않음
                "최근 개정일": revised_date,
                "소관부서": department,
                "개정이유": revision_reason,
                "개정내용": revision_content,
                "공포일": promulgation_date,
                "시행일": enforcement_date,
                "파일 다운로드 링크": download_link,
                "파일 이름": file_name,
            }
            print(f" - [0] {record['규정명']} (제·개정 {doc_type})")
            results.append(record)
        except Exception as exc:
            print(f"  ⚠ 첫 번째 항목 처리 중 오류 발생: {exc}")
        finally:
            # 상세 팝업 후 iframe 컨텍스트 복원 (안전하게 처리)
            try:
                # 유효한 창이 있는지 확인
                if driver.window_handles:
                    # 첫 번째 창으로 전환
                    driver.switch_to.window(driver.window_handles[0])
                    self._switch_to_results_frame(driver, wait)
            except Exception as e:
                print(f"  ⚠ iframe 컨텍스트 복원 실패: {e}")
        return results

    def _extract_detail(self, driver, wait, existing_handles: set = None, keyword: str = "") -> Tuple[str, str, str, str, str, str, str]:
        """상세 페이지(새 창)에서 내용, 다운로드 링크, 파일 이름, 개정이유, 공포일, 시행일, 개정내용 추출
        Args:
            driver: WebDriver 인스턴스
            wait: WebDriverWait 인스턴스
            existing_handles: 클릭 전 창 핸들 집합 (None이면 현재 창 핸들 사용)
            keyword: 검색 키워드 (파일명으로 사용)
        Returns:
            (본문 내용, 다운로드 링크, 파일 이름, 개정이유, 공포일, 시행일, 개정내용) 튜플
        """
        current_handle = driver.current_window_handle
        if existing_handles is None:
            existing_handles = set(driver.window_handles)
        content = "상세 내용 없음"
        download_link = ""
        file_name = ""
        revision_reason = ""
        promulgation_date = ""
        enforcement_date = ""
        revision_content = ""
        
        # 새 창이 열릴 때까지 대기 (최대 15초)
        try:
            print(f"  → 클릭 전 창 핸들 수: {len(existing_handles)}")
            print(f"  → 현재 창 핸들 수: {len(driver.window_handles)}")
            print(f"  → 새 창 대기 중...")
            WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > len(existing_handles))
            print(f"  → 새 창 감지됨! 현재 창 핸들 수: {len(driver.window_handles)}")
            new_handles = [h for h in driver.window_handles if h not in existing_handles]
            if new_handles:
                new_handle = new_handles[0]
                driver.switch_to.window(new_handle)
                print(f"  → 새 창으로 전환: {driver.current_url}")
                
                # 페이지 로딩 대기
                time.sleep(3)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # #regulCont 요소가 로드될 때까지 대기
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#regulCont")))
                    print("  → #regulCont 요소 발견")
                except TimeoutException:
                    print("  ⚠ #regulCont 요소를 찾지 못함, 다른 선택자 시도")
                
                # 본문 내용 추출 (#regulCont 우선)
                selectors = [
                    (By.CSS_SELECTOR, "#regulCont"),  # 상세 내용의 주요 컨테이너
                    (By.XPATH, '//*[@id="regulCont"]'),  # xpath로도 시도
                ]
                
                for selector_type, selector_value in selectors:
                    try:
                        element = driver.find_element(selector_type, selector_value)
                        content = element.text.strip()
                        if content and len(content) > 50:
                            print(f"  → 본문 추출 성공 ({len(content)}자)")
                            break
                    except Exception as e:
                        continue
                
                if not content or len(content) < 50:
                    # 폴백: body 전체 텍스트
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
                        content = body_text if body_text else "상세 내용 없음"
                        print(f"  → body 텍스트로 폴백 ({len(content)}자)")
                    except Exception:
                        content = "상세 내용 없음"
                
                # 파일 다운로드 링크 및 파일 이름 추출 (#webprint 처리)
                try:
                    # #webprint 요소 찾기
                    webprint_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#webprint")))
                    webprint_href = webprint_elem.get_attribute("href") or ""
                    webprint_onclick = webprint_elem.get_attribute("onclick") or ""
                    
                    print(f"  → #webprint 발견: href={webprint_href[:50] if webprint_href else 'None'}, onclick={webprint_onclick[:50] if webprint_onclick else 'None'}")
                    
                    # 파일 이름은 키워드로 설정 (확장자 추가)
                    if keyword:
                        # 키워드에서 파일명으로 사용할 수 없는 문자 제거
                        safe_keyword = re.sub(r'[<>:"/\\|?*]', '_', keyword)
                        file_name = f"{safe_keyword}.pdf"
                    else:
                        file_name = "download.pdf"
                    
                    # #webprint 클릭 전 창 핸들 저장
                    print_handles_before = set(driver.window_handles)
                    
                    # #webprint 클릭 (새 창으로 프린트 팝업 열림)
                    try:
                        webprint_elem.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", webprint_elem)
                    
                    # 새 창이 열릴 때까지 대기
                    time.sleep(2)
                    try:
                        WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > len(print_handles_before))
                        print_handles = [h for h in driver.window_handles if h not in print_handles_before]
                        if print_handles:
                            print_handle = print_handles[0]
                            driver.switch_to.window(print_handle)
                            print(f"  → 프린트 팝업 창으로 전환: {driver.current_url}")
                            
                            # 프린트 팝업 창의 URL
                            print_url = driver.current_url
                            download_link = print_url
                            
                            # 페이지 로딩 대기
                            time.sleep(2)
                            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                            
                            # 프린트 팝업 URL에서 PDF 직접 다운로드
                            print(f"  → PDF 다운로드 시작: {print_url}")
                            downloaded_path = self._download_pdf_from_print_url(driver, print_url, file_name)
                            
                            # 프린트 팝업 창 닫기
                            driver.close()
                            
                            # 상세 페이지 창(new_handle)으로 돌아가기
                            try:
                                if new_handle in driver.window_handles:
                                    driver.switch_to.window(new_handle)
                                elif driver.window_handles:
                                    driver.switch_to.window(driver.window_handles[0])
                            except Exception as e:
                                print(f"  ⚠ 상세 페이지 창으로 전환 실패: {e}")
                                if driver.window_handles:
                                    driver.switch_to.window(driver.window_handles[0])
                            
                            print(f"  → 다운로드 링크 설정: {download_link}")
                            print(f"  → 파일 이름: {file_name}")
                            if downloaded_path:
                                print(f"  → 다운로드된 파일 경로: {downloaded_path}")
                            else:
                                print(f"  ⚠ PDF 다운로드 실패")
                        else:
                            # 새 창이 열리지 않았으면 원래 창의 URL 사용
                            download_link = driver.current_url
                            print(f"  → 새 창이 열리지 않음, 현재 URL 사용: {download_link}")
                    except TimeoutException:
                        # 타임아웃 시 원래 창의 URL 사용
                        download_link = driver.current_url
                        print(f"  → 타임아웃, 현재 URL 사용: {download_link}")
                    
                except NoSuchElementException:
                    print("  ⚠ #webprint 요소를 찾지 못함")
                    download_link = driver.current_url
                    if keyword:
                        safe_keyword = re.sub(r'[<>:"/\\|?*]', '_', keyword)
                        file_name = f"{safe_keyword}.pdf"
                    else:
                        file_name = "download.pdf"
                except Exception as e:
                    print(f"  ⚠ 다운로드 링크 추출 실패: {e}")
                    download_link = driver.current_url
                    if keyword:
                        safe_keyword = re.sub(r'[<>:"/\\|?*]', '_', keyword)
                        file_name = f"{safe_keyword}.pdf"
                    else:
                        file_name = "download.pdf"
                
                # 개정이유 버튼 클릭 및 파일 다운로드
                try:
                    print(f"  → 개정이유 버튼 찾는 중...")
                    # 상세 페이지 창(new_handle)이 활성화되어 있는지 확인
                    if driver.current_window_handle != new_handle:
                        if new_handle in driver.window_handles:
                            driver.switch_to.window(new_handle)
                    
                    # 개정이유 버튼 찾기
                    revision_button = None
                    try:
                        revision_button = driver.find_element(By.CSS_SELECTOR, "body > div.funGroup > div.funRight > a:nth-child(5)")
                        print(f"  ✓ 개정이유 버튼 발견")
                    except NoSuchElementException:
                        # 대체 선택자 시도
                        try:
                            revision_button = driver.find_element(By.XPATH, "//body//div[@class='funGroup']//div[@class='funRight']//a[5]")
                            print(f"  ✓ 개정이유 버튼 발견 (XPath)")
                        except:
                            print(f"  ⚠ 개정이유 버튼을 찾을 수 없음")
                    
                    # 파일 변경이 감지된 경우에만 개정이유 추출
                    # comparison_result는 _extract_detail 호출 전에 확인할 수 없으므로,
                    # 여기서는 항상 추출하고, 나중에 비교 결과에 따라 필터링하는 대신
                    # 비교 결과를 먼저 확인할 수 있도록 구조 변경 필요
                    # 하지만 현재 구조상 _extract_detail 내부에서 비교를 수행하므로
                    # 비교 결과를 확인하기 어려움. 대신 파일 다운로드 후 비교 결과를 확인하여
                    # 조건부로 개정이유 추출하도록 수정
                    
                    # 비교 결과 확인 (파일 다운로드가 이미 완료된 경우)
                    # comparison_result는 _extract_detail의 지역 변수이므로
                    # 여기서는 파일 다운로드 후 비교를 수행하고 결과에 따라 추출
                    should_extract_revision = True  # 기본값은 True (새 파일이거나 변경 감지)
                    
                    if revision_button:
                        # 버튼 클릭 전 다운로드 디렉토리 파일 목록 확인
                        files_before = set(self.current_dir.glob("*"))
                        
                        # 버튼 클릭
                        try:
                            print(f"  → 개정이유 버튼 클릭 중...")
                            driver.execute_script("arguments[0].scrollIntoView(true);", revision_button)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", revision_button)
                            time.sleep(3)  # 파일 다운로드 대기
                            print(f"  ✓ 버튼 클릭 완료")
                        except Exception as e:
                            print(f"  ⚠ 버튼 클릭 실패: {e}")
                            try:
                                revision_button.click()
                                time.sleep(3)
                            except:
                                pass
                        
                        # 다운로드된 파일 찾기
                        files_after = set(self.current_dir.glob("*"))
                        new_files = files_after - files_before
                        
                        if new_files:
                            # 가장 최근 파일 선택
                            downloaded_file = max(new_files, key=lambda p: p.stat().st_mtime if p.is_file() else 0)
                            if downloaded_file.is_file():
                                print(f"  → 다운로드된 파일 발견: {downloaded_file.name}")
                                
                                # 파일 다운로드 후 비교 수행
                                comparison_result_revision = self._compare_with_previous_file(str(downloaded_file), downloaded_file.name)
                                
                                # 비교 결과에 따라 개정이유 추출 여부 결정
                                if comparison_result_revision:
                                    should_extract_revision = comparison_result_revision.get('changed', True)
                                else:
                                    should_extract_revision = True  # 비교 실패 시 추출
                                
                                if should_extract_revision:
                                    # 파일 내용 추출
                                    from common.file_extractor import FileExtractor
                                    file_extractor = FileExtractor(download_dir=str(self.current_dir))
                                    
                                    file_ext = downloaded_file.suffix.lower()
                                    if file_ext == '.pdf':
                                        file_content = file_extractor.extract_pdf_content(str(downloaded_file))
                                    elif file_ext in ['.hwp', '.hwpx']:
                                        file_content = file_extractor.extract_hwp_content(str(downloaded_file))
                                    else:
                                        # 기타 파일 형식 시도
                                        file_content = file_extractor.extract_hwp_content(str(downloaded_file))
                                    
                                    if file_content:
                                        print(f"  → 파일 내용 추출 완료 ({len(file_content)}자)")
                                        
                                        # 개정이유, 공포일, 시행일, 개정내용 추출
                                        revision_info = self._extract_revision_info_from_content(file_content)
                                        revision_reason = revision_info.get('revision_reason', '')
                                        promulgation_date = revision_info.get('promulgation_date', '')
                                        enforcement_date = revision_info.get('enforcement_date', '')
                                        revision_content = revision_info.get('revision_content', '')
                                        
                                        print(f"  ✓ 개정이유: {len(revision_reason)}자, 개정내용: {len(revision_content)}자, 공포일: {promulgation_date}, 시행일: {enforcement_date}")
                                    else:
                                        print(f"  ⚠ 파일 내용 추출 실패")
                                else:
                                    print(f"  → 파일 변경 없음, 개정이유/개정내용 추출 스킵")
                                    revision_reason = ""
                                    revision_content = ""
                        else:
                            print(f"  ⚠ 다운로드된 파일을 찾을 수 없음")
                except Exception as e:
                    print(f"  ⚠ 개정이유 추출 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                
                # 상세 페이지 창(new_handle) 닫기
                try:
                    # 현재 상세 페이지 창이 활성화되어 있는지 확인
                    if driver.current_window_handle == new_handle:
                        driver.close()
                    elif new_handle in driver.window_handles:
                        driver.switch_to.window(new_handle)
                        driver.close()
                except Exception as e:
                    print(f"  ⚠ 상세 페이지 창 닫기 실패: {e}")
                
                # 원래 창(current_handle)으로 안전하게 전환
                try:
                    if current_handle in driver.window_handles:
                        driver.switch_to.window(current_handle)
                    elif driver.window_handles:
                        # current_handle이 없으면 첫 번째 창으로 전환
                        driver.switch_to.window(driver.window_handles[0])
                except Exception as e:
                    print(f"  ⚠ 원래 창으로 전환 실패: {e}")
                    if driver.window_handles:
                        driver.switch_to.window(driver.window_handles[0])
                
                return (content, download_link, file_name, revision_reason, promulgation_date, enforcement_date, revision_content)
        except TimeoutException:
            print("  ⚠ 새 창이 열리지 않음 (타임아웃)")
        except Exception as exc:
            print(f"  ⚠ 상세 내용 추출 중 오류: {exc}")
        
        # 예외 발생 시 원래 창으로 복귀 시도
        try:
            if current_handle in driver.window_handles:
                driver.switch_to.window(current_handle)
            elif driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        except Exception as e:
            print(f"  ⚠ 창 복귀 실패: {e}")
        
        return (content, download_link, file_name, revision_reason, promulgation_date, enforcement_date, revision_content)
    
    def _download_pdf_from_print_url(self, driver, print_url: str, file_name: str) -> str:
        """프린트 팝업 URL에서 PDF 파일 다운로드 (Chrome print-to-pdf 사용)
        Args:
            driver: WebDriver 인스턴스
            print_url: 프린트 팝업 URL
            file_name: 저장할 파일명
        Returns:
            다운로드된 파일 경로
        """
        try:
            # current 디렉토리에 저장
            download_path = self.current_dir / file_name
            
            # Chrome print-to-pdf 기능 활용
            print(f"  → Chrome print-to-pdf 기능으로 PDF 생성 중...")
            pdf_data = driver.execute_cdp_cmd('Page.printToPDF', {
                'printBackground': True,
                'paperWidth': 8.27,  # A4 width in inches
                'paperHeight': 11.69,  # A4 height in inches
                'marginTop': 0,
                'marginBottom': 0,
                'marginLeft': 0,
                'marginRight': 0,
            })
            
            if pdf_data and 'data' in pdf_data:
                import base64
                pdf_bytes = base64.b64decode(pdf_data['data'])
                with open(download_path, 'wb') as f:
                    f.write(pdf_bytes)
                
                file_size = download_path.stat().st_size
                if file_size > 0:
                    print(f"  → PDF 생성 완료: {download_path} ({file_size} bytes)")
                    
                    # 이전 파일과 비교
                    self._compare_with_previous_file(str(download_path), file_name)
                    
                    return str(download_path)
            
            print(f"  ⚠ PDF 생성 실패")
            return ""
            
        except Exception as e:
            print(f"  ⚠ PDF 다운로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _compare_with_previous_file(self, new_file_path: str, file_name: str) -> Optional[Dict]:
        """다운로드한 파일을 이전 파일과 비교
        Args:
            new_file_path: 새로 다운로드한 파일 경로
            file_name: 파일명
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            previous_file = self._find_previous_file(file_name)
            
            if not previous_file:
                print(f"  ✓ 새 파일 (이전 파일 없음)")
                # 새 파일은 변경으로 간주
                return {'changed': True, 'new_exists': True, 'old_exists': False}
            
            print(f"  → 이전 파일과 비교 중... (이전 파일: {previous_file})")
            comparison_result = self.file_comparator.compare_and_report(
                new_file_path,
                str(previous_file),
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
            
            return comparison_result
                
        except Exception as e:
            print(f"  ⚠ 파일 비교 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _download_file(self, driver, download_url: str, file_name: str) -> str:
        """프린트 팝업 URL을 사용해서 PDF 파일 다운로드
        Args:
            driver: WebDriver 인스턴스
            download_url: 다운로드할 URL
            file_name: 저장할 파일명
        Returns:
            다운로드된 파일 경로
        """
        try:
            # Selenium 쿠키를 requests 세션에 전달
            cookies = driver.get_cookies()
            session = self.session
            
            # 쿠키 설정
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
            
            # current 디렉토리에 저장
            download_path = self.current_dir / file_name
            
            # 파일 다운로드 (헤더 설정)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Referer': download_url,
            }
            response = session.get(download_url, headers=headers, timeout=30, verify=False, stream=True)
            response.raise_for_status()
            
            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '').lower()
            print(f"  → Content-Type: {content_type}")
            
            # 파일 저장
            with open(download_path, 'wb') as f:
                first_chunk = True
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        # 첫 번째 청크에서 PDF 시그니처 확인
                        if first_chunk:
                            if chunk[:4] != b'%PDF':
                                print(f"  ⚠ PDF 파일이 아닌 것으로 보입니다. HTML일 수 있습니다.")
                            first_chunk = False
                        f.write(chunk)
            
            file_size = download_path.stat().st_size
            if file_size > 0:
                print(f"  → 파일 다운로드 완료: {download_path} ({file_size} bytes)")
                return str(download_path)
            else:
                print(f"  ⚠ 다운로드된 파일 크기가 0입니다.")
                try:
                    download_path.unlink()  # 빈 파일 삭제
                except Exception:
                    pass
                return ""
        except Exception as e:
            print(f"  ⚠ 파일 다운로드 실패: {e}")
            return ""
    
    def _parse_book_id(self, onclick_value: str) -> str:
        """onclick 문자열에서 규정 식별자(bookid) 추출"""
        try:
            matches = re.findall(r"'([^']+)'", onclick_value)
            if len(matches) >= 2:
                return matches[1]
        except Exception:
            pass
        return ""
    
    def _format_date(self, date_str: str) -> str:
        """날짜 문자열을 yyyy-mm-dd 형태로 변환"""
        if not date_str or not date_str.strip():
            return ""
        
        date_str = date_str.strip()
        # yyyymmdd 형태 (예: 20250205)를 yyyy-mm-dd로 변환
        if re.match(r'^\d{8}$', date_str):
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # 이미 yyyy-mm-dd 형태인 경우 그대로 반환
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # 다른 형태의 날짜는 그대로 반환 (추가 파싱 필요 시 확장 가능)
        return date_str
    
    def _extract_revision_info_from_content(self, content: str) -> Dict[str, str]:
        """파일 내용에서 개정이유, 공포일, 시행일, 개정내용 추출
        Args:
            content: 파일에서 추출한 텍스트 내용
        Returns:
            {'revision_reason': str, 'promulgation_date': str, 'enforcement_date': str, 'revision_content': str} 딕셔너리
        """
        revision_reason = ""
        promulgation_date = ""
        enforcement_date = ""
        revision_content = ""
        
        if not content:
            return {
                'revision_reason': revision_reason,
                'promulgation_date': promulgation_date,
                'enforcement_date': enforcement_date,
                'revision_content': revision_content
            }
        
        # 파일 내용을 라인별로 분석
        lines = content.split('\n')
        
        # 공포일 추출 (공포일, 공포, 개정일 등 키워드와 함께)
        promulgation_keywords = ['공포일', '공포', '개정일']
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            for keyword in promulgation_keywords:
                if keyword in line_stripped:
                    # 키워드가 포함된 라인에서 날짜 찾기
                    date_patterns = [
                        r'(\d{4})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})',  # YYYY.MM.DD 또는 YYYY-MM-DD
                        r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일',  # YYYY년 MM월 DD일
                        r'(\d{4})(\d{2})(\d{2})',  # YYYYMMDD
                    ]
                    
                    for pattern in date_patterns:
                        match = re.search(pattern, line_stripped)
                        if match:
                            if len(match.groups()) >= 3:
                                year = match.group(1)
                                month = match.group(2).zfill(2)
                                day = match.group(3).zfill(2)
                                promulgation_date = f"{year}-{month}-{day}"
                                print(f"  → 공포일 추출: {promulgation_date} (라인: {line_stripped[:50]}...)")
                                break
                    if promulgation_date:
                        break
            if promulgation_date:
                break
        
        # 시행일 추출 (시행일, 시행 등 키워드와 함께)
        enforcement_keywords = ['시행일', '시행']
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            for keyword in enforcement_keywords:
                if keyword in line_stripped:
                    # 키워드가 포함된 라인에서 날짜 찾기
                    date_patterns = [
                        r'(\d{4})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})',  # YYYY.MM.DD 또는 YYYY-MM-DD
                        r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일',  # YYYY년 MM월 DD일
                        r'(\d{4})(\d{2})(\d{2})',  # YYYYMMDD
                    ]
                    
                    for pattern in date_patterns:
                        match = re.search(pattern, line_stripped)
                        if match:
                            if len(match.groups()) >= 3:
                                year = match.group(1)
                                month = match.group(2).zfill(2)
                                day = match.group(3).zfill(2)
                                enforcement_date = f"{year}-{month}-{day}"
                                print(f"  → 시행일 추출: {enforcement_date} (라인: {line_stripped[:50]}...)")
                                break
                    if enforcement_date:
                        break
            if enforcement_date:
                break
        
        # 개정이유 추출 (개정이유, 개정사유 등 섹션에서 추출)
        revision_keywords = ['개정이유', '개정사유', '개정 이유', '개정 사유', '제정·개정이유', '제정개정이유', '개정이유서']
        revision_start_idx = -1
        
        # 개정이유 섹션 시작 위치 찾기
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            for keyword in revision_keywords:
                if keyword in line_stripped:
                    revision_start_idx = i
                    print(f"  → 개정이유 섹션 발견 (라인 {i+1}): {line_stripped[:50]}...")
                    break
            if revision_start_idx >= 0:
                break
        
        # '2. 주요내용' 섹션 시작 위치 찾기
        main_content_start_idx = -1
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            # '2. 주요내용', '2 주요내용', '주요내용' 등 패턴 확인
            if re.match(r'^2[.\s]*주요내용', line_stripped) or (line_stripped.startswith('주요내용') and i > revision_start_idx):
                main_content_start_idx = i
                print(f"  → 주요내용 섹션 발견 (라인 {i+1}): {line_stripped[:50]}...")
                break
        
        if revision_start_idx >= 0:
            # 개정이유 섹션에서 내용 추출 (주요내용 섹션 전까지)
            revision_lines = []
            end_idx = main_content_start_idx if main_content_start_idx > revision_start_idx else len(lines)
            
            for i in range(revision_start_idx + 1, end_idx):
                line = lines[i].strip()
                
                # '2. 주요내용' 섹션 시작 확인
                if re.match(r'^2[.\s]*주요내용', line):
                    break
                
                # 다음 섹션 시작 확인 (다른 키워드가 나타나면 중단)
                is_next_section = False
                section_keywords = ['공포일', '시행일', '제정일', '시행', '공포', '부칙', '제1조', '제 1 조']
                for section_keyword in section_keywords:
                    if line.startswith(section_keyword) and len(line) < 50:  # 섹션 제목으로 보이는 경우
                        is_next_section = True
                        break
                
                if is_next_section:
                    break
                
                # 빈 라인은 건너뛰기 (단, 이미 내용이 있으면 하나만 허용)
                if not line:
                    if revision_lines and revision_lines[-1]:  # 이전 라인이 비어있지 않으면 빈 라인 하나 허용
                        continue
                    else:
                        continue
                
                # 날짜만 있는 라인 제외
                if re.match(r'^\d{4}', line) and len(line) < 20:
                    continue
                
                revision_lines.append(line)
            
            if revision_lines:
                revision_reason = '\n'.join(revision_lines).strip()
                # 불필요한 공백 정리
                revision_reason = re.sub(r'\s+', ' ', revision_reason)
                # 의미 있는 내용인지 확인
                if revision_reason and len(revision_reason) > 10:
                    # 의미 없는 키워드가 포함되어 있으면 제외
                    meaningless_keywords = ['개정정보', '연혁 선택', 'SBLAW', '표준 규정', '약관 연혁']
                    if not any(keyword in revision_reason for keyword in meaningless_keywords):
                        print(f"  → 개정이유 추출: {revision_reason[:100]}...")
                    else:
                        print(f"  ⚠ 개정이유에 의미 없는 텍스트 포함, 빈 값으로 처리")
                        revision_reason = ""
                else:
                    print(f"  ⚠ 개정이유가 비어있거나 너무 짧음")
                    revision_reason = ""
        
        # '2. 주요내용' 섹션 추출
        if main_content_start_idx >= 0:
            main_content_lines = []
            # 다음 섹션 시작까지 또는 파일 끝까지 추출
            for i in range(main_content_start_idx + 1, len(lines)):
                line = lines[i].strip()
                
                # 다음 섹션 시작 확인 (3. 참고사항, 3 참고사항 등)
                if re.match(r'^3[.\s]*참고사항', line) or re.match(r'^3[.\s]*기타', line):
                    break
                
                # 다른 섹션 시작 확인
                is_next_section = False
                section_keywords = ['공포일', '시행일', '제정일', '시행', '공포', '부칙', '제1조', '제 1 조']
                for section_keyword in section_keywords:
                    if line.startswith(section_keyword) and len(line) < 50:
                        is_next_section = True
                        break
                
                if is_next_section:
                    break
                
                # 빈 라인은 건너뛰기 (단, 이미 내용이 있으면 하나만 허용)
                if not line:
                    if main_content_lines and main_content_lines[-1]:
                        continue
                    else:
                        continue
                
                # 날짜만 있는 라인 제외
                if re.match(r'^\d{4}', line) and len(line) < 20:
                    continue
                
                main_content_lines.append(line)
            
            if main_content_lines:
                revision_content = '\n'.join(main_content_lines).strip()
                # 불필요한 공백 정리
                revision_content = re.sub(r'\s+', ' ', revision_content)
                if revision_content and len(revision_content) > 10:
                    print(f"  → 개정내용 추출: {revision_content[:100]}...")
                else:
                    revision_content = ""
        
        # 개정이유를 찾지 못한 경우, 파일 전체에서 의미 있는 부분 추출 시도
        if not revision_reason:
            # 파일 앞부분에서 의미 있는 텍스트 블록 추출
            meaningful_lines = []
            for line in lines[:30]:  # 처음 30줄만 확인
                line = line.strip()
                if line and len(line) > 10:
                    # 날짜만 있는 라인 제외
                    if not re.match(r'^\d{4}', line):
                        # 섹션 제목 제외
                        if not any(keyword in line for keyword in ['공포일', '시행일', '제정일', '개정일']):
                            meaningful_lines.append(line)
                            if len(meaningful_lines) >= 10:  # 최대 10줄
                                break
            
            if meaningful_lines:
                revision_reason = ' '.join(meaningful_lines)
                print(f"  → 개정이유 추출 (전체 내용에서): {revision_reason[:100]}...")
        
        return {
            'revision_reason': revision_reason,
            'promulgation_date': promulgation_date,
            'enforcement_date': enforcement_date,
            'revision_content': revision_content
        }
    
    def _normalize_extracted_date(self, date_str: str) -> str:
        """추출한 날짜 문자열을 yyyy-mm-dd 형태로 정규화
        Args:
            date_str: 추출한 날짜 문자열
        Returns:
            yyyy-mm-dd 형태의 날짜 문자열
        """
        if not date_str:
            return ""
        
        date_str = date_str.strip()
        
        # YYYYMMDD 형태
        if re.match(r'^\d{8}$', date_str):
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # YYYY.MM.DD 또는 YYYY-MM-DD 형태
        match = re.match(r'(\d{4})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})', date_str)
        if match:
            year = match.group(1)
            month = match.group(2).zfill(2)
            day = match.group(3).zfill(2)
            return f"{year}-{month}-{day}"
        
        # YYYY년 MM월 DD일 형태
        match = re.match(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', date_str)
        if match:
            year = match.group(1)
            month = match.group(2).zfill(2)
            day = match.group(3).zfill(2)
            return f"{year}-{month}-{day}"
        
        # 이미 yyyy-mm-dd 형태인 경우
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        return ""
    
    def _save_outputs(self, records: List[Dict], meta: Dict) -> None:
        """JSON / CSV 결과 저장 (KFB_Scraper와 동일한 컬럼 구조)"""
        # 날짜 필드 정규화 및 본문/개정이유/개정내용 길이 제한
        normalized_records = []
        for item in records:
            normalized_item = item.copy()
            # 날짜 필드 정규화
            normalized_item['제정일'] = self.normalize_date_format(normalized_item.get('제정일', ''))
            normalized_item['최근 개정일'] = self.normalize_date_format(normalized_item.get('최근 개정일', ''))
            # 본문 내용 처리 (content_all 플래그에 따라 길이 제한)
            content = normalized_item.get('본문', '') or ''
            # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            # content_all이 False인 경우에만 4000자로 제한
            if not self.content_all and len(content) > 4000:
                content = content[:4000]
            normalized_item['본문'] = content

            # 개정이유/개정내용도 최대 4000자로 제한
            rev_reason = (normalized_item.get('개정이유', '') or '').replace("\r\n", "\n").replace("\r", "\n")
            if len(rev_reason) > 4000:
                rev_reason = rev_reason[:4000]
            normalized_item['개정이유'] = rev_reason

            rev_content = (normalized_item.get('개정내용', '') or '').replace("\r\n", "\n").replace("\r", "\n")
            if len(rev_content) > 4000:
                rev_content = rev_content[:4000]
            normalized_item['개정내용'] = rev_content
            normalized_records.append(normalized_item)
        
        # JSON 저장
        json_payload = {
            "crawled_at": meta.get("crawled_at", ""),
            "url": meta.get("url", ""),
            "total_count": len(normalized_records),
            "results": normalized_records,
        }
        json_path = self.output_dir / "json" / self.JSON_FILENAME
        with open(json_path, "w", encoding="utf-8") as jf:
            import json  # 지역 import로 지연 로딩
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        print(f"JSON 저장 완료: {json_path}")
        
        # CSV 저장 (KFB와 동일한 헤더 순서)
        csv_path = self.output_dir / "csv" / self.CSV_FILENAME
        if not normalized_records:
            print("저장할 레코드가 없어 CSV 생성을 건너뜁니다.")
            return
        
        # KFB_Scraper와 동일한 헤더 순서 (개정이유, 개정내용, 공포일, 시행일 추가)
        headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "개정이유", "개정내용", "공포일", "시행일", "파일 다운로드 링크", "파일 이름"]
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=headers)
            writer.writeheader()
            for item in normalized_records:
                # 본문/개정이유/개정내용 처리 (content_all 플래그에 따라 길이 제한, 최대 4000자)
                content = (item.get('본문', '') or '').replace("\r\n", "\n").replace("\r", "\n")
                if not self.content_all and len(content) > 4000:
                    content = content[:4000]

                rev_reason = (item.get('개정이유', '') or '').replace("\r\n", "\n").replace("\r", "\n")
                if len(rev_reason) > 4000:
                    rev_reason = rev_reason[:4000]

                rev_content = (item.get('개정내용', '') or '').replace("\r\n", "\n").replace("\r", "\n")
                if len(rev_content) > 4000:
                    rev_content = rev_content[:4000]
                
                csv_item = item.copy()
                csv_item['본문'] = content
                csv_item['개정이유'] = rev_reason
                csv_item['개정내용'] = rev_content
                # None 값을 빈 문자열로 변환
                for key in headers:
                    if csv_item.get(key) is None:
                        csv_item[key] = ''
                writer.writerow(csv_item)
        print(f"CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="KRX 법무포탈 스크래퍼")
    parser.add_argument(
        "--content-all",
        action="store_true",
        help="본문 내용을 전체로 가져옵니다 (기본값: 4000자 제한)"
    )
    args = parser.parse_args()
    
    crawler = KrxScraper(content_all=args.content_all)
    results = crawler.crawl_krx_legal_portal()
    print(f"추출된 데이터: {len(results)}개")

