# fsb_scraper_v2.py
# 저축은행중앙회-소비자포탈>모범규준
# 	참고 : [SBLAW포탈] 저축은행중앙회 SBLAW 표준규정·약관 연혁관리시스템


"""
저축은행중앙회-소비자포탈>모범규준 스크래퍼
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
from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor
from common.file_comparator import FileComparator
import time
import os
import re
import json
import argparse

# .env 파일 로드 (python-dotenv가 없어도 직접 파싱)
def load_env_file():
    """.env 파일을 직접 파싱하여 환경변수에 설정"""
    try:
        project_root = find_project_root()
    except:
        project_root = Path.cwd()
    
    env_paths = [
        project_root / '.env',
        project_root / 'FSB_Scraper' / '.env',
    ]
    try:
        env_paths.append(Path(__file__).resolve().parent / '.env')
    except:
        pass
    
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 주석이나 빈 줄 건너뛰기
                        if not line or line.startswith('#'):
                            continue
                        # KEY=VALUE 형식 파싱
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            # 따옴표 제거
                            if value.startswith('"') and value.endswith('"'):
                                value = value[1:-1]
                            elif value.startswith("'") and value.endswith("'"):
                                value = value[1:-1]
                            # 환경변수에 설정 (이미 있으면 덮어쓰지 않음)
                            if key and value and key not in os.environ:
                                os.environ[key] = value
                print(f"✓ .env 파일 로드: {env_path}")
                return True
            except Exception as e:
                print(f"⚠ .env 파일 파싱 중 오류 ({env_path}): {e}")
                continue
    
    # python-dotenv도 시도 (설치되어 있으면 사용)
    try:
        from dotenv import load_dotenv
        try:
            project_root = find_project_root()
        except:
            project_root = Path.cwd()
        
        env_paths = [
            project_root / '.env',
            project_root / 'FSB_Scraper' / '.env',
        ]
        try:
            env_paths.append(Path(__file__).resolve().parent / '.env')
        except:
            pass
        
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path, override=True)
                print(f"✓ .env 파일 로드 (dotenv): {env_path}")
                return True
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠ dotenv 로드 중 오류: {e}")
    
    return False

# .env 파일 로드 실행
env_loaded = load_env_file()
if not env_loaded:
    print("⚠ .env 파일을 찾을 수 없습니다. 환경변수 또는 명령줄 인자를 사용하세요.")


class FsbScraper(BaseScraper):
    """저축은행중앙회 - SBLAW 포탈 스크래퍼"""
    
    BASE_URL = "http://sblaw.fsb.or.kr"
    LOGIN_URL = "http://sblaw.fsb.or.kr/lmxsrv/member/login.do"
    # 모범규준 페이지 URL
    MODEL_GUIDELINES_URL = "https://www.fsb.or.kr/coslegianno_0200.act?ETC_YN=Y"
    DEFAULT_CSV_PATH = "FSB_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, login_id: str = None, login_password: str = None, csv_path: Optional[str] = None):
        super().__init__(delay)
    
        # 로그인 정보 설정 (우선순위: 인자 > 환경변수 > 코드 직접 입력)
        # 1. 인자로 전달된 경우 우선 사용
        if login_id:
            self.LOGIN_ID = login_id
            print(f"✓ 로그인 ID 설정됨 (명령줄 인자)")
        else:
            # 2. 환경변수에서 읽기 (.env 파일 또는 시스템 환경변수)
            self.LOGIN_ID = os.getenv('FSB_LOGIN_ID', '') or os.getenv('LOGIN_ID', '')
            if self.LOGIN_ID:
                print(f"✓ 로그인 ID 설정됨 (환경변수)")
            else:
                print(f"⚠ 로그인 ID가 설정되지 않았습니다.")
        
        if login_password:
            self.LOGIN_PASSWORD = login_password
            print(f"✓ 로그인 비밀번호 설정됨 (명령줄 인자)")
        else:
            # 2. 환경변수에서 읽기 (.env 파일 또는 시스템 환경변수)
            self.LOGIN_PASSWORD = os.getenv('FSB_LOGIN_PASSWORD', '') or os.getenv('LOGIN_PASSWORD', '')
            if self.LOGIN_PASSWORD:
                print(f"✓ 로그인 비밀번호 설정됨 (환경변수)")
            else:
                print(f"⚠ 로그인 비밀번호가 설정되지 않았습니다.")
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        self.downloads_dir = self.output_dir / "downloads"
        self.previous_dir = self.downloads_dir / "previous"
        self.current_dir = self.downloads_dir / "current"
        self.debug_dir = self.output_dir / "debug"
        
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.previous_dir.mkdir(parents=True, exist_ok=True)
        self.current_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        
        # FileExtractor 초기화 (current 디렉토리 사용)
        self.file_extractor = FileExtractor(download_dir=str(self.current_dir), session=self.session)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=str(self.downloads_dir))
        
        # 하위 호환성을 위해 기존 download_dir도 유지
        self.download_dir = str(self.downloads_dir)
        
        # CSV에서 대상 규정 목록 로드
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
            print("⚠ 대상 CSV를 찾지 못했거나 비어 있습니다. 전체 목록을 대상으로 진행합니다.")
    
    # 파일 처리 메서드들은 common.file_extractor.FileExtractor로 위임
    def download_file(self, url: str, filename: str, use_selenium: bool = False, driver=None) -> tuple[Optional[str], Optional[str]]:
        """파일 다운로드 (FileExtractor로 위임)"""
        return self.file_extractor.download_file(
            url, filename, use_selenium=use_selenium, driver=driver,
            referer=self.BASE_URL
        )
    
    def extract_files_from_zip(self, zip_path: str) -> Optional[str]:
        """ZIP 파일에서 파일 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_files_from_zip(zip_path)
    
    def extract_pdf_content(self, filepath: str) -> str:
        """PDF 내용 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_pdf_content(filepath)
    
    def extract_hwp_content(self, filepath: str) -> str:
        """HWP 내용 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_hwp_content(filepath)
    
    def _backup_current_to_previous(self) -> None:
        """스크래퍼 시작 시 current 디렉토리를 previous로 백업"""
        if not self.current_dir.exists():
            return
        
        files_in_current = [f for f in self.current_dir.glob("*") if f.is_file()]
        if not files_in_current:
            return
        
        print(f"  → 이전 버전 백업 중... (current → previous)")
        
        import shutil
        if self.previous_dir.exists():
            for item in self.previous_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        
        for file_path in files_in_current:
            shutil.copy2(file_path, self.previous_dir / file_path.name)
        
        for file_path in files_in_current:
            file_path.unlink()
        
        print(f"  ✓ 이전 버전 백업 완료 ({len(files_in_current)}개 파일)")
    
    def _clear_diffs_directory(self) -> None:
        """스크래퍼 시작 시 diffs 디렉토리 비우기"""
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
    
    def save_debug_html(self, soup: BeautifulSoup, filename: str = "debug.html"):
        """디버깅용 HTML 저장"""
        debug_path = self.debug_dir / filename
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        print(f"  ✓ 디버그 HTML 저장: {debug_path}")
    
    def _login(self, driver) -> bool:
        """로그인 처리
        Args:
            driver: Selenium WebDriver
        Returns:
            로그인 성공 여부
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            if not self.LOGIN_ID or not self.LOGIN_PASSWORD:
                print("⚠ 로그인 ID 또는 비밀번호가 설정되지 않았습니다.")
                print("   코드에서 LOGIN_ID와 LOGIN_PASSWORD를 설정하거나")
                print("   --login-id, --login-password 옵션을 사용하세요.")
                return False
            
            print(f"  → 로그인 페이지 접근 중...")
            driver.get(self.LOGIN_URL)
            time.sleep(2)
            
            # 로그인 폼 찾기 (여러 가능한 선택자 시도)
            id_input = None
            password_input = None
            login_button = None
            
            # ID 입력 필드 찾기
            id_selectors = [
                'input[name="id"]',
                'input[name="userId"]',
                'input[name="user_id"]',
                'input[name="username"]',
                'input[type="text"]',
                '#id',
                '#userId',
                '#user_id',
                '#username',
            ]
            
            for selector in id_selectors:
                try:
                    id_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if id_input:
                        break
                except:
                    continue
            
            # 비밀번호 입력 필드 찾기
            password_selectors = [
                'input[name="password"]',
                'input[name="pwd"]',
                'input[name="passwd"]',
                'input[type="password"]',
                '#password',
                '#pwd',
                '#passwd',
            ]
            
            for selector in password_selectors:
                try:
                    password_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if password_input:
                        break
                except:
                    continue
            
            # 로그인 버튼 찾기
            button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("로그인")',
                'a:contains("로그인")',
                '.login-btn',
                '#loginBtn',
                '#login',
            ]
            
            for selector in button_selectors:
                try:
                    login_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if login_button:
                        break
                except:
                    continue
            
            if not id_input or not password_input:
                print(f"  ⚠ 로그인 폼을 찾을 수 없습니다.")
                # 디버깅: 페이지 소스 저장
                self.save_debug_html(BeautifulSoup(driver.page_source, 'lxml'), filename="debug_fsb_login.html")
                return False
            
            # 로그인 정보 입력
            print(f"  → 로그인 정보 입력 중...")
            id_input.clear()
            id_input.send_keys(self.LOGIN_ID)
            time.sleep(0.5)
            
            password_input.clear()
            password_input.send_keys(self.LOGIN_PASSWORD)
            time.sleep(0.5)
            
            # 로그인 버튼 클릭 또는 Enter 키 입력
            if login_button:
                login_button.click()
            else:
                from selenium.webdriver.common.keys import Keys
                password_input.send_keys(Keys.RETURN)
            
            time.sleep(3)  # 로그인 처리 대기
            
            # 로그인 성공 확인 (URL 변경 또는 특정 요소 확인)
            current_url = driver.current_url
            if 'login' not in current_url.lower() or current_url != self.LOGIN_URL:
                print(f"  ✓ 로그인 성공 (URL: {current_url})")
                return True
            else:
                # 로그인 실패 가능성 (에러 메시지 확인)
                page_text = driver.page_source.lower()
                if 'error' in page_text or '실패' in page_text or '틀렸' in page_text:
                    print(f"  ✗ 로그인 실패 (에러 메시지 발견)")
                    return False
                else:
                    # URL이 변경되지 않았지만 에러도 없으면 성공으로 간주
                    print(f"  ✓ 로그인 완료 (URL 변경 없음, 계속 진행)")
                    return True
                    
        except Exception as e:
            print(f"  ⚠ 로그인 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _download_and_compare_file(
        self, file_url: str, file_name: str, regulation_name: str = "", 
        use_selenium: bool = False, driver=None
    ) -> Optional[Dict]:
        """파일 다운로드 및 이전 파일과 비교"""
        try:
            import shutil
            
            # 파일 확장자 추출
            ext = Path(file_name).suffix if file_name else ''
            if not ext:
                url_lower = file_url.lower()
                if '.zip' in url_lower:
                    ext = '.zip'
                elif '.pdf' in url_lower:
                    ext = '.pdf'
                elif '.hwp' in url_lower:
                    ext = '.hwp'
                else:
                    ext = '.hwp'
            
            # 안전한 파일명 생성 (규정명 기반)
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
            
            new_file_path = self.current_dir / safe_filename
            previous_file_path = self.previous_dir / safe_filename
            
            print(f"  → 파일 다운로드 중: {file_name}")
            downloaded_result = self.file_extractor.download_file(
                file_url,
                safe_filename,
                use_selenium=use_selenium,
                driver=driver,
                referer=self.BASE_URL
            )
            
            if downloaded_result:
                downloaded_path, actual_filename = downloaded_result
            else:
                downloaded_path, actual_filename = None, None
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                print(f"  ⚠ 파일 다운로드 실패")
                return None
            
            if str(downloaded_path) != str(new_file_path):
                if new_file_path.exists():
                    new_file_path.unlink()
                shutil.move(downloaded_path, new_file_path)
                print(f"  ✓ 파일 저장: {new_file_path}")
            
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
    
    def _load_target_laws(self, csv_path: str) -> List[Dict]:
        """CSV 파일에서 스크래핑 대상 규정명을 로드한다.
        기대 컬럼: 구분, 법령명 (또는 규정명)
        """
        if not csv_path:
            return []
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            csv_file = find_project_root() / csv_path
        if not csv_file.exists():
            print(f"⚠ FSB 대상 CSV를 찾을 수 없습니다: {csv_file}")
            return []

        targets: List[Dict] = []
        try:
            with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    # 법령명 또는 규정명 컬럼 확인
                    name = (row.get("법령명") or row.get("규정명") or "").strip()
                    category = (row.get("구분") or "").strip()
                    if not name:
                        continue
                    targets.append({"law_name": name, "category": category})
        except Exception as exc:
            print(f"⚠ FSB 대상 CSV 로드 실패: {exc}")
            return []
        return targets

    def _normalize_title(self, text: Optional[str]) -> str:
        """비교를 위한 규정명 정규화"""
        if not text:
            return ""
        cleaned = re.sub(r"[\s\W]+", "", text)
        return cleaned.lower()
    
    def _normalize_date_text(self, date_text: str) -> str:
        """
        날짜 텍스트를 정규화된 형식으로 변환
        예: "2008. 12. 30" -> "2008-12-30"
        예: "2025-01-16 개정" -> "2025-01-16"
        """
        if not date_text:
            return ""
        
        # "개정", "제정" 등의 텍스트 제거
        cleaned = re.sub(r'\s*(개정|제정|\.)\s*$', '', date_text, flags=re.IGNORECASE)
        
        # 이미 YYYY-MM-DD 형식인 경우
        if re.match(r'^\d{4}-\d{1,2}-\d{1,2}', cleaned):
            parts = cleaned.split('-')
            if len(parts) >= 3:
                year = parts[0]
                month = str(int(parts[1])).zfill(2)
                day = str(int(parts[2])).zfill(2)
                return f"{year}-{month}-{day}"
        
        # 공백 제거 및 정규화
        cleaned = re.sub(r"[년월일]", ".", cleaned)
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
    
    def extract_tree_links(self, driver) -> List[Dict]:
        """
        왼쪽 트리 iframe(#tree01)에서 모든 규정 링크를 추출한다.
        """
        links: List[Dict] = []

        try:
            from selenium.webdriver.common.by import By
            
            # 왼쪽 트리 iframe으로 전환
            tree_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#tree01")
            driver.switch_to.frame(tree_iframe)
            time.sleep(2)  # iframe 로딩 대기

            # 트리를 모두 펼치기 시도
            try:
                # JavaScript 함수로 트리 펼치기 시도
                driver.execute_script("""
                    try {
                        if (typeof allFolderOpen === 'function') {
                            allFolderOpen();
                        }
                    } catch(e) { console.log('allFolderOpen error:', e); }
                """)
                time.sleep(1)
                
                driver.execute_script("""
                    try {
                        if (typeof tree1 !== 'undefined' && typeof tree1.expandChildren === 'function') {
                            tree1.expandChildren();
                        }
                    } catch(e) { console.log('tree1.expandChildren error:', e); }
                """)
                time.sleep(1)
                
                # 모든 폴더 클릭하여 펼치기
                driver.execute_script("""
                    try {
                        var folders = document.querySelectorAll('a[id^="webfx-tree-object-"][href*="javascript"]');
                        for (var i = 0; i < folders.length; i++) {
                            var folder = folders[i];
                            var img = folder.querySelector('img');
                            if (img && (img.src.indexOf('folder') !== -1 || img.src.indexOf('cbook') !== -1)) {
                                var parent = folder.parentElement;
                                if (parent && (parent.className.indexOf('closed') !== -1 || 
                                    getComputedStyle(parent).display === 'none')) {
                                    folder.click();
                                }
                            }
                        }
                    } catch(e) { console.log('expand all error:', e); }
                """)
                time.sleep(3)
                
                print(f"  트리 펼치기 시도 완료")
            except Exception as e:
                print(f"  ⚠ 트리 펼치기 실패 (계속 진행): {e}")

            # 트리 구조에서 모든 링크 추출
            tree_link_selectors = [
                "a[id^='webfx-tree-object-']",
                "[id^='webfx-tree-object-'][id$='-anchor']",
                "a[href*='javascript']",
            ]

            all_links = []
            for selector in tree_link_selectors:
                try:
                    found_links = driver.find_elements(By.CSS_SELECTOR, selector)
                    if found_links:
                        all_links = found_links
                        break
                except Exception as e:
                    continue
            
            print(f"  발견된 링크: {len(all_links)}개")

            # 중복 제거
            seen_ids = set()
            unique_links = []
            for link in all_links:
                try:
                    link_id = link.get_attribute("id") or ""
                    link_text = link.text.strip()
                    if link_id and link_id not in seen_ids:
                        seen_ids.add(link_id)
                        unique_links.append(link)
                    elif link_text and link_text not in seen_ids:
                        seen_ids.add(link_text)
                        unique_links.append(link)
                except:
                    continue
            
            all_links = unique_links
            print(f"  최종: {len(all_links)}개 링크 (중복 제거 후)")

            # 링크 정보 추출
            for link_element in all_links:
                try:
                    text = link_element.text.strip()
                    element_id = link_element.get_attribute("id") or ""
                    href = link_element.get_attribute("href") or ""
                    onclick = link_element.get_attribute("onclick") or ""
                    js_code = href if href.startswith("javascript:") else onclick

                    # 규정명이 있는 링크만 수집
                    if text and len(text) > 2:
                        item: Dict[str, str] = {
                            "title": text,
                            "regulation_name": text,
                            "organization": "저축은행중앙회",
                            "tree_element_id": element_id,
                            "tree_onclick": js_code,
                            "detail_link": "",
                            "content": "",
                            "department": "",
                            "file_name": "",
                            "download_link": "",
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
    
    def click_tree_link_and_extract(self, driver, item: Dict) -> Optional[BeautifulSoup]:
        """
        트리 링크를 클릭하고 오른쪽 iframe에서 내용을 추출한다.
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            
            # 왼쪽 트리 iframe으로 전환
            tree_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#tree01")
            driver.switch_to.frame(tree_iframe)
            time.sleep(1)

            # 요소 ID로 링크 찾기 및 클릭
            element_id = item.get("tree_element_id", "")
            if element_id:
                try:
                    link_element = driver.find_element(By.CSS_SELECTOR, f"#{element_id}")
                    driver.execute_script("arguments[0].click();", link_element)
                    time.sleep(2)  # 콘텐츠 로딩 대기
                except Exception as e:
                    print(f"  ⚠ 요소 클릭 실패 ({element_id}): {e}")
                    driver.switch_to.default_content()
                    return None

            # 메인 프레임으로 복귀
            driver.switch_to.default_content()

            # 오른쪽 콘텐츠 iframe 확인 (#lawDetailContent)
            time.sleep(2)  # iframe 로딩 대기
            
            # 여러 iframe 위치 시도 (규정마다 다른 구조를 사용할 수 있음)
            iframe_xpaths = [
                ("CSS Selector", "iframe#lawDetailContent", None),
                ("XPath (일반)", "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[6]/div[2]/iframe", None),
                ("XPath (뷰어)", "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[5]/div/div/iframe", None),
            ]
            
            soup = None
            for method_name, selector, _ in iframe_xpaths:
                try:
                    driver.switch_to.default_content()  # 매번 메인 프레임으로 복귀
                    time.sleep(0.5)
                    
                    if method_name == "CSS Selector":
                        content_iframe = driver.find_element(By.CSS_SELECTOR, selector)
                    else:
                        content_iframe = driver.find_element(By.XPATH, selector)
                    
                    driver.switch_to.frame(content_iframe)
                    time.sleep(2)
                    
                    # iframe 내용 추출
                    soup = BeautifulSoup(driver.page_source, "lxml")
                    
                    # 디버깅: 첫 번째 항목만 HTML 저장
                    if not hasattr(self, '_lawDetailContent_debug_saved'):
                        self.save_debug_html(soup, filename="debug_fsb_lawDetailContent.html")
                        self._lawDetailContent_debug_saved = True
                    
                    print(f"  ✓ iframe 접근 성공 ({method_name})")
                    driver.switch_to.default_content()
                    return soup
                    
                except Exception as e:
                    print(f"  ⚠ {method_name}로 iframe 접근 실패: {e}")
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass
                    continue
            
            # 모든 방법 실패 - iframe이 없는 경우일 수 있음
            print(f"  ⚠ 모든 iframe 접근 방법 실패 (iframe이 없는 구조일 수 있음)")
            driver.switch_to.default_content()
            
            # 메인 프레임의 HTML 저장 (iframe이 없는 경우 대비)
            try:
                main_soup = BeautifulSoup(driver.page_source, "lxml")
                regulation_name = item.get('title', item.get('regulation_name', 'unknown'))
                safe_name = re.sub(r'[^\w\s-]', '', regulation_name).replace(' ', '_')
                debug_filename = f"debug_fsb_no_iframe_{safe_name}.html"
                self.save_debug_html(main_soup, filename=debug_filename)
                print(f"  ✓ 메인 프레임 HTML 저장: {debug_filename}")
                # iframe이 없음을 표시하기 위한 플래그 추가
                main_soup._no_iframe = True
                return main_soup
            except Exception as e:
                print(f"  ⚠ 메인 프레임 HTML 저장 실패: {e}")
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
    
    def _extract_revision_info_from_soup(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        BeautifulSoup 객체에서 개정정보 추출 (공통 함수)
        
        Args:
            soup: BeautifulSoup 객체
            
        Returns:
            {'revision_reason': str, 'enforcement_date': str, 'promulgation_date': str} 딕셔너리
        """
        revision_reason = ""
        enforcement_date = ""
        promulgation_date = ""
        
        try:
            table = soup.find('table', class_='popTable')
            if table:
                rows = table.find_all('tr')
                for row in rows:
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        th_text = th.get_text(strip=True)
                        td_text = td.get_text(strip=True)
                        
                        # 시행일 추출
                        if '시행일' in th_text:
                            date_match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', td_text)
                            if date_match:
                                year = date_match.group(1)
                                month = str(int(date_match.group(2))).zfill(2)
                                day = str(int(date_match.group(3))).zfill(2)
                                enforcement_date = f"{year}-{month}-{day}"
                                print(f"  ✓ 시행일 추출: {enforcement_date}")
                        
                        # 개정일 추출 (공포일로 사용)
                        elif '개정일' in th_text:
                            date_match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', td_text)
                            if date_match:
                                year = date_match.group(1)
                                month = str(int(date_match.group(2))).zfill(2)
                                day = str(int(date_match.group(3))).zfill(2)
                                promulgation_date = f"{year}-{month}-{day}"
                                print(f"  ✓ 개정일 추출 (공포일로 사용): {promulgation_date}")
                        
                        # 개정사유 추출
                        elif '개정사유' in th_text or '개정이유' in th_text:
                            next_row = row.find_next_sibling('tr')
                            if next_row:
                                reason_td = next_row.find('td')
                                if reason_td:
                                    pre = reason_td.find('pre')
                                    if pre:
                                        extracted_text = pre.get_text(strip=True)
                                    else:
                                        extracted_text = reason_td.get_text(strip=True)
                                    
                                    # 의미 있는 개정사유인지 확인
                                    if extracted_text and len(extracted_text) > 10:
                                        meaningless_keywords = ['개정정보', '연혁 선택', '연혁선택', 'SBLAW', '표준 규정', '약관 연혁']
                                        if not any(keyword in extracted_text for keyword in meaningless_keywords):
                                            revision_reason = extracted_text
                                            print(f"  ✓ 개정사유 추출: {revision_reason[:100]}...")
                                        else:
                                            print(f"  ⚠ 개정사유에 의미 없는 텍스트 포함, 빈 값으로 처리")
                                    else:
                                        print(f"  ⚠ 개정사유가 비어있거나 너무 짧음, 빈 값으로 처리")
                
                # 개정사유가 아직 없으면 한 번 더 시도 (다른 방법)
                if not revision_reason:
                    reason_section = soup.find('th', string=re.compile('개정사유|개정이유'))
                    if reason_section:
                        reason_row = reason_section.find_parent('tr')
                        if reason_row:
                            next_row = reason_row.find_next_sibling('tr')
                            if next_row:
                                reason_td = next_row.find('td')
                                if reason_td:
                                    pre = reason_td.find('pre')
                                    if pre:
                                        extracted_text = pre.get_text(strip=True)
                                    else:
                                        extracted_text = reason_td.get_text(strip=True)
                                    
                                    # 의미 있는 개정사유인지 확인
                                    if extracted_text and len(extracted_text) > 10:
                                        meaningless_keywords = ['개정정보', '연혁 선택', '연혁선택', 'SBLAW', '표준 규정', '약관 연혁']
                                        if not any(keyword in extracted_text for keyword in meaningless_keywords):
                                            revision_reason = extracted_text
                                            print(f"  ✓ 개정사유 추출 (대체 방법): {revision_reason[:100]}...")
                                        else:
                                            print(f"  ⚠ 개정사유에 의미 없는 텍스트 포함, 빈 값으로 처리")
                                    else:
                                        print(f"  ⚠ 개정사유가 비어있거나 너무 짧음, 빈 값으로 처리")
        except Exception as e:
            print(f"  ⚠ 개정정보 추출 중 오류: {e}")
        
        return {
            'revision_reason': revision_reason,
            'enforcement_date': enforcement_date,
            'promulgation_date': promulgation_date
        }
    
    def extract_content_from_new_window(
        self,
        driver,
        has_no_iframe: bool = False,
        regulation_name: str = "",
        content_limit: int = 0
    ) -> Dict[str, str]:
        """
        상세 페이지에서 개정이유 버튼을 클릭하여 열리는 새 창에서 내용 추출
        '개정이유', '시행일', '공포일' 정보를 추출
        
        Args:
            driver: Selenium WebDriver 인스턴스
            has_no_iframe: iframe이 없는 구조인지 여부
            
        Returns:
            {
                'revision_reason': str,
                'enforcement_date': str,
                'promulgation_date': str,
                'revision_content': str
            } 딕셔너리
        """
        if driver is None:
            return {
                'revision_reason': '',
                'enforcement_date': '',
                'promulgation_date': '',
                'revision_content': '',
            }
        
        original_window = None
        revision_reason = ""
        enforcement_date = ""
        promulgation_date = ""
        revision_content = ""
        
        # js_code 변수 초기화 (showPopup 처리용)
        js_code = ""
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time
            import re
            import os
            import shutil
            from pathlib import Path
            
            # 개정문 파일 다운로드 헬퍼
            def _download_revision_file_from_popup() -> str:
                """
                새 창(팝업)에서 개정문(HWP/PDF) 파일을 다운로드하고 내용(개정내용)을 추출한다.
                """
                try:
                    from selenium.webdriver.common.by import By as ByInner
                except Exception:
                    return ""

                # 다운로드 전 현재 파일 목록 저장
                files_before = set(
                    f.name for f in self.current_dir.glob("*") if f.is_file()
                )

                link_element = None
                # 1차: 사용자 제공 CSS 셀렉터
                selectors = [
                    "#Popup_content > table > tbody > tr:nth-child(7) > td > a",
                ]
                xpaths = [
                    "/html/body/div/div[2]/table/tbody/tr[7]/td/a",
                ]

                # CSS selector 시도
                for selector in selectors:
                    try:
                        link_element = driver.find_element(ByInner.CSS_SELECTOR, selector)
                        if link_element:
                            break
                    except Exception:
                        continue

                # XPath 시도
                if not link_element:
                    from selenium.common.exceptions import NoSuchElementException
                    for xp in xpaths:
                        try:
                            link_element = driver.find_element(ByInner.XPATH, xp)
                            if link_element:
                                break
                        except NoSuchElementException:
                            continue

                if not link_element:
                    print("  ⚠ 팝업에서 개정문 다운로드 링크를 찾지 못했습니다.")
                    return ""

                # CDP 다운로드 설정 (실패해도 계속 진행)
                try:
                    driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                        'behavior': 'allow',
                        'downloadPath': str(self.current_dir)
                    })
                except Exception as cdp_error:
                    print(f"  ⚠ 팝업 개정문 CDP 설정 실패 (계속 진행): {cdp_error}")

                # 링크 클릭으로 다운로드 시작
                try:
                    driver.execute_script("arguments[0].click();", link_element)
                    print("  → 개정문 파일 다운로드 클릭")
                except Exception as e:
                    print(f"  ⚠ 개정문 다운로드 클릭 실패: {e}")
                    return ""

                # 다운로드 완료 대기
                max_wait = 60
                waited = 0
                downloaded_file = None

                while waited < max_wait:
                    downloaded_files = list(self.current_dir.glob("*"))
                    crdownload_files = [
                        f for f in downloaded_files if f.name.endswith('.crdownload')
                    ]

                    if crdownload_files:
                        print(f"  → 개정문 다운로드 진행 중... ({waited}초)")
                    else:
                        for f in downloaded_files:
                            if f.is_file() and not f.name.endswith('.crdownload'):
                                if f.name not in files_before:
                                    if (not downloaded_file or
                                            f.stat().st_mtime > downloaded_file.stat().st_mtime):
                                        downloaded_file = f

                        if downloaded_file:
                            print(f"  ✓ 개정문 파일 다운로드 완료: {downloaded_file.name}")
                            break

                    time.sleep(1)
                    waited += 1

                if not downloaded_file or not downloaded_file.exists():
                    print("  ⚠ 개정문 파일을 찾을 수 없습니다.")
                    return ""

                # 파일명 정리 (규정명 기반)
                ext = downloaded_file.suffix or '.hwp'
                base_name = regulation_name or "revision"
                safe_reg_name = re.sub(r'[^\w\s-]', '', base_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                safe_filename = f"{safe_reg_name}_개정문{ext}"
                new_file_path = self.current_dir / safe_filename

                try:
                    if str(downloaded_file) != str(new_file_path):
                        if new_file_path.exists():
                            new_file_path.unlink()
                        shutil.move(downloaded_file, new_file_path)
                    print(f"  ✓ 개정문 파일 저장: {new_file_path}")
                except Exception as e:
                    print(f"  ⚠ 개정문 파일 이동/이름 변경 실패: {e}")
                    new_file_path = downloaded_file

                # 파일 내용 추출
                file_ext = new_file_path.suffix.lower()
                file_content = ""
                try:
                    if file_ext == '.hwp':
                        file_content = self.extract_hwp_content(str(new_file_path))
                    elif file_ext == '.pdf':
                        file_content = self.extract_pdf_content(str(new_file_path))
                    else:
                        # 기타 확장자는 HWP로 간주
                        file_content = self.extract_hwp_content(str(new_file_path))
                except Exception as e:
                    print(f"  ⚠ 개정문 파일 내용 추출 실패: {e}")
                    file_content = ""

                if not file_content:
                    return ""

                # 개정내용 텍스트 정리 및 길이 제한 (전체 파일 내용 사용)
                content_text = file_content.replace("\r\n", "\n").replace("\r", "\n")
                max_len = min(4000, content_limit) if content_limit > 0 else 4000
                if len(content_text) > max_len:
                    content_text = content_text[:max_len]

                return content_text
            
            # 현재 창 핸들 저장
            original_window = driver.current_window_handle
            all_windows_before = set(driver.window_handles)
            
            # 메인 프레임으로 전환
            driver.switch_to.default_content()
            time.sleep(0.5)
            
            # 개정이유 버튼 찾기 및 클릭
            button_element = None
            
            # 디버깅: has_no_iframe 값 확인
            print(f"  → has_no_iframe 값: {has_no_iframe}")
            
            # 버튼 검증 헬퍼 함수: img title로 확인
            def verify_button_by_img_title(element, expected_title):
                """버튼 내부의 img 태그 title로 검증"""
                try:
                    img = element.find_element(By.TAG_NAME, "img")
                    img_title = img.get_attribute('title') or img.get_attribute('alt') or ''
                    if expected_title in img_title:
                        return True
                except:
                    pass
                return False
            
            # 방법 1: CSS 셀렉터로 찾기 (iframe 있는 경우만)
            if not has_no_iframe:
                try:
                    candidate = driver.find_element(By.CSS_SELECTOR, "#contents_wrap > div > div.btn_box > div > a:nth-child(3)")
                    if candidate and verify_button_by_img_title(candidate, '개정이유'):
                        button_element = candidate
                        print(f"  → 개정이유 버튼 발견 (iframe 있는 경우, CSS 셀렉터, title 검증 통과)")
                except:
                    pass
                
                # 방법 2: XPath로 찾기 (iframe 있는 경우만)
                if not button_element:
                    try:
                        candidate = driver.find_element(By.XPATH, "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[3]/div/a[3]")
                        if candidate and verify_button_by_img_title(candidate, '개정이유'):
                            button_element = candidate
                            print(f"  → 개정이유 버튼 발견 (iframe 있는 경우, XPath, title 검증 통과)")
                    except:
                        pass
            
            # 방법 3: iframe 없는 경우 (개정정보 버튼 - 두 번째 버튼)
            if not button_element and has_no_iframe:
                try:
                    # iframe 없는 경우: #contents_wrap > div > div.btn_box > div > a:nth-child(2)
                    candidate = driver.find_element(By.CSS_SELECTOR, "#contents_wrap > div > div.btn_box > div > a:nth-child(2)")
                    if candidate and verify_button_by_img_title(candidate, '개정정보'):
                        button_element = candidate
                        print(f"  → 개정정보 버튼 발견 (iframe 없는 구조, CSS 셀렉터, title 검증 통과)")
                except:
                    try:
                        # XPath로 시도: /html/body/div[3]/div[3]/div[2]/div[2]/div/div[3]/div/a[2]
                        candidate = driver.find_element(By.XPATH, "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[3]/div/a[2]")
                        if candidate and verify_button_by_img_title(candidate, '개정정보'):
                            button_element = candidate
                            print(f"  → 개정정보 버튼 발견 (iframe 없는 구조, XPath, title 검증 통과)")
                    except:
                        pass
            
            # 방법 4: iframe 없는 경우 대체 방법 (href에 lawRevisionInfo 포함)
            if not button_element and has_no_iframe:
                try:
                    # .btn_box .kor_btn 내의 개정정보 버튼 찾기
                    candidate = driver.find_element(By.CSS_SELECTOR, ".btn_box .kor_btn a[href*='lawRevisionInfo'], .btnDiv.kor_btn a[href*='lawRevisionInfo']")
                    if candidate and verify_button_by_img_title(candidate, '개정정보'):
                        button_element = candidate
                        print(f"  → 개정정보 버튼 발견 (iframe 없는 구조, href 매칭, title 검증 통과)")
                except:
                    try:
                        # XPath로 시도
                        candidate = driver.find_element(By.XPATH, "//div[@class='btn_box']//div[@class='kor_btn']//a[contains(@href, 'lawRevisionInfo')]")
                        if candidate and verify_button_by_img_title(candidate, '개정정보'):
                            button_element = candidate
                            print(f"  → 개정정보 버튼 발견 (iframe 없는 구조, XPath href 매칭, title 검증 통과)")
                    except:
                        pass
            
            # 방법 5: 최후의 수단 - 모든 버튼을 검사하여 img title로 찾기
            if not button_element:
                try:
                    all_buttons = driver.find_elements(By.CSS_SELECTOR, ".btn_box a, .btnDiv a")
                    for btn in all_buttons:
                        if verify_button_by_img_title(btn, '개정정보') or verify_button_by_img_title(btn, '개정이유'):
                            button_element = btn
                            print(f"  → 개정정보/개정이유 버튼 발견 (img title로 검색)")
                            break
                except:
                    pass
            
            if not button_element:
                print(f"  ⚠ 개정이유/개정정보 버튼을 찾을 수 없습니다")
                return {
                    'revision_reason': '',
                    'enforcement_date': '',
                    'promulgation_date': '',
                    'revision_content': '',
                }
            
            # href에서 showPopup 함수 추출 (버튼 클릭 전에)
            href = button_element.get_attribute('href') or ''
            onclick = button_element.get_attribute('onclick') or ''
            js_code = href if href.startswith('javascript:') else onclick
            
            # 디버깅: js_code 출력
            if js_code:
                print(f"  → 버튼 JS 코드: {js_code[:100]}...")
            
            # showPopup 함수인 경우 URL 추출하여 직접 접근
            popup_url = None
            if js_code and 'showPopup' in js_code:
                # showPopup('/lmxsrv/law/lawRevisionInfo.do?SEQ_HISTORY=682','revisionview','735','350');
                popup_url_match = re.search(r"showPopup\s*\(\s*['\"]([^'\"]+)['\"]", js_code)
                if popup_url_match:
                    popup_url = popup_url_match.group(1)
                    if not popup_url.startswith('http'):
                        popup_url = urljoin(self.BASE_URL, popup_url)
                    print(f"  → showPopup URL 추출: {popup_url}")
                else:
                    print(f"  ⚠ showPopup URL 추출 실패 (정규식 매칭 실패)")
            elif js_code:
                print(f"  ⚠ showPopup 함수를 찾을 수 없음 (js_code: {js_code[:50]}...)")
            
            # 버튼 클릭
            try:
                print(f"  → 새 창 열기 버튼 클릭 중...")
                driver.execute_script("arguments[0].scrollIntoView(true);", button_element)
                time.sleep(0.5)
                
                if popup_url:
                    # showPopup인 경우 직접 새 창 열기 시도
                    try:
                        driver.execute_script(f"window.open('{popup_url}', '_blank');")
                        time.sleep(3)
                        print(f"  ✓ window.open으로 새 창 열기 시도 완료")
                    except Exception as e:
                        print(f"  ⚠ window.open 실패, 버튼 클릭으로 시도: {e}")
                        driver.execute_script("arguments[0].click();", button_element)
                        time.sleep(3)
                else:
                    # 일반 클릭
                    driver.execute_script("arguments[0].click();", button_element)
                    time.sleep(3)
                
                print(f"  ✓ 버튼 클릭 완료")
            except Exception as e:
                print(f"  ⚠ 버튼 클릭 실패: {e}")
                # 클릭 실패 시 showPopup URL이 있으면 직접 접근
                if popup_url:
                    print(f"  → 클릭 실패, URL 직접 접근 시도: {popup_url}")
                    try:
                        driver.get(popup_url)
                        time.sleep(2)
                        # 현재 창에서 내용 추출
                        new_window_soup = BeautifulSoup(driver.page_source, 'lxml')
                        self.save_debug_html(new_window_soup, filename="debug_fsb_new_window_direct.html")
                        
                        # 공통 함수로 개정정보 추출
                        result = self._extract_revision_info_from_soup(new_window_soup)

                        # 개정문 파일에서 개정내용 추출
                        try:
                            popup_revision_content = _download_revision_file_from_popup()
                            if popup_revision_content:
                                result['revision_content'] = popup_revision_content
                        except Exception as e3:
                            print(f"  ⚠ 개정문 파일 처리 중 오류: {e3}")
                        
                        # 원래 페이지로 돌아가기
                        driver.back()
                        time.sleep(1)
                        return result
                    except Exception as e2:
                        print(f"  ⚠ 직접 URL 접근 실패: {e2}")
                
                return {
                    'revision_reason': '',
                    'enforcement_date': '',
                    'promulgation_date': '',
                    'revision_content': '',
                }
            
            # 새 창이 열렸는지 확인
            all_windows_after = set(driver.window_handles)
            new_windows = all_windows_after - all_windows_before
            
            if not new_windows:
                print(f"  ⚠ 새 창이 열리지 않았습니다")
                # showPopup이 팝업으로 열렸을 수 있으므로 현재 창에서 직접 URL 접근 시도
                # popup_url이 없으면 버튼에서 다시 추출 시도
                if not popup_url and js_code and 'showPopup' in js_code:
                    popup_url_match = re.search(r"showPopup\s*\(\s*['\"]([^'\"]+)['\"]", js_code)
                    if popup_url_match:
                        popup_url = popup_url_match.group(1)
                        if not popup_url.startswith('http'):
                            popup_url = urljoin(self.BASE_URL, popup_url)
                        print(f"  → showPopup URL 재추출: {popup_url}")
                
                if popup_url:
                    print(f"  → 팝업 URL로 직접 접근 시도: {popup_url}")
                    try:
                        driver.get(popup_url)
                        time.sleep(2)
                        # 현재 창에서 내용 추출
                        new_window_soup = BeautifulSoup(driver.page_source, 'lxml')
                        self.save_debug_html(new_window_soup, filename="debug_fsb_new_window_direct.html")
                        
                        # 공통 함수로 개정정보 추출
                        result = self._extract_revision_info_from_soup(new_window_soup)

                        # 개정문 파일에서 개정내용 추출
                        try:
                            popup_revision_content = _download_revision_file_from_popup()
                            if popup_revision_content:
                                result['revision_content'] = popup_revision_content
                        except Exception as e3:
                            print(f"  ⚠ 개정문 파일 처리 중 오류: {e3}")
                        
                        # 원래 페이지로 돌아가기
                        driver.back()
                        time.sleep(1)
                        return result
                    except Exception as e:
                        print(f"  ⚠ 직접 URL 접근 실패: {e}")
                
                return {
                    'revision_reason': '',
                    'enforcement_date': '',
                    'promulgation_date': '',
                    'revision_content': '',
                }
            
            # 새 창으로 전환
            new_window_handle = new_windows.pop()
            driver.switch_to.window(new_window_handle)
            print(f"  ✓ 새 창으로 전환 완료")
            
            # 새 창 로드 대기
            time.sleep(2)
            
            # 새 창의 HTML 저장 (디버깅용)
            try:
                new_window_soup = BeautifulSoup(driver.page_source, 'lxml')
                self.save_debug_html(new_window_soup, filename="debug_fsb_new_window.html")
                print(f"  ✓ 새 창 HTML 저장 완료")
            except:
                pass
            
            # 새 창의 내용 추출 (테이블 구조 파싱)
            try:
                # BeautifulSoup으로 테이블 구조 파싱
                new_window_soup = BeautifulSoup(driver.page_source, 'lxml')
                
                # 공통 함수로 개정정보 추출
                result = self._extract_revision_info_from_soup(new_window_soup)
                revision_reason = result['revision_reason']
                enforcement_date = result['enforcement_date']
                promulgation_date = result['promulgation_date']

                # 개정문 파일에서 개정내용 추출
                try:
                    popup_revision_content = _download_revision_file_from_popup()
                    if popup_revision_content:
                        revision_content = popup_revision_content
                except Exception as e3:
                    print(f"  ⚠ 개정문 파일 처리 중 오류: {e3}")
                
            except Exception as e:
                print(f"  ⚠ 새 창 내용 추출 중 오류: {e}")
                import traceback
                traceback.print_exc()
                # 오류 발생 시 빈 값으로 유지
                revision_reason = ""
                enforcement_date = ""
                promulgation_date = ""
            
            # 원래 창으로 복귀
            driver.close()  # 새 창 닫기
            driver.switch_to.window(original_window)
            print(f"  ✓ 원래 창으로 복귀 완료")
            
        except Exception as e:
            print(f"  ⚠ 새 창 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()
            # 원래 창으로 복귀 시도
            try:
                if original_window:
                    driver.switch_to.window(original_window)
            except:
                pass
        
        return {
            'revision_reason': revision_reason,
            'enforcement_date': enforcement_date,
            'promulgation_date': promulgation_date,
            'revision_content': revision_content,
        }
    
    def extract_law_info_from_content(self, content: str, title: str = "") -> Dict:
        """파일 내용에서 법규 정보 추출 (규정명, 기관명, 본문, 제정일, 최근 개정일)"""
        import re
        
        info = {
            'regulation_name': title,
            'organization': '저축은행중앙회',
            'content': content,
            'enactment_date': '',
            'revision_date': ''
        }
        
        if not content:
            return info
        
        # 제정일 추출
        enactment_patterns = [
            r'제\s*정\s+(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)',
            r'제\s*정\s+(\d{4}\.\d{1,2}\.\d{1,2}\.?)',
            r'제\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)\s*제\s*정',
        ]
        
        for pattern in enactment_patterns:
            match = re.search(pattern, content[:2000], re.IGNORECASE)
            if match:
                date_str = match.group(1) if match.groups() else match.group(0)
                date_str = re.sub(r'[년월일]', '', date_str).strip()
                date_str = date_str.replace(' ', '').replace('-', '.')
                if date_str and not date_str.endswith('.'):
                    if re.match(r'\d{4}\.\d{1,2}\.\d{1,2}$', date_str):
                        date_str += '.'
                info['enactment_date'] = date_str
                break
        
        # 최근 개정일 추출
        revision_patterns = [
            r'개\s*정\s+(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)',
            r'개\s*정\s+(\d{4}\.\d{1,2}\.\d{1,2}\.?)',
            r'최\s*근\s*개\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)\s*개\s*정',
        ]
        
        revision_dates_raw = []
        for pattern in revision_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1) if match.groups() else match.group(0)
                date_str = re.sub(r'[년월일]', '', date_str).strip()
                date_str = date_str.replace(' ', '').replace('-', '.')
                date_str = date_str.rstrip('.')
                if date_str:
                    revision_dates_raw.append(date_str)
        
        if revision_dates_raw:
            parsed_dates = []
            seen = set()
            for date_str in revision_dates_raw:
                parts = date_str.split('.')
                if len(parts) >= 3:
                    try:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        date_key = (year, month, day)
                        if date_key not in seen:
                            seen.add(date_key)
                            parsed_dates.append((year, month, day, date_str))
                    except ValueError:
                        continue
            
            if parsed_dates:
                latest = max(parsed_dates, key=lambda x: (x[0], x[1], x[2]))
                latest_date_str = f"{latest[3]}"
                if not latest_date_str.endswith('.'):
                    latest_date_str += '.'
                info['revision_date'] = latest_date_str
        
        return info
    
    def extract_model_guidelines_list(self, soup: BeautifulSoup) -> List[Dict]:
        """모범규준 목록 페이지에서 항목 추출"""
        items: List[Dict] = []
        
        if not soup:
            return items
        
        try:
            # 테이블 구조 찾기 (우선 시도)
            table = soup.find('table')
            
            if table:
                # 테이블 행 찾기
                rows = table.find_all('tr')
                
                for row in rows:
                    item = {}
                    cells = row.find_all('td')
                    
                    if len(cells) >= 2:
                        # 첫 번째 셀: 항목명
                        title_cell = cells[0]
                        title_elem = title_cell.find('a') or title_cell.find('strong') or title_cell
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            if title and title not in ['항목명', '제목']:
                                item['title'] = title
                        
                        # 두 번째 셀: 부서 정보
                        if len(cells) >= 2:
                            dept_cell = cells[1]
                            dept_text = dept_cell.get_text(strip=True)
                            if dept_text and dept_text not in ['부서', '소관부서']:
                                item['department'] = dept_text
                        
                        # 다운로드 링크 찾기 (모든 셀에서)
                        for cell in cells:
                            download_elem = cell.find('a', string=re.compile('다운로드'))
                            if not download_elem:
                                # href에 download가 포함된 링크 찾기
                                download_elem = cell.find('a', href=re.compile('download|\.(pdf|hwp|doc)', re.I))
                            
                            if download_elem:
                                download_link = download_elem.get('href', '')
                                if download_link:
                                    if not download_link.startswith('http'):
                                        download_link = urljoin("https://www.fsb.or.kr", download_link)
                                    item['download_link'] = download_link
                                    break
                        
                        if item.get('title'):
                            items.append(item)
            
            # 테이블이 없는 경우 다른 구조 시도
            if not items:
                # 모든 "다운로드" 링크 찾기
                download_links = soup.find_all('a', string=re.compile('다운로드'))
                
                for download_link in download_links:
                    # 부모 요소에서 제목 찾기
                    parent = download_link.find_parent('tr') or download_link.find_parent('li') or download_link.find_parent('div')
                    if parent:
                        # 제목 찾기 (다운로드 링크가 아닌 다른 링크 또는 텍스트)
                        title_elem = None
                        for elem in parent.find_all(['a', 'strong', 'span', 'div']):
                            text = elem.get_text(strip=True)
                            if text and '다운로드' not in text and len(text) > 5:
                                title_elem = elem
                                break
                        
                        if not title_elem:
                            # 직접 텍스트 추출
                            all_text = parent.get_text(strip=True)
                            lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                            for line in lines:
                                if '다운로드' not in line and len(line) > 5:
                                    title_elem = type('obj', (object,), {'get_text': lambda: line})()
                                    break
                        
                        if title_elem:
                            title = title_elem.get_text(strip=True) if hasattr(title_elem, 'get_text') else str(title_elem)
                            href = download_link.get('href', '')
                            if href:
                                if not href.startswith('http'):
                                    href = urljoin("https://www.fsb.or.kr", href)
                                
                                item = {
                                    'title': title,
                                    'download_link': href
                                }
                                
                                # 부서 정보 찾기
                                dept_elem = parent.find('span', class_=re.compile('dept|부서', re.I))
                                if dept_elem:
                                    item['department'] = dept_elem.get_text(strip=True)
                                
                                items.append(item)
        
        except Exception as e:
            print(f"  ⚠ 항목 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return items
    
    def extract_model_guidelines_list_with_selenium(self, driver) -> List[Dict]:
        """Selenium을 사용하여 모범규준 목록 페이지에서 항목 추출
        구조: /html/body/div/div/div[6]/div[2]/div/div/div[2]/ul/li[N]
        - 제목: li 내부의 텍스트
        - 소관부서: li/p[2]
        - 다운로드 링크: li/div/a
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        items: List[Dict] = []
        
        try:
            driver.get(self.MODEL_GUIDELINES_URL)
            time.sleep(3)  # 페이지 로딩 대기
            
            # 페이지 소스로 BeautifulSoup 생성
            soup = BeautifulSoup(driver.page_source, 'lxml')
            
            # 디버그 HTML 저장
            self.save_debug_html(soup, "debug_model_list.html")
            
            # ul 요소 찾기
            try:
                # ul 요소 찾기 (여러 방법 시도)
                ul_elem = None
                try:
                    # XPath로 ul 찾기
                    ul_elem = driver.find_element(By.XPATH, "/html/body/div/div/div[6]/div[2]/div/div/div[2]/ul")
                except:
                    try:
                        # CSS Selector로 시도
                        ul_elem = driver.find_element(By.CSS_SELECTOR, "div[class*='list'], ul[class*='list'], ul")
                    except:
                        pass
                
                if not ul_elem:
                    print(f"  ⚠ ul 요소를 찾을 수 없습니다.")
                    return items
                
                # li 요소들 찾기
                li_elements = ul_elem.find_elements(By.TAG_NAME, "li")
                print(f"  → 발견된 li 요소: {len(li_elements)}개")
                
                for idx, li_elem in enumerate(li_elements, 1):
                    try:
                        item = {}
                        
                        # 제목 추출 (li 내부의 첫 번째 텍스트 또는 링크)
                        try:
                            # p[1] 또는 첫 번째 텍스트 요소 찾기
                            title_elem = None
                            try:
                                title_elem = li_elem.find_element(By.XPATH, "./p[1]")
                            except:
                                try:
                                    title_elem = li_elem.find_element(By.XPATH, "./div[1]")
                                except:
                                    # li의 직접 텍스트 사용
                                    title_text = li_elem.text.strip()
                                    if title_text:
                                        lines = [line.strip() for line in title_text.split('\n') if line.strip()]
                                        if lines:
                                            item['title'] = lines[0]
                            else:
                                item['title'] = title_elem.text.strip()
                        except Exception as e:
                            print(f"  ⚠ 제목 추출 실패 (li[{idx}]): {e}")
                            continue
                        
                        if not item.get('title'):
                            continue
                        
                        # 소관부서 추출 (p[2])
                        try:
                            dept_elem = li_elem.find_element(By.XPATH, "./p[2]")
                            item['department'] = dept_elem.text.strip()
                        except:
                            try:
                                # 대체 방법: p 요소 중 두 번째 찾기
                                p_elems = li_elem.find_elements(By.TAG_NAME, "p")
                                if len(p_elems) >= 2:
                                    item['department'] = p_elems[1].text.strip()
                            except:
                                pass
                        
                        # 다운로드 링크 추출 (div/a)
                        try:
                            download_elem = li_elem.find_element(By.XPATH, "./div/a")
                            download_link = download_elem.get_attribute('href')
                            if download_link:
                                if not download_link.startswith('http'):
                                    download_link = urljoin("https://www.fsb.or.kr", download_link)
                                item['download_link'] = download_link
                        except:
                            try:
                                # 대체 방법: div 내부의 a 요소 찾기
                                div_elem = li_elem.find_element(By.XPATH, "./div")
                                download_elem = div_elem.find_element(By.TAG_NAME, "a")
                                download_link = download_elem.get_attribute('href')
                                if download_link:
                                    if not download_link.startswith('http'):
                                        download_link = urljoin("https://www.fsb.or.kr", download_link)
                                    item['download_link'] = download_link
                            except:
                                pass
                        
                        if item.get('title'):
                            items.append(item)
                            print(f"  ✓ 항목 추출: {item.get('title', '')[:50]}... (부서: {item.get('department', 'N/A')})")
                    
                    except Exception as e:
                        print(f"  ⚠ li[{idx}] 항목 추출 중 오류: {e}")
                        continue
                
            except Exception as e:
                print(f"  ⚠ 목록 구조 파싱 중 오류: {e}")
                import traceback
                traceback.print_exc()
        
        except Exception as e:
            print(f"  ⚠ 목록 페이지 접근 중 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return items
    
    def crawl_model_guidelines(
        self, 
        target_items: List[Dict],
        driver,
        limit: int = 0, 
        download_files: bool = True,
        content_limit: int = 0
    ) -> List[Dict]:
        """모범규준 목록을 스크래핑"""
        all_results: List[Dict] = []
        
        try:
            # 목록 페이지에서 항목 추출
            print(f"\n=== 모범규준 목록 추출 중 ===")
            items = self.extract_model_guidelines_list_with_selenium(driver)
            
            if not items:
                print(f"⚠ 항목을 찾을 수 없습니다.")
                return all_results
            
            print(f"✓ {len(items)}개의 항목 발견")
            
            # CSV 필터링 (CSV가 있는 경우)
            if target_items:
                print(f"  → CSV 필터링 적용 ({len(target_items)}개 대상)")
                filtered_items = []
                matched_titles = set()
                
                # 항목을 정규화된 이름으로 매핑
                items_map = {}
                for item in items:
                    title = item.get('title', '')
                    normalized_title = self._normalize_title(title)
                    if normalized_title:
                        items_map[normalized_title] = item
                
                # CSV 목록과 매칭
                for target in target_items:
                    target_name = target.get('law_name', '')
                    normalized_target = self._normalize_title(target_name)
                    
                    matched_item = None
                    # 정확히 일치하는 경우
                    if normalized_target in items_map:
                        matched_item = items_map[normalized_target]
                    else:
                        # 부분 매칭 시도
                        for item_key, item in items_map.items():
                            if normalized_target in item_key or item_key in normalized_target:
                                matched_item = item
                                break
                    
                    if matched_item:
                        # 항목 복사 및 CSV 정보 추가
                        result_item = dict(matched_item)
                        result_item['target_name'] = target_name
                        result_item['target_category'] = target.get('category', '')
                        result_item['regulation_name'] = target_name
                        result_item['organization'] = '저축은행중앙회'
                        result_item['content'] = ''
                        result_item['file_name'] = ''
                        result_item['enactment_date'] = ''
                        result_item['revision_date'] = ''
                        filtered_items.append(result_item)
                        matched_titles.add(target_name)
                        print(f"  ✓ 매칭: '{matched_item.get('title', '')}' → '{target_name}'")
                    else:
                        print(f"  ✗ 매칭 안됨: '{target_name}'")
                
                items = filtered_items
                print(f"  ✓ 필터링 후 {len(items)}개 항목")
            
            # 제한 적용
            if limit > 0 and len(items) > limit:
                items = items[:limit]
                print(f"  → 제한 적용: {limit}개 항목만 처리")
            
            # 각 항목 처리
            for idx, item in enumerate(items, 1):
                title = item.get('title', 'N/A')
                regulation_name = item.get('target_name') or item.get('regulation_name', title)
                print(f"\n[{idx}/{len(items)}] {regulation_name[:50]}...")
                
                # 파일 다운로드
                if download_files and item.get('download_link'):
                    download_link = item.get('download_link')
                    print(f"  → 파일 다운로드 시도: {download_link}")
                    
                    # 다운로드 전 현재 파일 목록 저장
                    files_before = set(f.name for f in self.current_dir.glob("*") if f.is_file())
                    
                    # CDP 다운로드 동작 설정
                    try:
                        driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                            'behavior': 'allow',
                            'downloadPath': str(self.current_dir)
                        })
                    except Exception as cdp_error:
                        print(f"  ⚠ CDP 설정 실패 (계속 진행): {cdp_error}")
                    
                    # 다운로드 링크 클릭
                    try:
                        from selenium.webdriver.common.by import By
                        # 다운로드 링크를 직접 열기
                        driver.get(download_link)
                        time.sleep(2)  # 다운로드 시작 대기
                    except Exception as e:
                        print(f"  ⚠ 다운로드 링크 접근 실패: {e}")
                    
                    # 다운로드 완료 대기
                    max_wait = 30
                    waited = 0
                    downloaded_file = None
                    
                    while waited < max_wait:
                        downloaded_files = list(self.current_dir.glob("*"))
                        crdownload_files = [f for f in downloaded_files if f.name.endswith('.crdownload')]
                        
                        if crdownload_files:
                            print(f"  → 다운로드 진행 중... ({waited}초)")
                        else:
                            # 새 파일 찾기
                            for f in downloaded_files:
                                if f.is_file() and not f.name.endswith('.crdownload'):
                                    if f.name not in files_before:
                                        if not downloaded_file or f.stat().st_mtime > downloaded_file.stat().st_mtime:
                                            downloaded_file = f
                            
                            if downloaded_file:
                                print(f"  ✓ 새 파일 발견: {downloaded_file.name}")
                                break
                        
                        time.sleep(1)
                        waited += 1
                    
                    if downloaded_file and downloaded_file.exists():
                        # 파일명 생성 (규정명.확장자)
                        ext = downloaded_file.suffix or '.hwp'
                        safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                        safe_reg_name = safe_reg_name.replace(' ', '_')
                        safe_filename = f"{safe_reg_name}{ext}"
                        new_file_path = self.current_dir / safe_filename
                        
                        # 파일 이동/이름 변경
                        import shutil
                        if str(downloaded_file) != str(new_file_path):
                            if new_file_path.exists():
                                new_file_path.unlink()
                            shutil.move(downloaded_file, new_file_path)
                            print(f"  ✓ 파일 저장: {new_file_path}")
                        
                        item['file_name'] = safe_filename
                        
                        # 이전 파일과 비교
                        previous_file_path = self.previous_dir / safe_filename
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
                        
                        # HWP 파일 내용 추출
                        file_ext = Path(new_file_path).suffix.lower()
                        if file_ext == '.hwp':
                            print(f"  → HWP 내용 추출 중...")
                            file_content = self.extract_hwp_content(str(new_file_path))
                            
                            if file_content:
                                # 법규 정보 추출
                                law_info = self.extract_law_info_from_content(file_content, regulation_name)
                                if law_info.get('regulation_name'):
                                    item['regulation_name'] = law_info.get('regulation_name')
                                if law_info.get('enactment_date'):
                                    item['enactment_date'] = law_info.get('enactment_date')
                                # revision_date는 select에서 추출한 값이 우선 (이미 있으면 덮어쓰지 않음)
                                if law_info.get('revision_date') and not item.get('revision_date'):
                                    item['revision_date'] = law_info.get('revision_date')
                                
                                # 본문 설정 (제한 적용, 최대 4000자)
                                content = file_content.replace("\r\n", "\n").replace("\r", "\n")
                                max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                if len(content) > max_length:
                                    item['content'] = content[:max_length]
                                else:
                                    item['content'] = content
                                print(f"  ✓ 파일 내용 추출 완료 ({len(file_content)}자)")
                            else:
                                print(f"  ⚠ HWP 내용 추출 실패")
                        elif file_ext == '.pdf':
                            print(f"  → PDF 내용 추출 중...")
                            file_content = self.extract_pdf_content(str(new_file_path))
                            if file_content:
                                content = file_content.replace("\r\n", "\n").replace("\r", "\n")
                                max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                if len(content) > max_length:
                                    item['content'] = content[:max_length]
                                else:
                                    item['content'] = content
                                print(f"  ✓ 파일 내용 추출 완료 ({len(file_content)}자)")
                    else:
                        print(f"  ⚠ 파일 다운로드 실패 (파일을 찾을 수 없음)")
                    
                    # 목록 페이지로 돌아가기
                    driver.get(self.MODEL_GUIDELINES_URL)
                    time.sleep(1)
                
                all_results.append(item)
                time.sleep(self.delay)
        
        except Exception as e:
            print(f"✗ 모범규준 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        
        return all_results
    
    def crawl_sblaw_portal(
        self, limit: int = 0, download_files: bool = True, content_limit: int = 0
    ) -> List[Dict]:
        """
        SBLAW 표준규정·약관 연혁관리시스템 및 모범규준 스크래핑
        CSV의 '구분' 값에 따라 자동으로 분기 처리:
        - '감독규정': SBLAW 포탈 (로그인 필요)
        - '모범규준': 모범규준 페이지 (로그인 불필요)
        
        Args:
            limit: 가져올 개수 제한 (0=전체)
            download_files: 파일 다운로드 및 내용 추출 여부
            content_limit: 본문 길이 제한 (0=제한 없음, 문자 수)
        """
        # 스크래퍼 시작 시 current를 previous로 백업
        self._backup_current_to_previous()
        self._clear_diffs_directory()
        
        all_results = []
        driver = None
        
        # CSV에서 구분값에 따라 항목 분리
        supervision_items = []  # 감독규정
        model_items = []  # 모범규준
        
        if self.target_laws:
            for target in self.target_laws:
                category = target.get('category', '').strip()
                if category == '모범규준':
                    model_items.append(target)
                else:
                    supervision_items.append(target)
        
        print(f"\n=== CSV 항목 분류 ===")
        print(f"  감독규정: {len(supervision_items)}개")
        print(f"  모범규준: {len(model_items)}개")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            
            chrome_options = Options()
            # 헤드리스 모드 활성화 (크롬 창이 열리지 않도록)
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ko-KR')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            # HTTP 사이트에서도 다운로드 허용
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-web-security')
            # 다운로드 관련 추가 설정
            chrome_options.add_argument('--disable-features=DownloadBubble,DownloadBubbleV2')
            # 안전하지 않은 다운로드 차단 해제
            chrome_options.add_argument('--disable-features=SafeBrowsing')
            chrome_options.add_argument('--safebrowsing-disable-download-protection')
            prefs = {
                "download.default_directory": os.path.abspath(str(self.current_dir)),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True,  # PDF를 외부에서 열기
                "safebrowsing.enabled": False,  # SafeBrowsing 비활성화 (안전하지 않은 다운로드 허용)
                "safebrowsing.disable_download_protection": True,  # 다운로드 보호 비활성화
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.automatic_downloads": 1,  # 자동 다운로드 허용
                "profile.content_settings.exceptions.automatic_downloads": {
                    "*": {
                        "setting": 1  # 모든 사이트에서 자동 다운로드 허용
                    }
                }
            }
            chrome_options.add_experimental_option("prefs", prefs)
            # 폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용 (SeleniumManager 우회)
            driver = self._create_webdriver(chrome_options)
            
            # Chrome DevTools Protocol로 다운로드 동작 설정 (드라이버 생성 직후)
            try:
                driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                    'behavior': 'allow',
                    'downloadPath': str(self.current_dir)
                })
                print("✓ CDP 다운로드 동작 설정 완료")
            except Exception as cdp_error:
                print(f"⚠ CDP 설정 실패 (계속 진행): {cdp_error}")
            
            print("Selenium 드라이버 생성 완료")
        except Exception as e:
            print(f"⚠ Selenium 드라이버 생성 실패: {e}")
            return all_results
        
        try:
            # 1. 모범규준 스크래핑 (로그인 불필요)
            if model_items:
                print(f"\n{'='*60}")
                print(f"=== 모범규준 스크래핑 시작 ({len(model_items)}개) ===")
                print(f"{'='*60}")
                model_results = self.crawl_model_guidelines(
                    target_items=model_items,
                    driver=driver,
                    limit=limit,
                    download_files=download_files,
                    content_limit=content_limit
                )
                all_results.extend(model_results)
                print(f"\n✓ 모범규준 스크래핑 완료: {len(model_results)}개")
            
            # 2. 감독규정 스크래핑 (로그인 필요)
            if supervision_items:
                print(f"\n{'='*60}")
                print(f"=== 감독규정 스크래핑 시작 ({len(supervision_items)}개) ===")
                print(f"{'='*60}")
                
                # 로그인 처리
                print("\n=== 로그인 처리 ===")
                if not self._login(driver):
                    print("⚠ 로그인 실패. 감독규정 스크래핑을 건너뜁니다.")
                else:
            
                    # 로그인 후 규정 목록 페이지 접근
                    list_url = "http://sblaw.fsb.or.kr/lmxsrv/law/lawListManager.do?LAWGROUP=3"
                    print(f"\n=== 규정 목록 페이지 접근 ===")
                    print(f"  → URL: {list_url}")
                    driver.get(list_url)
                    time.sleep(3)
                    
                    # 디버깅: 첫 페이지 HTML 저장
                    main_soup = BeautifulSoup(driver.page_source, 'lxml')
                    self.save_debug_html(main_soup, filename="debug_fsb_main.html")
                    
                    # 트리 iframe에서 링크 추출
                    print("\n=== 트리 iframe에서 규정 링크 추출 ===")
                    tree_links = self.extract_tree_links(driver)
                    print(f"트리에서 추출된 링크: {len(tree_links)}개")
                    
                    # CSV 목록이 있으면 필터링
                    if supervision_items and tree_links:
                        print(f"\n=== CSV 목록 기반 필터링 ===")
                        filtered_links = []
                        matched_titles = set()
                        
                        # 트리 링크를 정규화된 이름으로 매핑
                        tree_links_map = {}
                        for link in tree_links:
                            title = link.get('title', '') or link.get('regulation_name', '')
                            normalized_title = self._normalize_title(title)
                            if normalized_title:
                                tree_links_map[normalized_title] = link
                        
                        # CSV 목록과 매칭 (감독규정만)
                        for target in supervision_items:
                            target_name = target.get('law_name', '')
                            normalized_target = self._normalize_title(target_name)
                            
                            matched_link = None
                            # 정확히 일치하는 경우
                            if normalized_target in tree_links_map:
                                matched_link = tree_links_map[normalized_target]
                            else:
                                # 부분 매칭 시도
                                for tree_key, link in tree_links_map.items():
                                    if normalized_target in tree_key or tree_key in normalized_target:
                                        matched_link = link
                                        break
                            
                            if matched_link:
                                # 링크 복사 및 CSV 정보 추가
                                item = dict(matched_link)
                                item['target_name'] = target_name
                                item['target_category'] = target.get('category', '')
                                item['regulation_name'] = target_name  # CSV의 원본 이름 사용
                                filtered_links.append(item)
                                matched_titles.add(target_name)
                                print(f"  ✓ 매칭: '{matched_link.get('title', '')}' → '{target_name}'")
                            else:
                                print(f"  ✗ 매칭 안됨: '{target_name}'")
                
                        tree_links = filtered_links
                        print(f"필터링 결과: {len(tree_links)}개 항목 (CSV 목록: {len(supervision_items)}개)")
                        
                        # CSV에 있지만 매칭되지 않은 항목 확인
                        missing = [t['law_name'] for t in supervision_items if t['law_name'] not in matched_titles]
                        if missing:
                            print(f"⚠ 매칭되지 않은 CSV 항목 ({len(missing)}개):")
                            for name in missing[:5]:  # 처음 5개만 표시
                                print(f"    - {name}")
                            if len(missing) > 5:
                                print(f"    ... 외 {len(missing) - 5}개")
                    
                    supervision_results = tree_links
                    
                    # 제한 적용
                    if limit > 0 and len(supervision_results) > limit:
                        supervision_results = supervision_results[:limit]
                        print(f"제한 적용: 처음 {limit}개 항목만 사용")
                    
                    # 트리 링크 클릭하여 상세 내용 추출
                    if supervision_results:
                        print(f"\n=== 트리 링크 클릭 및 상세 내용 추출 시작 ===")
                        for idx, item in enumerate(supervision_results, 1):
                            regulation_name = item.get('target_name') or item.get('regulation_name') or item.get('title', '')
                            print(f"[{idx}/{len(supervision_results)}] {regulation_name[:50]}... 처리 중")
                    
                            try:
                                detail_soup = self.click_tree_link_and_extract(driver, item)
                                if detail_soup:
                                    # iframe이 없는 경우인지 확인
                                    has_no_iframe = getattr(detail_soup, '_no_iframe', False)
                                    
                                    if has_no_iframe:
                                        # iframe이 없는 경우: 메인 프레임에서 직접 추출
                                        print(f"  → iframe 없는 구조 감지, 메인 프레임에서 직접 추출")
                                        driver.switch_to.default_content()
                                        time.sleep(1)
                                        
                                        # 테이블에서 정보 추출
                                        try:
                                            # 테이블 찾기 (.file_content > table.brdComView)
                                            table = detail_soup.find('table', class_='brdComView')
                                            if table:
                                                rows = table.find_all('tr')
                                                for row in rows:
                                                    th = row.find('th')
                                                    td = row.find('td')
                                                    if th and td:
                                                        th_text = th.get_text(strip=True)
                                                        td_text = td.get_text(strip=True)
                                                        
                                                        # 시행일 추출 (참고용, 새 창에서도 가져옴)
                                                        if '시행일' in th_text:
                                                            date_match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', td_text)
                                                            if date_match:
                                                                year = date_match.group(1)
                                                                month = str(int(date_match.group(2))).zfill(2)
                                                                day = str(int(date_match.group(3))).zfill(2)
                                                                item['enforcement_date'] = f"{year}-{month}-{day}"
                                                                print(f"  ✓ 시행일 추출: {item['enforcement_date']} (원본: '{td_text}')")
                                        except Exception as e:
                                            print(f"  ⚠ 테이블에서 정보 추출 실패: {e}")
                                        
                                        # select 요소에서 최근 개정일 추출 (최우선)
                                        try:
                                            date_select = driver.find_element(By.CSS_SELECTOR, "select#histroySeq, select[name='SEQ_HISTORY']")
                                            from selenium.webdriver.support.ui import Select
                                            select = Select(date_select)
                                            options = select.options
                                            
                                            if options:
                                                first_option_text = options[0].text.strip()
                                                # 최근 개정일은 select에서 추출한 값 사용
                                                item['revision_date'] = self._normalize_date_text(first_option_text)
                                                print(f"  ✓ 최근 개정일 추출 (select): {item['revision_date']} (원본: '{first_option_text}')")
                                        except Exception as e:
                                            print(f"  ⚠ select 요소를 찾을 수 없음: {e}")
                                        
                                        # 본문은 PDF로 제공되므로 파일 다운로드 후 추출
                                        # 일단 빈 문자열로 설정
                                        item['content'] = ""
                                        print(f"  ⚠ 본문은 PDF 파일로 제공되므로 파일 다운로드 후 추출 예정")
                                        
                                        # 파일 다운로드 버튼 찾기 (iframe 없는 구조)
                                        # 버튼 검증 헬퍼 함수: img title로 확인
                                        def verify_download_button_by_img_title(element, expected_titles):
                                            """버튼 내부의 img 태그 title로 검증 (전문 다운로드 또는 개정문 다운로드)"""
                                            try:
                                                img = element.find_element(By.TAG_NAME, "img")
                                                img_title = img.get_attribute('title') or img.get_attribute('alt') or ''
                                                for expected in expected_titles:
                                                    if expected in img_title:
                                                        return True
                                            except:
                                                pass
                                            return False
                                        
                                        download_button = None
                                        try:
                                            # 전문 다운로드 버튼 찾기 (href에 fileDown 포함)
                                            candidates = driver.find_elements(By.CSS_SELECTOR, ".btn_box .kor_btn a[href*='fileDown'], .btnDiv.kor_btn a[href*='fileDown']")
                                            for candidate in candidates:
                                                if verify_download_button_by_img_title(candidate, ['전문 다운로드', '전문']):
                                                    download_button = candidate
                                                    print(f"  ✓ 전문 다운로드 버튼 발견 (title 검증 통과)")
                                                    break
                                        except:
                                            pass
                                        
                                        if not download_button:
                                            try:
                                                # XPath로 시도
                                                candidates = driver.find_elements(By.XPATH, "//div[@class='btn_box']//div[@class='kor_btn']//a[contains(@href, 'fileDown')]")
                                                for candidate in candidates:
                                                    if verify_download_button_by_img_title(candidate, ['전문 다운로드', '전문']):
                                                        download_button = candidate
                                                        print(f"  ✓ 전문 다운로드 버튼 발견 (XPath, title 검증 통과)")
                                                        break
                                            except Exception as e:
                                                print(f"  ⚠ 다운로드 버튼을 찾을 수 없음: {e}")
                                        
                                        # 최후의 수단: 모든 버튼을 검사하여 img title로 찾기
                                        if not download_button:
                                            try:
                                                all_buttons = driver.find_elements(By.CSS_SELECTOR, ".btn_box a, .btnDiv a")
                                                for btn in all_buttons:
                                                    if verify_download_button_by_img_title(btn, ['전문 다운로드', '전문']):
                                                        download_button = btn
                                                        print(f"  ✓ 전문 다운로드 버튼 발견 (img title로 검색)")
                                                        break
                                            except:
                                                pass
                                    else:
                                        # iframe이 있는 경우: 기존 로직 사용
                                        # 본문 추출 (#lawDetailContent iframe 내부)
                                        content = detail_soup.get_text(separator='\n', strip=True)
                                        if content and len(content) > 20:
                                            # 개행 유지, 4000자 제한
                                            content = content.replace("\r\n", "\n").replace("\r", "\n")
                                            max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                            if len(content) > max_length:
                                                content = content[:max_length]
                                            item['content'] = content
                                            print(f"  ✓ 본문 추출 완료 ({len(content)}자)")
                                        
                                        # 날짜 정보 추출 (select 요소에서)
                                        driver.switch_to.default_content()
                                        time.sleep(1)
                                        
                                        try:
                                            # select 요소 찾기
                                            date_select = driver.find_element(By.XPATH, "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[2]/div/select")
                                            from selenium.webdriver.support.ui import Select
                                            select = Select(date_select)
                                            options = select.options
                                            
                                            if options:
                                                # 가장 위에 있는 옵션 (첫 번째) = 최근 개정일
                                                first_option_text = options[0].text.strip()
                                                item['revision_date'] = self._normalize_date_text(first_option_text)
                                                print(f"  ✓ 최근 개정일 추출: {item['revision_date']} (원본: '{first_option_text}')")
                                                
                                                # '제정' 텍스트가 있는 옵션 찾기
                                                for opt in options:
                                                    opt_text = opt.text.strip()
                                                    if '제정' in opt_text:
                                                        item['enactment_date'] = self._normalize_date_text(opt_text)
                                                        print(f"  ✓ 제정일 추출: {item['enactment_date']} (원본: '{opt_text}')")
                                                        break
                                        except Exception as e:
                                            print(f"  ⚠ 날짜 select 요소를 찾을 수 없음: {e}")
                                        
                                        # 파일 다운로드 버튼 찾기 (메인 프레임에서)
                                        # 버튼 검증 헬퍼 함수: img title로 확인
                                        def verify_download_button_by_img_title_iframe(element, expected_titles):
                                            """버튼 내부의 img 태그 title로 검증 (전문 다운로드 또는 개정문 다운로드)"""
                                            try:
                                                img = element.find_element(By.TAG_NAME, "img")
                                                img_title = img.get_attribute('title') or img.get_attribute('alt') or ''
                                                for expected in expected_titles:
                                                    if expected in img_title:
                                                        return True
                                            except:
                                                pass
                                            return False
                                        
                                        download_button = None
                                        try:
                                            # CSS Selector로 시도
                                            candidate = driver.find_element(By.CSS_SELECTOR, "#contents_wrap > div > div.btn_box > div > a:nth-child(2)")
                                            if candidate and verify_download_button_by_img_title_iframe(candidate, ['전문 다운로드', '전문']):
                                                download_button = candidate
                                                print(f"  ✓ 전문 다운로드 버튼 발견 (iframe 있는 경우, CSS 셀렉터, title 검증 통과)")
                                        except:
                                            try:
                                                # XPath로 시도
                                                candidate = driver.find_element(By.XPATH, "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[3]/div/a[2]")
                                                if candidate and verify_download_button_by_img_title_iframe(candidate, ['전문 다운로드', '전문']):
                                                    download_button = candidate
                                                    print(f"  ✓ 전문 다운로드 버튼 발견 (iframe 있는 경우, XPath, title 검증 통과)")
                                            except Exception as e:
                                                print(f"  ⚠ 다운로드 버튼을 찾을 수 없음: {e}")
                                        
                                        # 최후의 수단: 모든 버튼을 검사하여 img title로 찾기
                                        if not download_button:
                                            try:
                                                all_buttons = driver.find_elements(By.CSS_SELECTOR, ".btn_box a, #contents_wrap a")
                                                for btn in all_buttons:
                                                    if verify_download_button_by_img_title_iframe(btn, ['전문 다운로드', '전문']):
                                                        download_button = btn
                                                        print(f"  ✓ 전문 다운로드 버튼 발견 (img title로 검색)")
                                                        break
                                            except:
                                                pass
                                    
                                    # 다운로드 버튼 처리 (iframe 유무와 관계없이)
                                    if download_button:
                                        # 버튼의 href 또는 onclick 확인
                                        href = download_button.get_attribute('href') or ''
                                        onclick = download_button.get_attribute('onclick') or ''
                                        
                                        # JavaScript 함수 추출 (예: fileDown('563', 'oriPdf'))
                                        js_function = None
                                        if href.startswith('javascript:'):
                                            js_function = href.replace('javascript:', '').strip()
                                        elif onclick:
                                            js_function = onclick.strip()
                                        
                                        # 파일명 추출 (버튼 텍스트 또는 href에서)
                                        file_name = download_button.text.strip() or ''
                                        if not file_name:
                                            # href에서 파일명 추출
                                            if href:
                                                file_name = Path(href).name or ''
                                        
                                        if js_function or href or onclick:
                                            # JavaScript 함수 저장 (다운로드 시 직접 실행)
                                            if js_function:
                                                item['download_js_function'] = js_function
                                            # 다운로드 링크 생성
                                            if href.startswith('http'):
                                                item['download_link'] = href
                                            elif href.startswith('javascript:'):
                                                item['download_link'] = href
                                            else:
                                                item['download_link'] = urljoin(self.BASE_URL, href) if href else ''
                                            
                                            item['file_name'] = file_name or 'download'
                                            
                                            # 다운로드 버튼 선택자 저장 (iframe 유무에 따라 다름)
                                            if has_no_iframe:
                                                item['download_button_selector'] = ".btn_box .kor_btn a[href*='fileDown']"
                                                item['download_button_xpath'] = "//div[@class='btn_box']//div[@class='kor_btn']//a[contains(@href, 'fileDown')]"
                                            else:
                                                item['download_button_selector'] = "#contents_wrap > div > div.btn_box > div > a:nth-child(2)"
                                                item['download_button_xpath'] = "/html/body/div[3]/div[3]/div[2]/div[2]/div/div[3]/div/a[2]"
                                            
                                            print(f"  ✓ 다운로드 버튼 발견: {item['file_name']} (JS: {js_function[:50] if js_function else 'N/A'})")
                                    
                                    # 새 창에서 개정이유, 시행일, 공포일, 개정내용 추출
                                    try:
                                        print(f"  → 새 창에서 내용 추출 시도 중...")
                                        new_window_data = self.extract_content_from_new_window(
                                            driver,
                                            has_no_iframe=has_no_iframe,
                                            regulation_name=regulation_name,
                                            content_limit=content_limit,
                                        )
                                        if new_window_data:
                                            # 새 창에서 추출한 내용 저장
                                            if new_window_data.get('revision_reason'):
                                                item['revision_reason'] = new_window_data.get('revision_reason', '')
                                            if new_window_data.get('enforcement_date'):
                                                item['enforcement_date'] = new_window_data.get('enforcement_date', '')
                                            if new_window_data.get('promulgation_date'):
                                                item['promulgation_date'] = new_window_data.get('promulgation_date', '')
                                            if new_window_data.get('revision_content'):
                                                item['revision_content'] = new_window_data.get('revision_content', '')
                                            
                                            revision_reason_len = len(item.get('revision_reason', ''))
                                            print(f"  ✓ 새 창 내용 추출 완료 (개정이유: {revision_reason_len}자, 시행일: {item.get('enforcement_date', '없음')}, 공포일: {item.get('promulgation_date', '없음')})")
                                        else:
                                            print(f"  ⚠ 새 창에서 내용을 추출하지 못했습니다.")
                                    except Exception as e:
                                        print(f"  ⚠ 새 창 내용 추출 중 오류: {e}")
                                        import traceback
                                        traceback.print_exc()
                                else:
                                    print(f"  ⚠ 상세 내용 추출 실패")
                            
                            except Exception as e:
                                print(f"  ⚠ 상세 페이지 처리 실패: {e}")
                                import traceback
                                traceback.print_exc()
                                continue
                    
                    # 파일 다운로드 및 내용 추출 (감독규정)
                    if download_files and supervision_results:
                        print(f"\n=== 감독규정 파일 다운로드 및 내용 추출 시작 ===")
                        for idx, item in enumerate(supervision_results, 1):
                            download_button_selector = item.get('download_button_selector')
                            download_button_xpath = item.get('download_button_xpath')
                            download_link = item.get('download_link', '')
                            
                            if not download_button_selector and not download_link:
                                continue
                            
                            print(f"[{idx}/{len(supervision_results)}] {item.get('title', 'N/A')[:50]}... 파일 다운로드 중")
                            
                            regulation_name = item.get('regulation_name', item.get('title', ''))
                            file_name = item.get('file_name', '')
                            
                            # 버튼이 있으면 클릭하여 다운로드, 없으면 링크로 다운로드
                            if download_button_selector or download_button_xpath:
                                try:
                                    # 메인 프레임으로 전환
                                    driver.switch_to.default_content()
                                    time.sleep(1)
                                    
                                    # 다운로드 전 현재 파일 목록 저장 (새 파일 감지용)
                                    files_before = set(f.name for f in self.current_dir.glob("*") if f.is_file())
                                    
                                    # JavaScript 함수가 있으면 직접 실행, 없으면 버튼 클릭
                                    download_js_function = item.get('download_js_function')
                                    if download_js_function:
                                        # JavaScript 함수 직접 실행
                                        print(f"  → JavaScript 함수 실행: {download_js_function[:50]}...")
                                        try:
                                            # 함수 실행 전에 다운로드 디렉토리 확인
                                            print(f"  → 다운로드 디렉토리: {self.current_dir}")
                                            print(f"  → 현재 파일 수: {len(files_before)}")
                                            
                                            # Chrome DevTools Protocol을 사용하여 다운로드 허용
                                            try:
                                                driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                                                    'behavior': 'allow',
                                                    'downloadPath': str(self.current_dir)
                                                })
                                                print(f"  ✓ 다운로드 동작 설정 완료 (CDP)")
                                            except Exception as cdp_error:
                                                print(f"  ⚠ CDP 설정 실패 (계속 진행): {cdp_error}")
                                            
                                            # JavaScript 함수 실행
                                            driver.execute_script(download_js_function)
                                            print(f"  ✓ JavaScript 함수 실행 완료")
                                            
                                            # 추가 대기 (다운로드 시작 대기)
                                            time.sleep(3)
                                        except Exception as e:
                                            print(f"  ⚠ JavaScript 함수 실행 실패: {e}")
                                            import traceback
                                            traceback.print_exc()
                                            # 버튼 클릭으로 fallback
                                            download_js_function = None
                                    
                                    if not download_js_function:
                                        # 다운로드 버튼 다시 찾기 (stale element 방지)
                                        # 버튼 검증 헬퍼 함수: img title로 확인
                                        def verify_download_button_title(element, expected_titles):
                                            """버튼 내부의 img 태그 title로 검증"""
                                            try:
                                                img = element.find_element(By.TAG_NAME, "img")
                                                img_title = img.get_attribute('title') or img.get_attribute('alt') or ''
                                                for expected in expected_titles:
                                                    if expected in img_title:
                                                        return True
                                            except:
                                                pass
                                            return False
                                        
                                        download_button = None
                                        if download_button_selector:
                                            try:
                                                candidate = driver.find_element(By.CSS_SELECTOR, download_button_selector)
                                                if candidate and verify_download_button_title(candidate, ['전문 다운로드', '전문']):
                                                    download_button = candidate
                                                    print(f"  ✓ 다운로드 버튼 재확인 (CSS 셀렉터, title 검증 통과)")
                                            except:
                                                pass
                                        
                                        if not download_button and download_button_xpath:
                                            try:
                                                candidate = driver.find_element(By.XPATH, download_button_xpath)
                                                if candidate and verify_download_button_title(candidate, ['전문 다운로드', '전문']):
                                                    download_button = candidate
                                                    print(f"  ✓ 다운로드 버튼 재확인 (XPath, title 검증 통과)")
                                            except:
                                                pass
                                        
                                        # 셀렉터/XPath로 찾지 못한 경우 img title로 직접 검색
                                        if not download_button:
                                            try:
                                                all_buttons = driver.find_elements(By.CSS_SELECTOR, ".btn_box a, .btnDiv a, #contents_wrap a")
                                                for btn in all_buttons:
                                                    if verify_download_button_title(btn, ['전문 다운로드', '전문']):
                                                        download_button = btn
                                                        print(f"  ✓ 다운로드 버튼 발견 (img title로 검색)")
                                                        break
                                            except:
                                                pass
                                        
                                        if not download_button:
                                            print(f"  ⚠ 다운로드 버튼을 찾을 수 없음 (title 검증 실패)")
                                            continue
                                        
                                        # 버튼 클릭
                                        driver.execute_script("arguments[0].click();", download_button)
                                        print(f"  ✓ 다운로드 버튼 클릭 완료")
                                    
                                    # 다운로드 완료 대기 (최대 60초)
                                    time.sleep(2)  # 초기 대기
                                    max_wait = 60
                                    waited = 0
                                    downloaded_file = None
                                    
                                    while waited < max_wait:
                                        downloaded_files = list(self.current_dir.glob("*"))
                                        # .crdownload 파일 확인 (다운로드 진행 중)
                                        crdownload_files = [f for f in downloaded_files if f.name.endswith('.crdownload')]
                                        
                                        if crdownload_files:
                                            # 다운로드 진행 중
                                            print(f"  → 다운로드 진행 중... ({waited}초)")
                                        else:
                                            # 다운로드 완료된 파일 찾기 (이전에 없던 새 파일)
                                            for f in downloaded_files:
                                                if f.is_file() and not f.name.endswith('.crdownload'):
                                                    if f.name not in files_before:
                                                        if not downloaded_file or f.stat().st_mtime > downloaded_file.stat().st_mtime:
                                                            downloaded_file = f
                                            
                                            if downloaded_file:
                                                print(f"  ✓ 새 파일 발견: {downloaded_file.name}")
                                                break
                                        
                                        time.sleep(1)
                                        waited += 1
                                    
                                    if waited >= max_wait:
                                        print(f"  ⚠ 다운로드 대기 시간 초과 ({max_wait}초)")
                                    
                                    if downloaded_file and downloaded_file.exists():
                                        # 파일명 생성 (규정명 기반)
                                        ext = downloaded_file.suffix or '.hwp'
                                        if regulation_name:
                                            safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                                            safe_reg_name = safe_reg_name.replace(' ', '_')
                                            safe_filename = f"{safe_reg_name}{ext}"
                                        else:
                                            safe_filename = downloaded_file.name
                                        
                                        new_file_path = self.current_dir / safe_filename
                                        
                                        # 파일 이동/이름 변경
                                        import shutil
                                        if str(downloaded_file) != str(new_file_path):
                                            if new_file_path.exists():
                                                new_file_path.unlink()
                                            shutil.move(downloaded_file, new_file_path)
                                            print(f"  ✓ 파일 저장: {new_file_path}")
                                        
                                        # 파일 이름 저장 (규정명.확장자 형태)
                                        item['file_name'] = safe_filename
                                        
                                        # 이전 파일과 비교
                                        previous_file_path = self.previous_dir / safe_filename
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
                                        
                                        # 파일 내용 추출
                                        file_content = self.extract_hwp_content(str(new_file_path))
                                        if file_content:
                                            # 법규 정보 추출
                                            law_info = self.extract_law_info_from_content(file_content, item.get('title', ''))
                                            if law_info.get('regulation_name'):
                                                item['regulation_name'] = law_info.get('regulation_name')
                                            if law_info.get('enactment_date'):
                                                item['enactment_date'] = law_info.get('enactment_date')
                                            # revision_date는 select에서 추출한 값이 우선 (이미 있으면 덮어쓰지 않음)
                                            if law_info.get('revision_date') and not item.get('revision_date'):
                                                item['revision_date'] = law_info.get('revision_date')
                                            
                                            # 본문 설정 (4000자 제한, 개행 유지)
                                            content = file_content.replace("\r\n", "\n").replace("\r", "\n")
                                            max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                            if len(content) > max_length:
                                                item['content'] = content[:max_length]
                                            else:
                                                item['content'] = content
                                            
                                            print(f"  ✓ 파일 내용 추출 완료 ({len(file_content)}자)")
                                        else:
                                            print(f"  ⚠ 파일 내용 추출 실패")
                                    else:
                                        print(f"  ⚠ 파일 다운로드 실패 (파일을 찾을 수 없음)")
                                
                                except Exception as e:
                                    print(f"  ⚠ 버튼 클릭 다운로드 실패: {e}")
                                    import traceback
                                    traceback.print_exc()
                            
                            elif download_link:
                                # 링크로 다운로드 (기존 방식)
                                comparison_result = self._download_and_compare_file(
                                    download_link,
                                    file_name,
                                    regulation_name=regulation_name,
                                    use_selenium=True,
                                    driver=driver
                                )
                                
                                if comparison_result:
                                    filepath = comparison_result.get('file_path')
                                    if filepath and os.path.exists(filepath):
                                        # 파일 내용 추출
                                        file_content = self.extract_hwp_content(filepath)
                                        if file_content:
                                            # 법규 정보 추출
                                            law_info = self.extract_law_info_from_content(file_content, item.get('title', ''))
                                            if law_info.get('regulation_name'):
                                                item['regulation_name'] = law_info.get('regulation_name')
                                            if law_info.get('enactment_date'):
                                                item['enactment_date'] = law_info.get('enactment_date')
                                            # revision_date는 select에서 추출한 값이 우선 (이미 있으면 덮어쓰지 않음)
                                            if law_info.get('revision_date') and not item.get('revision_date'):
                                                item['revision_date'] = law_info.get('revision_date')
                                            
                                            # 본문 설정 (4000자 제한, 개행 유지)
                                            content = file_content.replace("\r\n", "\n").replace("\r", "\n")
                                            max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                            if len(content) > max_length:
                                                item['content'] = content[:max_length]
                                            else:
                                                item['content'] = content
                                            
                                            print(f"  ✓ 파일 내용 추출 완료 ({len(file_content)}자)")
                                        else:
                                            print(f"  ⚠ 파일 내용 추출 실패")
                    
                    # 감독규정 결과를 all_results에 추가
                    all_results.extend(supervision_results)
                    print(f"\n✓ 감독규정 스크래핑 완료: {len(supervision_results)}개")
        
        except Exception as e:
            print(f"✗ 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if driver:
                driver.quit()
                print("Selenium 드라이버 종료 완료")
        
        return all_results


def save_fsb_results(records: List[Dict], crawler: Optional[FsbScraper] = None):
    """JSON 및 CSV로 저축은행중앙회 데이터를 저장한다.
    
    Args:
        records: 스크래핑된 법규정보 리스트
        crawler: FsbScraper 인스턴스 (CSV의 모든 항목을 포함하기 위해 사용)
    """
    import json
    import csv
    
    if not records:
        print("저장할 데이터가 없습니다.")
        return
    
    # CSV의 모든 항목을 포함하도록 정렬 (CSV 순서 유지)
    if crawler and crawler.target_laws:
        # CSV 항목 순서대로 정렬하기 위한 딕셔너리 생성
        records_dict = {}
        for item in records:
            # target_name을 우선적으로 사용, 없으면 regulation_name, title 순서로 확인
            reg_name = item.get("target_name") or item.get("regulation_name") or item.get("title", "")
            if reg_name:
                records_dict[reg_name] = item
        
        # CSV 순서대로 정렬된 결과 생성
        ordered_records = []
        missing_count = 0
        for target in crawler.target_laws:
            target_name = target.get("law_name", "")
            category = target.get("category", "")  # 구분 값
            if target_name in records_dict:
                record = records_dict[target_name].copy()
                record['category'] = category  # 구분 값 추가
                ordered_records.append(record)
            else:
                # CSV에 있지만 스크래핑되지 않은 항목은 빈 데이터로 추가
                ordered_records.append({
                    "target_name": target_name,
                    "regulation_name": target_name,
                    "title": target_name,
                    "organization": "저축은행중앙회",
                    "content": "",
                    "department": "",
                    "file_name": "",
                    "download_link": "",
                    "enactment_date": "",
                    "revision_date": "",
                    "category": category,  # 구분 값 추가
                })
                missing_count += 1
        
        if missing_count > 0:
            print(f"⚠ CSV에 있지만 스크래핑되지 않은 항목 {missing_count}개를 빈 데이터로 추가했습니다.")
        
        records = ordered_records
    
    # 날짜 정규화를 위한 scraper 인스턴스
    scraper = crawler if crawler else FsbScraper()
    
    # 데이터 정리
    law_results = []
    for item in records:
        regulation_name = item.get('target_name') or item.get('regulation_name', item.get('title', ''))
        
        # 파일 이름 생성 (규정명.확장자 형태)
        file_name = item.get('file_name', '')
        if not file_name and regulation_name:
            # 다운로드된 파일이 있으면 확장자 확인
            # current 디렉토리에서 규정명으로 시작하는 파일 찾기
            if crawler:
                import re
                safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                matching_files = list(crawler.current_dir.glob(f"{safe_reg_name}.*"))
                if matching_files:
                    file_name = matching_files[0].name
        
        law_item = {
            '구분': item.get('category', item.get('target_category', '')),  # 구분 값 추가
            '규정명': regulation_name,
            '기관명': item.get('organization', '저축은행중앙회'),
            '본문': item.get('content', ''),
            '제정일': scraper.normalize_date_format(item.get('enactment_date', '')),
            '최근 개정일': scraper.normalize_date_format(item.get('revision_date', '')),
            '소관부서': item.get('department', ''),
            '개정이유': item.get('revision_reason', ''),
            '개정내용': item.get('revision_content', ''),
            '시행일': item.get('enforcement_date', ''),
            '공포일': item.get('promulgation_date', ''),
            '파일 이름': file_name
        }
        law_results.append(law_item)
    
    # JSON 저장
    json_dir = os.path.join('output', 'json')
    os.makedirs(json_dir, exist_ok=True)
    
    json_path = os.path.join(json_dir, 'fsb_scraper.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(
            {
                'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'url': FsbScraper.LOGIN_URL,
                'total_count': len(law_results),
                'results': law_results
            },
            f,
            ensure_ascii=False,
            indent=2
        )
    print(f"JSON 저장 완료: {json_path}")
    
    # CSV 저장
    csv_dir = os.path.join('output', 'csv')
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, 'fsb_scraper.csv')
    
    headers = ["구분", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "개정이유", "개정내용", "시행일", "공포일", "파일 이름"]
    
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for law_item in law_results:
            # 본문 내용 처리 (개행 유지, 4000자 제한)
            content = law_item.get('본문', '') or ''
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            if len(content) > 4000:
                content = content[:4000]
            
            csv_item = law_item.copy()
            csv_item['본문'] = content
            writer.writerow(csv_item)
    
    print(f"CSV 저장 완료: {csv_path}")

# ==================================================
# Health Check (표준 출력 양식)
# ==================================================
import time
from selenium.webdriver.chrome.options import Options
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType

def fsb_health_check() -> dict:
    """
    FSB(저축은행중앙회) 모범규준 Health Check
    - BOK Health Check 출력 포맷과 완전 동일
    """
    start_ts = time.perf_counter()

    result = base_health_output(
        auth_src="저축은행중앙회-모범규준",
        scraper_id="FSB_LAW",
        target_url="http://sblaw.fsb.or.kr/lmxsrv/law/lawListManager.do?LAWGROUP=3",
    )

    driver = None
    scraper = None

    try:
        # ==================================================
        # 1️⃣ Scraper 생성
        # ==================================================
        scraper = FsbScraper(delay=1.0)

        # ==================================================
        # 2️⃣ Selenium Driver 생성
        # ==================================================
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")

        try:
            driver = scraper._create_webdriver(chrome_options)
        except Exception as e:
            raise HealthCheckError(
                HealthErrorType.DRIVER_ERROR,
                f"Selenium 드라이버 생성 실패: {e}",
            )

        # ==================================================
        # 3️⃣ 로그인
        # ==================================================
        if not scraper._login(driver):
            raise HealthCheckError(
                HealthErrorType.AUTH_ERROR,
                "FSB 로그인 실패",
                "login()",
            )

        # ==================================================
        # 4️⃣ 목록(검색) 페이지 접근
        # ==================================================
        list_url = result["target_url"]
        driver.get(list_url)
        time.sleep(3)

        result["checks"]["http"] = {
            "ok": True,
            "status_code": 200,
            "verify_ssl": False,
        }

        # ==================================================
        # 5️⃣ 트리 목록 1건 추출
        # ==================================================
        tree_links = scraper.extract_tree_links(driver)

        if not tree_links:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "FSB 규정 트리 목록이 비어 있음",
                "extract_tree_links()",
            )

        item = tree_links[0]
        title = item.get("title") or item.get("regulation_name", "")

        result["checks"]["list"] = {
            "ok": True,
            "count": len(tree_links),
            "title": title,
        }

        # ==================================================
        # 6️⃣ 상세 페이지 접근
        # ==================================================
        detail_soup = scraper.click_tree_link_and_extract(driver, item)

        if not detail_soup:
            raise HealthCheckError(
                HealthErrorType.NO_DETAIL_URL,
                "상세 페이지 접근 실패",
                "click_tree_link_and_extract()",
            )

        content = detail_soup.get_text(strip=True)
        if not content:
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "상세 페이지 본문이 비어 있음",
                "detail iframe",
            )

        result["checks"]["detail"] = {
            "ok": True,
            "url": "SBLAW 트리 > 상세 iframe",
            "content_length": len(content),
        }

        # ==================================================
        # SUCCESS
        # ==================================================
        result["ok"] = True
        result["status"] = "OK"

    except HealthCheckError as he:
        apply_health_error(result, he)

    except Exception as e:
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.UNEXPECTED_ERROR,
                str(e),
            ),
        )

    finally:
        result["elapsed_ms"] = int(
            (time.perf_counter() - start_ts) * 1000
        )
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return result

# ==================================================
# scheduler call
# ==================================================
def run():
    crawler = FsbScraper()
    results = crawler.crawl_sblaw_portal()
    
    print(f"\n총 {len(results)}개의 데이터를 수집했습니다.")
    save_fsb_results(results, crawler=crawler)

if __name__ == "__main__":
   
    parser = argparse.ArgumentParser(description='저축은행중앙회 SBLAW 스크래퍼')
    parser.add_argument('--limit', type=int, default=0, help='가져올 개수 제한 (0=전체)')
    parser.add_argument('--no-download', action='store_true', help='파일 다운로드 및 내용 추출 건너뛰기')
    parser.add_argument('--content', type=int, default=0, help='본문 길이 제한 (0=제한 없음, 문자 수)')
    parser.add_argument('--login-id', type=str, default=None, help='로그인 ID (코드에 설정된 값보다 우선)')
    parser.add_argument('--login-password', type=str, default=None, help='로그인 비밀번호 (코드에 설정된 값보다 우선)')
    parser.add_argument('--csv', type=str, default=None, help='대상 규정 목록 CSV 경로 (기본: FSB_Scraper/input/list.csv)')

    parser.add_argument(
        "--check",
        action="store_true",
        help="저축은행중앙회-소비자포탈>모범규준 Health Check 실행"
    )  

    args = parser.parse_args()
    
    if args.check:
        health_result = fsb_health_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)

    crawler = FsbScraper(
        login_id=args.login_id,
        login_password=args.login_password,
        csv_path=args.csv
    )
    results = crawler.crawl_sblaw_portal(
        limit=args.limit,
        download_files=not args.no_download,
        content_limit=args.content
    )
    
    print(f"\n총 {len(results)}개의 데이터를 수집했습니다.")
    save_fsb_results(results, crawler=crawler)
