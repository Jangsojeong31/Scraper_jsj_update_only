# fss_admin_scraper_v2.py
# 금융감독원-업무자료>금융감독법규>감독행정작용>감독행정작용 내역

import os
import sys
import time
import logging
import json
import csv
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import pandas as pd

# ==================================================
# 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 로그 설정 (한글 깨짐 방지)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FSSAdminScraper:
    def __init__(self):
        self.base_url = "https://www.fss.or.kr/fss/job/admnstgudcDtls/list.do?menuNo=200494&pageIndex={}&searchRegn=&searchYear=&searchCecYn=T&searchWrd="
        self.data = []
        self.json_file = "fss_results.json"
        self.csv_file = "fss_results.csv"

        # Chrome 옵션 설정
        chrome_options = Options()
        # headless 모드 비활성화 - 디버깅을 위해
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 10)

    def load_existing_data(self):
        """기존 결과 파일에서 데이터 로드"""
        existing_data = []
        
        # JSON 파일에서 로드
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                logger.info(f"기존 JSON 파일에서 {len(existing_data)}건 로드: {self.json_file}")
            except Exception as e:
                logger.warning(f"기존 JSON 파일 로드 실패: {str(e)}")
        
        return existing_data

    def get_total_pages(self):
        """총 페이지 수를 자동으로 감지"""
        try:
            url = self.base_url.format(1)
            self.driver.get(url)
            time.sleep(2)
            
            # 페이지네이션 요소 찾기
            total_pages = 1
            
            # 방법 1: 페이지 번호 링크 찾기
            try:
                page_links = self.driver.find_elements(By.CSS_SELECTOR, ".paging a, .pagination a, .page a, a[href*='pageIndex']")
                page_numbers = []
                for link in page_links:
                    try:
                        text = link.text.strip()
                        if text.isdigit():
                            page_numbers.append(int(text))
                        # href에서 페이지 번호 추출
                        href = link.get_attribute('href')
                        if href and 'pageIndex=' in href:
                            match = re.search(r'pageIndex=(\d+)', href)
                            if match:
                                page_numbers.append(int(match.group(1)))
                    except:
                        continue
                
                if page_numbers:
                    total_pages = max(page_numbers)
                    logger.info(f"페이지네이션에서 총 {total_pages}페이지 감지")
                    return total_pages
            except Exception as e:
                logger.debug(f"페이지 번호 링크 찾기 실패: {str(e)}")
            
            # 방법 2: "다음" 버튼이 있는지 확인하고 마지막 페이지 찾기
            try:
                next_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".paging .next, .pagination .next, a:contains('다음'), a:contains('>')")
                if next_buttons:
                    # 다음 버튼이 있으면 충분히 큰 수로 시작
                    total_pages = 100
                    logger.info("다음 버튼 발견, 페이지 수를 동적으로 확인합니다")
            except:
                pass
            
            # 방법 3: 총 건수와 페이지당 건수로 계산
            try:
                # 총 건수 텍스트 찾기 (예: "총 96건", "전체 96건")
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                match = re.search(r'(?:총|전체)\s*(\d+)\s*건', page_text)
                if match:
                    total_count = int(match.group(1))
                    # 페이지당 10개라고 가정 (실제로는 동적으로 확인 가능)
                    items_per_page = 10
                    total_pages = (total_count + items_per_page - 1) // items_per_page
                    logger.info(f"총 건수 {total_count}건, 페이지당 {items_per_page}건으로 계산: {total_pages}페이지")
                    return total_pages
            except Exception as e:
                logger.debug(f"총 건수 계산 실패: {str(e)}")
            
            return total_pages
        except Exception as e:
            logger.warning(f"총 페이지 수 감지 실패: {str(e)}, 기본값 10페이지로 진행")
            return 10

    def get_list_data(self, page_num=1):
        """목록 페이지에서 데이터 수집"""
        url = self.base_url.format(page_num)
        logger.info(f"페이지 {page_num} 접속 중: {url}")

        try:
            self.driver.get(url)
            time.sleep(3)

            # 페이지 소스 로그
            logger.info(f"페이지 로드 완료, 소스 길이: {len(self.driver.page_source)}")

            # 여러 가지 셀렉터 시도
            rows = []
            selectors = [
                "table.tbl_list tbody tr",
                "table.table tbody tr",
                "table tbody tr",
                ".tbl_list tbody tr",
                "#contents table tbody tr"
            ]

            for selector in selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if rows:
                        logger.info(f"셀렉터 '{selector}'로 {len(rows)}개 행 발견")
                        break
                except:
                    continue

            if not rows:
                logger.warning(f"페이지 {page_num}에서 테이블을 찾을 수 없습니다.")
                # HTML 구조 일부 출력
                try:
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    logger.info(f"페이지에 테이블 {len(tables)}개 발견")
                    if tables:
                        logger.info(f"첫 번째 테이블 클래스: {tables[0].get_attribute('class')}")
                except:
                    pass
                return

            logger.info(f"페이지 {page_num}에서 {len(rows)}개 항목 처리 시작")

            for idx, row in enumerate(rows, 1):
                try:
                    # 빈 행 스킵
                    if not row.text.strip():
                        continue

                    cols = row.find_elements(By.TAG_NAME, "td")

                    if len(cols) < 5:
                        logger.debug(f"  [{idx}] 컬럼 수 부족: {len(cols)}개")
                        continue

                    # 기본 정보 추출
                    item = {
                        '관리번호': cols[0].text.strip(),
                        '제목': cols[1].text.strip(),
                        '소관부서': cols[2].text.strip(),
                        '시행일': cols[3].text.strip(),
                        '시행여부': cols[4].text.strip(),
                    }

                    # 제목이 비어있으면 스킵
                    if not item['제목']:
                        continue

                    logger.info(f"  [{idx}] 관리번호: {item['관리번호']}, 제목: {item['제목'][:50]}")

                    # 제목 링크 찾기
                    try:
                        title_link = cols[1].find_element(By.TAG_NAME, "a")
                        detail_url = title_link.get_attribute('href')

                        # 상대 경로를 절대 경로로 변환
                        if detail_url.startswith('./'):
                            detail_url = "https://www.fss.or.kr/fss/job/admnstgudcDtls/" + detail_url[2:]
                        elif not detail_url.startswith('http'):
                            detail_url = "https://www.fss.or.kr" + detail_url

                        logger.info(f"    상세 URL: {detail_url}")

                        # 상세 정보 수집
                        detail_info = self.get_detail_data(detail_url)
                        item.update(detail_info)
                    except NoSuchElementException:
                        logger.warning(f"  [{idx}] 상세 링크를 찾을 수 없습니다.")

                    self.data.append(item)

                except Exception as e:
                    logger.error(f"  항목 {idx} 처리 중 오류: {str(e)}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            logger.error(f"페이지 {page_num} 처리 중 오류: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())

    def get_detail_data(self, url):
        """상세 페이지에서 데이터 수집"""
        detail_info = {
            '첨부파일명': '',
            '첨부파일링크': '',
            '담당부서': '',
            '담당팀': '',
            '담당자': '',
            '자료문의': '',
            '상세본문내용': ''
        }

        original_window = self.driver.current_window_handle

        try:
            # 새 탭에서 열기
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            time.sleep(1)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            time.sleep(2)

            logger.info(f"    상세 페이지 로드 완료")

            # 첨부파일 정보 - 여러 방법 시도
            try:
                # 방법 1: 첨부파일 링크
                file_links = self.driver.find_elements(By.CSS_SELECTOR, "a[onclick*='download'], a[href*='download'], .file_list a, .attach a")
                if file_links:
                    file_names = []
                    file_urls = []
                    for link in file_links:
                        name = link.text.strip()
                        if name:
                            file_names.append(name)
                            href = link.get_attribute('href')
                            if href:
                                file_urls.append(href)
                    if file_names:
                        detail_info['첨부파일명'] = ' | '.join(file_names)
                        detail_info['첨부파일링크'] = ' | '.join(file_urls)
                        logger.info(f"    첨부파일 {len(file_names)}개 발견")
            except Exception as e:
                logger.debug(f"    첨부파일 추출 오류: {str(e)}")

            # 상세 정보 추출 - 여러 방법 시도
            try:
                # 방법 1: 테이블에서 추출 (th/td 구조)
                table_selectors = [
                    "table.view_table",
                    "table.tbl_view",
                    "table.table",
                    ".view_area table",
                    "#contents table",
                    "table",
                    ".view_info table",
                    ".detail_info table"
                ]

                info_table = None
                for selector in table_selectors:
                    try:
                        tables = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for table in tables:
                            rows = table.find_elements(By.TAG_NAME, "tr")
                            if rows and len(rows) > 0:
                                info_table = table
                                logger.info(f"    정보 테이블 발견: {selector}")
                                break
                        if info_table:
                            break
                    except:
                        continue

                if info_table:
                    info_rows = info_table.find_elements(By.TAG_NAME, "tr")
                    logger.info(f"    정보 테이블에서 {len(info_rows)}개 행 발견")

                    for row in info_rows:
                        try:
                            th_elems = row.find_elements(By.TAG_NAME, "th")
                            td_elems = row.find_elements(By.TAG_NAME, "td")

                            if th_elems and td_elems:
                                key = th_elems[0].text.strip()
                                value = td_elems[0].text.strip()

                                logger.info(f"      테이블 키: {key}, 값: {value[:50]}")

                                if '담당부서' in key or '소관부서' in key:
                                    if not detail_info['담당부서']:
                                        detail_info['담당부서'] = value
                                elif '담당팀' in key or ('팀' in key and '담당' in key):
                                    if not detail_info['담당팀']:
                                        detail_info['담당팀'] = value
                                elif '담당자' in key:
                                    if not detail_info['담당자']:
                                        detail_info['담당자'] = value
                                elif '자료문의' in key or '문의' in key or '전화' in key or '연락처' in key:
                                    if not detail_info['자료문의']:
                                        detail_info['자료문의'] = value
                        except Exception as e:
                            logger.debug(f"      행 처리 오류: {str(e)}")
                            continue

                # 방법 2: dl/dt/dd 구조에서 추출
                if not all([detail_info['담당부서'], detail_info['담당팀'], detail_info['담당자'], detail_info['자료문의']]):
                    try:
                        dl_elements = self.driver.find_elements(By.TAG_NAME, "dl")
                        for dl in dl_elements:
                            try:
                                dt_elements = dl.find_elements(By.TAG_NAME, "dt")
                                dd_elements = dl.find_elements(By.TAG_NAME, "dd")
                                
                                for dt, dd in zip(dt_elements, dd_elements):
                                    key = dt.text.strip()
                                    value = dd.text.strip()
                                    
                                    logger.info(f"      DL 키: {key}, 값: {value[:50]}")
                                    
                                    if '담당부서' in key or '소관부서' in key:
                                        if not detail_info['담당부서']:
                                            detail_info['담당부서'] = value
                                    elif '담당팀' in key or ('팀' in key and '담당' in key):
                                        if not detail_info['담당팀']:
                                            detail_info['담당팀'] = value
                                    elif '담당자' in key:
                                        if not detail_info['담당자']:
                                            detail_info['담당자'] = value
                                    elif '자료문의' in key or '문의' in key or '전화' in key or '연락처' in key:
                                        if not detail_info['자료문의']:
                                            detail_info['자료문의'] = value
                            except:
                                continue
                    except Exception as e:
                        logger.debug(f"    DL 구조 추출 오류: {str(e)}")

                # 방법 3: div 구조에서 추출 (label/span 등)
                if not all([detail_info['담당부서'], detail_info['담당팀'], detail_info['담당자'], detail_info['자료문의']]):
                    try:
                        # label과 함께 있는 텍스트 찾기
                        labels = self.driver.find_elements(By.TAG_NAME, "label")
                        for label in labels:
                            try:
                                key = label.text.strip()
                                # label 다음 요소 찾기
                                parent = label.find_element(By.XPATH, "./..")
                                value = parent.text.replace(key, "").strip()
                                
                                if value and len(value) < 200:  # 너무 긴 값은 제외
                                    logger.info(f"      Label 키: {key}, 값: {value[:50]}")
                                    
                                    if '담당부서' in key or '소관부서' in key:
                                        if not detail_info['담당부서']:
                                            detail_info['담당부서'] = value
                                    elif '담당팀' in key or ('팀' in key and '담당' in key):
                                        if not detail_info['담당팀']:
                                            detail_info['담당팀'] = value
                                    elif '담당자' in key:
                                        if not detail_info['담당자']:
                                            detail_info['담당자'] = value
                                    elif '자료문의' in key or '문의' in key or '전화' in key or '연락처' in key:
                                        if not detail_info['자료문의']:
                                            detail_info['자료문의'] = value
                            except:
                                continue
                    except Exception as e:
                        logger.debug(f"    Label 구조 추출 오류: {str(e)}")

                # 방법 4: 전체 페이지에서 키워드 검색
                if not all([detail_info['담당부서'], detail_info['담당팀'], detail_info['담당자'], detail_info['자료문의']]):
                    try:
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text
                        
                        # 정규표현식으로 패턴 찾기
                        
                        # 담당부서 패턴
                        if not detail_info['담당부서']:
                            match = re.search(r'담당부서[:\s]+([^\n]+)', page_text)
                            if match:
                                detail_info['담당부서'] = match.group(1).strip()
                                logger.info(f"      정규식으로 담당부서 발견: {detail_info['담당부서'][:50]}")
                        
                        # 담당팀 패턴
                        if not detail_info['담당팀']:
                            match = re.search(r'담당팀[:\s]+([^\n]+)', page_text)
                            if match:
                                detail_info['담당팀'] = match.group(1).strip()
                                logger.info(f"      정규식으로 담당팀 발견: {detail_info['담당팀'][:50]}")
                        
                        # 담당자 패턴
                        if not detail_info['담당자']:
                            match = re.search(r'담당자[:\s]+([^\n]+)', page_text)
                            if match:
                                detail_info['담당자'] = match.group(1).strip()
                                logger.info(f"      정규식으로 담당자 발견: {detail_info['담당자'][:50]}")
                        
                        # 자료문의 패턴
                        if not detail_info['자료문의']:
                            patterns = [
                                r'자료문의[:\s]+([^\n]+)',
                                r'문의[:\s]+([^\n]+)',
                                r'연락처[:\s]+([^\n]+)',
                                r'전화[:\s]+([^\n]+)'
                            ]
                            for pattern in patterns:
                                match = re.search(pattern, page_text)
                                if match:
                                    detail_info['자료문의'] = match.group(1).strip()
                                    logger.info(f"      정규식으로 자료문의 발견: {detail_info['자료문의'][:50]}")
                                    break
                    except Exception as e:
                        logger.debug(f"    정규식 추출 오류: {str(e)}")

            except Exception as e:
                logger.error(f"    상세 정보 추출 오류: {str(e)}")
                import traceback
                logger.debug(traceback.format_exc())

            # 상세 본문 내용 - dd > pre 태그에서 추출
            try:
                # 방법 1: dd > pre 태그 직접 찾기
                pre_elem = None
                try:
                    pre_elem = self.driver.find_element(By.CSS_SELECTOR, "dd pre")
                    if pre_elem:
                        content = pre_elem.text.strip()
                        if content:
                            detail_info['상세본문내용'] = content
                            logger.info(f"    상세본문내용 수집 완료 (dd > pre, 길이: {len(content)})")
                except:
                    pass

                # 방법 2: dd 안의 pre 찾기
                if not detail_info['상세본문내용']:
                    try:
                        dd_elems = self.driver.find_elements(By.TAG_NAME, "dd")
                        for dd in dd_elems:
                            try:
                                pre = dd.find_element(By.TAG_NAME, "pre")
                                if pre:
                                    content = pre.text.strip()
                                    if content:
                                        detail_info['상세본문내용'] = content
                                        logger.info(f"    상세본문내용 수집 완료 (dd 순회, 길이: {len(content)})")
                                        break
                            except:
                                continue
                    except:
                        pass

                # 방법 3: 모든 pre 태그 확인
                if not detail_info['상세본문내용']:
                    try:
                        pre_elems = self.driver.find_elements(By.TAG_NAME, "pre")
                        for pre in pre_elems:
                            content = pre.text.strip()
                            if content and len(content) > 50:  # 충분히 긴 내용만
                                detail_info['상세본문내용'] = content
                                logger.info(f"    상세본문내용 수집 완료 (pre 태그, 길이: {len(content)})")
                                break
                    except:
                        pass

                # 방법 4: 다른 컨텐츠 영역 시도
                if not detail_info['상세본문내용']:
                    content_selectors = [
                        ".view_content",
                        ".content",
                        ".detail_content",
                        ".view_area .content",
                        "#contents .content",
                        "div.content"
                    ]

                    for selector in content_selectors:
                        try:
                            content_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if content_elem:
                                content = content_elem.text.strip()
                                if content:
                                    detail_info['상세본문내용'] = content
                                    logger.info(f"    상세본문내용 수집 완료 ({selector}, 길이: {len(content)})")
                                    break
                        except:
                            continue

                if not detail_info['상세본문내용']:
                    logger.warning(f"    상세본문내용을 찾을 수 없습니다.")

            except Exception as e:
                logger.debug(f"    상세본문내용 추출 오류: {str(e)}")

        except Exception as e:
            logger.error(f"    상세 페이지 처리 중 오류: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
        finally:
            # 원래 탭으로 복귀
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                self.driver.switch_to.window(original_window)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"    탭 전환 오류: {str(e)}")
                self.driver.switch_to.window(self.driver.window_handles[0])

        return detail_info

    def save_to_files(self):
        """CSV와 JSON 파일로 저장 (기존 데이터와 병합)"""
        if not self.data:
            logger.warning("저장할 데이터가 없습니다.")
            return

        # 기존 데이터 로드
        existing_data = self.load_existing_data()
        
        # 관리번호를 기준으로 중복 제거 (새 데이터 우선)
        existing_dict = {item.get('관리번호', ''): item for item in existing_data}
        new_dict = {item.get('관리번호', ''): item for item in self.data}
        
        # 기존 데이터와 새 데이터 병합 (새 데이터가 우선)
        merged_dict = {**existing_dict, **new_dict}
        merged_data = list(merged_dict.values())
        
        logger.info(f"기존 데이터: {len(existing_data)}건, 새 데이터: {len(self.data)}건, 병합 후: {len(merged_data)}건")

        # JSON 저장
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON 저장 완료: {self.json_file} (총 {len(merged_data)}건)")
        except Exception as e:
            logger.error(f"JSON 저장 오류: {str(e)}")

        # CSV 저장
        try:
            df = pd.DataFrame(merged_data)
            df.to_csv(self.csv_file, index=False, encoding='utf-8-sig')
            logger.info(f"CSV 저장 완료: {self.csv_file} (총 {len(merged_data)}건)")
        except Exception as e:
            logger.error(f"CSV 저장 오류: {str(e)}")

    def run(self, max_pages=None):
        """스크래핑 실행"""
        logger.info("=" * 80)
        logger.info("감독행정작용 스크래핑 시작")
        logger.info("=" * 80)

        try:
            # 총 페이지 수 자동 감지
            if max_pages is None:
                logger.info("총 페이지 수를 자동으로 감지합니다...")
                total_pages = self.get_total_pages()
                logger.info(f"총 {total_pages}페이지를 스크랩핑합니다.")
            else:
                total_pages = max_pages
                logger.info(f"지정된 페이지 수: {total_pages}페이지")

            for page in range(1, total_pages + 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"페이지 {page}/{total_pages} 처리 중")
                logger.info(f"{'='*60}")
                
                # 데이터 수집 전 현재 수집된 항목 수 확인
                before_count = len(self.data)
                
                self.get_list_data(page)
                
                # 수집된 항목 수 확인
                after_count = len(self.data)
                new_items = after_count - before_count
                
                if new_items > 0:
                    logger.info(f"이번 페이지에서 {new_items}건 수집, 누적: {len(self.data)}건")
                else:
                    logger.warning(f"이번 페이지에서 수집된 항목이 없습니다. 페이지가 끝났을 수 있습니다.")
                    # 연속으로 2페이지에서 항목이 없으면 중단
                    if page > 1 and new_items == 0:
                        logger.info(f"페이지 {page}에서 항목이 없어 스크랩핑을 중단합니다.")
                        break

                time.sleep(2)  # 페이지 간 대기 시간 증가

            # 결과 저장
            self.save_to_files()

        except Exception as e:
            logger.error(f"실행 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.driver.quit()
            logger.info("=" * 80)
            logger.info(f"스크래핑 완료 - 총 {len(self.data)}건 수집")
            logger.info("=" * 80)

# -------------------------------------------------
# Health Check 모드
# 금융감독원-업무자료>금융감독법규>감독행정작용>감독행정작용 내역
# -------------------------------------------------
from typing import Dict
# import time
# from datetime import datetime

# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC

from common.common_http import check_url_status, URLStatus
from common.url_health_mapper import map_urlstatus_to_health_error
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType


def fss_admin_health_check() -> Dict:
    """
    금융감독원 감독행정작용 Health Check
    - HealthErrorType 명시적 raise 패턴
    - 표준 Health Output Schema 사용
    """

    start_ts = time.perf_counter()

    LIST_URL = (
        "https://www.fss.or.kr/fss/job/admnstgudcDtls/"
        "list.do?menuNo=200494&pageIndex=1&searchRegn=&searchYear=&searchCecYn=T&searchWrd="
    )

    result = base_health_output(
        auth_src="금융감독원-감독행정작용",
        scraper_id="FSS_ADMIN",
        target_url=LIST_URL,
    )

    scraper = None

    try:
        # ==================================================
        # 1️⃣ HTTP 접근 체크
        # ==================================================
        http_result = check_url_status(LIST_URL)
        url_status = http_result["status"]

        result["checks"]["http"] = {
            "ok": url_status == URLStatus.OK,
            "status_code": http_result.get("status_code"),
            "verify_ssl": http_result.get("verify_ssl", True),
        }

        if url_status != URLStatus.OK:
            raise HealthCheckError(
                map_urlstatus_to_health_error(url_status),
                "감독행정작용 목록 페이지 HTTP 접근 실패",
                LIST_URL,
            )

        # ==================================================
        # 2️⃣ 목록 페이지 로딩
        # ==================================================
        scraper = FSSAdminScraper()
        driver = scraper.driver
        wait = WebDriverWait(driver, 10)

        driver.get(LIST_URL)

        rows = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "div.bd-list.ovx table tbody tr")
            )
        )

        if not rows:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "감독행정작용 목록 데이터 없음",
                "div.bd-list.ovx table tbody tr",
            )

        result["checks"]["list"] = {
            "ok": True,
            "count": len(rows),
        }

        # ==================================================
        # 3️⃣ 상세 페이지 접근
        # ==================================================
        first_row = rows[0]

        title_el = first_row.find_element(
            By.CSS_SELECTOR, "td.title a[href]"
        )

        detail_url = title_el.get_attribute("href")
        title_text = title_el.text.strip()

        if not detail_url:
            raise HealthCheckError(
                HealthErrorType.NO_DETAIL_URL,
                "상세 페이지 URL 누락",
                "td.title a[href]",
            )

        driver.get(detail_url)

        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "body")
            )
        )

        result["checks"]["detail"] = {
            "ok": True,
            "url": detail_url,
            "title": title_text,
        }

        # ==================================================
        # 4️⃣ 첨부파일 링크 존재 여부 (있을 때만 생성)
        # ==================================================
        file_links = driver.find_elements(
            By.CSS_SELECTOR, "a[href*='hpdownload']"
        )

        if file_links:
            result["checks"]["file_download"] = {
                "success": True,
                "file_count": len(file_links),
                "message": "첨부파일 링크 존재",
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
                HealthErrorType.UNKNOWN,
                str(e),
            ),
        )

    finally:
        result["elapsed_ms"] = int(
            (time.perf_counter() - start_ts) * 1000
        )

        if scraper and scraper.driver:
            scraper.driver.quit()

    return result


# ==================================================
# scheduler call
# ==================================================
def run():
    scraper = FSSAdminScraper()
    scraper.run()  # max_pages=None이면 자동으로 총 페이지 수 감지

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Health Check 실행")
    args = parser.parse_args()
     
    if args.check:
        result = fss_admin_health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scraper = FSSAdminScraper()
    scraper.run()  # max_pages=None이면 자동으로 총 페이지 수 감지