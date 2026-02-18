"""
금융위원회 행정지도 스크래퍼
금융위원회의 행정지도 데이터를 수집합니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
def find_project_root():
    """common 디렉토리를 찾을 때까지 상위 디렉토리로 이동"""
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

import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import re
import csv
import logging
import argparse
from typing import List, Dict, Optional
from datetime import datetime, date
from common.base_scraper import BaseScraper
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

sys.stdout.reconfigure(encoding='utf-8')

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FSCGuidelineScraper(BaseScraper):
    """금융위원회 행정지도 스크래퍼"""
    
    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        
        # 출력 디렉토리 설정
        self.base_dir = Path(__file__).resolve().parent
        self.output_dir = self.base_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "csv").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "json").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "downloads").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "debug").mkdir(parents=True, exist_ok=True)
        
        # 금융위원회 URL
        self.url_config = {
            'name': '금융위원회_행정지도',
            'base_url': 'https://better.fsc.go.kr',
            'list_url': 'https://better.fsc.go.kr/fsc_new/status/adminMap/OpertnList.do?stNo=11&muNo=145&muGpNo=60&pageIndex={page}',
            'detail_base': 'https://better.fsc.go.kr/fsc_new/status/adminMap/'
        }
        
        self.results = []
        self.last_scrape_dates = {}  # 마지막 스크래핑 날짜
        
        # 결과 파일 경로
        self.result_file = self.output_dir / "json" / "fsc_guideline_results.json"
    
    def get_last_scrape_date(self) -> Optional[date]:
        """결과 JSON 파일에서 마지막 스크래핑 날짜를 읽어옵니다"""
        if not self.result_file.exists():
            return None
        
        try:
            with open(self.result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Law_Scraper 형식: 메타데이터에 last_scrape_date가 있음
                if isinstance(data, dict) and 'last_scrape_date' in data:
                    date_dict = data.get('last_scrape_date', {})
                    # FSC는 단일 소스이므로 'fsc_guidance' 키 사용
                    date_str = date_dict.get('fsc_guidance')
                    if date_str:
                        return datetime.strptime(date_str, '%Y%m%d').date()
        except Exception as e:
            logger.warning(f"마지막 스크래핑 날짜 읽기 실패: {e}")
        
        return None
    
    def parse_date(self, date_str: str) -> Optional[date]:
        """시행일 문자열을 date 객체로 변환합니다 (여러 형식 지원)"""
        if not date_str:
            return None
        
        # 공백 제거
        date_str = date_str.strip()
        
        # 여러 날짜 형식 시도
        date_formats = [
            '%Y-%m-%d',      # 2025-11-17
            '%Y.%m.%d',      # 2025.11.17
            '%Y/%m/%d',      # 2025/11/17
            '%Y%m%d',        # 20251117
            '%Y-%m-%d %H:%M:%S',  # 2025-11-17 00:00:00
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.date()
            except:
                continue
        
        # 숫자만 있는 경우 (YYYYMMDD)
        if date_str.isdigit() and len(date_str) == 8:
            try:
                return datetime.strptime(date_str, '%Y%m%d').date()
            except:
                pass
        
        return None
        
    def get_page(self, url: str, retry: int = 3) -> Optional[requests.Response]:
        """페이지 가져오기 (재시도 로직 포함)"""
        for i in range(retry):
            try:
                response = self.session.get(url, timeout=30, verify=False)
                response.raise_for_status()
                if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
                return response
            except Exception as e:
                logger.error(f"페이지 로드 실패 (시도 {i+1}/{retry}): {e}")
                if i < retry - 1:
                    time.sleep(2)
                else:
                    raise
        return None
    
    def scrape_list_page(self, page_index: int) -> List[Dict]:
        """금융위원회 목록 페이지 스크래핑 (DataTables 사용)"""
        url = self.url_config['list_url'].format(page=page_index)
        
        logger.info(f"[{self.url_config['name']}] 페이지 {page_index} 스크래핑 중...")
        print(f"\n[{self.url_config['name']}] 페이지 {page_index} 스크래핑 중...")
        
        items = []
        
        # DataTables는 JavaScript로 동적 로드되므로 Selenium 사용
        # DataTables는 항상 JavaScript로 로드되므로 Selenium을 먼저 사용
        try:
            chrome_options = self._build_default_chrome_options()
            driver = self._create_webdriver(chrome_options)
            
            try:
                driver.get(url)
                wait = WebDriverWait(driver, 30)
                
                # 첫 번째 페이지일 때만 필터링 적용
                if page_index == 1:
                    # 필터링 요소들이 로드될 때까지 기다리기
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#searchStartDt")))
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#searchAddFild4")))
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#searchBtn")))
                    
                    # 시행일 시작일 입력: '2000-01-01'
                    start_date_input = driver.find_element(By.CSS_SELECTOR, "#searchStartDt")
                    start_date_input.clear()
                    start_date_input.send_keys('2000-01-01')
                    logger.info("시작일 '2000-01-01' 입력 완료")
                    
                    # 시행여부 선택: '시행중' (option:nth-child(2))
                    status_select = driver.find_element(By.CSS_SELECTOR, "#searchAddFild4")
                    select = Select(status_select)
                    # option:nth-child(2) 선택 (value가 '시행중')
                    option = driver.find_element(By.CSS_SELECTOR, "#searchAddFild4 > option:nth-child(2)")
                    select.select_by_value(option.get_attribute('value'))
                    logger.info(f"시행여부 '{option.get_attribute('value')}' 선택 완료")
                    
                    # 검색 버튼 클릭
                    search_btn = driver.find_element(By.CSS_SELECTOR, "#searchBtn")
                    search_btn.click()
                    logger.info("검색 버튼 클릭 완료")
                    
                    # 검색 결과가 로드될 때까지 기다리기
                    time.sleep(2)
                else:
                    # 두 번째 페이지 이후: DataTables 페이지네이션 버튼 클릭
                    # 페이지네이션 버튼 찾기 (예: "2", "3" 등의 페이지 번호)
                    try:
                        # DataTables 페이지네이션에서 해당 페이지 번호 버튼 찾기
                        page_buttons = driver.find_elements(By.CSS_SELECTOR, ".dataTables_paginate a")
                        for btn in page_buttons:
                            if btn.text.strip() == str(page_index):
                                btn.click()
                                logger.info(f"페이지 {page_index}로 이동")
                                time.sleep(2)
                                break
                    except Exception as e:
                        logger.warning(f"페이지네이션 버튼 클릭 실패: {e}")
                
                # DataTables가 로드될 때까지 기다리기 (#DataTables_Table_0 테이블이 나타날 때까지)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#DataTables_Table_0")))
                # 추가로 DataTables의 tbody에 데이터가 로드될 때까지 기다림
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr")))
                # DataTables의 processing이 완료될 때까지 추가 대기
                time.sleep(2)
                
                html = driver.page_source
                soup = BeautifulSoup(html, 'lxml')
                
                # #DataTables_Table_0 테이블 찾기
                table = soup.select_one('#DataTables_Table_0')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) < 3:
                                continue
                            
                            try:
                                # 테이블 구조: 연번(0), 기관(1), 제목(2), 소관부서(3), 시행일(4), 시행여부(5)
                                제목_셀 = cells[2] if len(cells) > 2 else cells[1]
                                제목 = 제목_셀.get_text(strip=True)
                                if not 제목:
                                    continue
                                
                                시행일 = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                                
                                link = 제목_셀.find('a', href=True)
                                detail_url = None
                                if link:
                                    href = link.get('href', '')
                                    if href.startswith('./'):
                                        detail_url = urljoin(self.url_config['detail_base'], href[2:])
                                    elif href.startswith('/'):
                                        detail_url = urljoin(self.url_config['base_url'], href)
                                    elif href.startswith('http'):
                                        detail_url = href
                                    elif href.startswith('javascript:'):
                                        # JavaScript 링크는 나중에 처리
                                        detail_url = href
                                    else:
                                        detail_url = urljoin(url, href)
                                
                                items.append({
                                    '제목': 제목,
                                    '시행일': 시행일,
                                    '링크': detail_url,
                                    '_상세페이지URL': detail_url
                                })
                            except Exception as e:
                                logger.error(f"Selenium으로 추출 중 오류: {e}")
                                continue
            finally:
                driver.quit()
        except Exception as e:
            logger.error(f"Selenium 사용 중 오류: {e}")
            # 폴백: BaseScraper의 fetch_page 메서드 사용
            soup = self.fetch_page(url, use_selenium=True)
            if soup:
                table = soup.select_one('#DataTables_Table_0')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) < 3:
                                continue
                            
                            try:
                                제목_셀 = cells[2] if len(cells) > 2 else cells[1]
                                제목 = 제목_셀.get_text(strip=True)
                                if not 제목:
                                    continue
                                
                                시행일 = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                                
                                link = 제목_셀.find('a', href=True)
                                detail_url = None
                                if link:
                                    href = link.get('href', '')
                                    if href.startswith('./'):
                                        detail_url = urljoin(self.url_config['detail_base'], href[2:])
                                    elif href.startswith('/'):
                                        detail_url = urljoin(self.url_config['base_url'], href)
                                    elif href.startswith('http'):
                                        detail_url = href
                                    elif href.startswith('javascript:'):
                                        # JavaScript 링크는 나중에 처리
                                        detail_url = href
                                    else:
                                        detail_url = urljoin(url, href)
                                
                                items.append({
                                    '제목': 제목,
                                    '시행일': 시행일,
                                    '링크': detail_url,
                                    '_상세페이지URL': detail_url
                                })
                            except Exception as e:
                                logger.error(f"Selenium으로 추출 중 오류: {e}")
                                continue
        
        logger.info(f"페이지 {page_index}: {len(items)}개 항목 발견")
        return items
    
    def get_detail_data(self, detail_url: str) -> Dict:
        """상세 페이지에서 데이터 추출 - 필요한 필드만: 내용, 담당부서, 첨부파일링크, 첨부파일명"""
        detail_info = {
            '내용': '',
            '담당부서': '',
            '첨부파일링크': '',
            '첨부파일명': ''
        }
        
        if not detail_url:
            return detail_info
        
        try:
            # JavaScript 링크인 경우 POST 요청으로 변환
            if detail_url.startswith('javascript:'):
                # JavaScript 함수에서 ID 추출 (예: openOpertnDetail('5065'))
                match = re.search(r"openOpertnDetail\('(\d+)'\)", detail_url)
                if match:
                    post_no = match.group(1)
                    # 금융위원회 상세 페이지는 POST 방식으로 요청해야 함
                    detail_url = "https://better.fsc.go.kr/fsc_new/status/adminMap/OpertnDetail.do"
                    # POST 파라미터 준비
                    post_data = {
                        'muNo': '145',
                        'postNo': post_no,
                        'stNo': '11',
                        'prevStNo': '11',
                        'prevMuNo': '145',
                        'prevTab1': '',
                        'prevTab2': '',
                        'actCd': 'R'
                    }
                    logger.info(f"JavaScript 링크를 POST 요청으로 변환: {detail_url}, postNo={post_no}")
                    
                    # POST 요청으로 상세 페이지 가져오기
                    response = self.session.post(detail_url, data=post_data, timeout=30, verify=False)
                    response.raise_for_status()
                    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                        response.encoding = response.apparent_encoding or 'utf-8'
                    soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
                else:
                    logger.warning(f"JavaScript 링크를 파싱할 수 없습니다: {detail_url}")
                    return detail_info
            else:
                # 일반 URL인 경우 (Selenium 사용)
                soup = self.fetch_page(detail_url, use_selenium=True)
                if not soup:
                    return detail_info
            
            # 디버그용 HTML 저장 (항상 저장하여 구조 확인)
            debug_file = self.output_dir / "debug" / f"detail_{self.url_config['name'].replace(' ', '_')}_{int(time.time())}.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            logger.info(f"디버그 HTML 저장: {debug_file}")
            
            # 금융위원회 상세 페이지 구조 추출
            # 실제 구조에 맞게 수정 필요
            content_selectors = [
                '.content',
                '#content',
                '.view_content',
                'div[class*="content"]',
                'div[class*="view"]'
            ]
            
            for selector in content_selectors:
                content_div = soup.select_one(selector)
                if content_div:
                    for br in content_div.find_all('br'):
                        br.replace_with('\n')
                    text = content_div.get_text(separator='\n', strip=True)
                    if text and len(text) > 50:
                        detail_info['내용'] = text
                        break
            
            # 담당부서와 첨부파일 추출 (실제 구조 확인 후 수정 필요)
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                for row in rows:
                    th_elements = row.find_all('th')
                    td_elements = row.find_all('td')
                    
                    if th_elements and td_elements:
                        key = th_elements[0].get_text(strip=True)
                        value_td = td_elements[0]
                        value = value_td.get_text(strip=True)
                        
                        # 첨부파일 추출
                        if ('첨부파일' in key or '첨부 파일' in key or '첨부' in key) and not detail_info['첨부파일명']:
                            file_links = value_td.find_all('a', href=True)
                            file_names = []
                            file_urls = []
                            for link in file_links:
                                file_name = link.get_text(strip=True)
                                file_href = link.get('href', '')
                                if file_name:
                                    file_names.append(file_name)
                                    if file_href.startswith('./'):
                                        file_url = urljoin(detail_url, file_href)
                                    elif file_href.startswith('/'):
                                        file_url = urljoin(detail_url, file_href)
                                    elif file_href.startswith('http'):
                                        file_url = file_href
                                    else:
                                        file_url = urljoin(detail_url, file_href)
                                    file_urls.append(file_url)
                            
                            if file_names:
                                detail_info['첨부파일명'] = ' | '.join(file_names)
                                detail_info['첨부파일링크'] = ' | '.join(file_urls)
                        # 담당부서 추출 ('>'로 분리해서 마지막 단어만 가져오기)
                        elif ('담당부서' in key or '소관부서' in key) and not detail_info['담당부서']:
                            # '>'로 분리해서 마지막 단어만 가져오기
                            if '>' in value:
                                parts = [p.strip() for p in value.split('>')]
                                detail_info['담당부서'] = parts[-1] if parts else value
                            else:
                                detail_info['담당부서'] = value.strip()
            
        except Exception as e:
            logger.error(f"상세 페이지 처리 중 오류: {e}")
            print(f"  상세 페이지 처리 중 오류: {e}")
        
        return detail_info
    
    def get_total_pages(self) -> int:
        """총 페이지 수 확인"""
        try:
            url = self.url_config['list_url'].format(page=1)
            response = self.get_page(url)
            if not response:
                return 1
            
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
            
            max_page = 1
            
            # 페이지네이션 링크 찾기
            page_links = soup.find_all('a', href=re.compile(r'pageIndex=\d+'))
            
            for link in page_links:
                href = link.get('href', '')
                match = re.search(r'pageIndex=(\d+)', href)
                if match:
                    try:
                        page_num = int(match.group(1))
                        max_page = max(max_page, page_num)
                    except:
                        pass
                
                text = link.get_text(strip=True)
                if text.isdigit():
                    try:
                        page_num = int(text)
                        max_page = max(max_page, page_num)
                    except:
                        pass
            
            # 총 건수로 계산
            page_text = soup.get_text()
            patterns = [
                r'총\s*(\d+)\s*건',
                r'전체\s*(\d+)\s*건',
                r'(\d+)\s*건\s*전체',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    try:
                        total_count = int(match.group(1))
                        items_per_page = 10
                        calculated_pages = (total_count + items_per_page - 1) // items_per_page
                        max_page = max(max_page, calculated_pages)
                        break
                    except:
                        continue
            
            return max(max_page, 1)
        except Exception as e:
            logger.warning(f"총 페이지 수 확인 실패: {e}, 기본값 1페이지로 진행")
            return 1
    
    def scrape_all(self) -> List[Dict]:
        """모든 데이터 스크래핑"""
        # 마지막 스크래핑 날짜 확인
        last_scrape_date = self.get_last_scrape_date()
        if last_scrape_date:
            logger.info(f"마지막 스크래핑 날짜: {last_scrape_date.strftime('%Y-%m-%d')} 이후의 항목만 수집합니다.")
            print(f"마지막 스크래핑 날짜: {last_scrape_date.strftime('%Y-%m-%d')} 이후의 항목만 수집합니다.")
        else:
            logger.info("마지막 스크래핑 날짜가 없어 모든 항목을 수집합니다.")
            print("마지막 스크래핑 날짜가 없어 모든 항목을 수집합니다.")
        
        logger.info("=" * 60)
        logger.info("금융위원회 행정지도 스크래핑 시작")
        logger.info("=" * 60)
        print("=" * 60)
        print("금융위원회 행정지도 스크래핑 시작")
        print("=" * 60)
        
        # 총 페이지 수 확인
        total_pages = self.get_total_pages()
        logger.info(f"총 {total_pages}페이지를 스크랩핑합니다.")
        print(f"총 {total_pages}페이지를 스크랩핑합니다.")
        
        all_items = []
        seen_numbers = set()
        page = 1
        consecutive_empty = 0
        max_empty_pages = 3
        old_items_count = 0  # 마지막 스크래핑 날짜 이전 항목 수
        
        while page <= total_pages:
            items = self.scrape_list_page(page)
            
            if not items:
                consecutive_empty += 1
                if consecutive_empty >= max_empty_pages:
                    logger.info(f"페이지 {page}에서 연속 {consecutive_empty}페이지에서 항목이 없어 수집을 종료합니다.")
                    break
                page += 1
                time.sleep(1)
                continue
            
            consecutive_empty = 0
            
            # 날짜 필터링 및 중복 제거
            new_items = []
            for item in items:
                # 중복 제거 (제목 기준)
                제목 = item.get('제목', '')
                if 제목 and 제목 in seen_numbers:
                    continue
                
                # 날짜 필터링
                if last_scrape_date:
                    시행일_str = item.get('시행일', '')
                    시행일 = self.parse_date(시행일_str)
                    
                    if 시행일:
                        if 시행일 <= last_scrape_date:
                            old_items_count += 1
                            continue  # 마지막 스크래핑 날짜 이전 항목은 건너뜀
                    else:
                        # 날짜가 없는 항목은 처리하지 않음 (안전을 위해)
                        logger.warning(f"날짜가 없는 항목 발견: {제목}")
                        continue
                
                if 제목:
                    seen_numbers.add(제목)
                new_items.append(item)
            
            all_items.extend(new_items)
            logger.info(f"페이지 {page}/{total_pages}: {len(items)}개 항목 발견, {len(new_items)}개 신규 항목, 누적 수집: {len(all_items)}건")
            print(f"  페이지 {page}/{total_pages}: {len(items)}개 항목 발견, {len(new_items)}개 신규 항목, 누적 수집: {len(all_items)}건")
            
            # 마지막 스크래핑 날짜 이후 항목이 없으면 더 이상 진행할 필요 없음
            # 하지만 페이지 순서가 최신순이 아닐 수 있으므로 계속 진행
            # 대신 연속으로 오래된 항목만 나오면 종료
            if last_scrape_date and len(new_items) == 0:
                old_items_count += len(items)
                if old_items_count >= 20:  # 연속으로 20개 이상 오래된 항목이면 종료
                    logger.info(f"연속으로 오래된 항목이 많아 수집을 종료합니다.")
                    break
            
            time.sleep(self.delay)
            page += 1
        
        logger.info(f"총 {len(all_items)}개 항목 수집 완료")
        print(f"\n총 {len(all_items)}개 항목 수집 완료")
        
        # 상세 정보 추출
        logger.info("상세 정보 추출 시작...")
        print("\n상세 정보 추출 시작...")
        
        for idx, item in enumerate(all_items, 1):
            title_preview = item.get('제목', '')[:50]
            logger.info(f"[{idx}/{len(all_items)}] {title_preview} 처리 중...")
            print(f"\n[{idx}/{len(all_items)}] {title_preview} 처리 중...")
            
            # 필요한 필드만 포함하는 최종 결과 딕셔너리
            final_item = {
                '출처': self.url_config['name'],
                '제목': item.get('제목', ''),
                '시행일': item.get('시행일', ''),
                '내용': '',
                '담당부서': '',
                '링크': item.get('링크', ''),
                '첨부파일링크': '',
                '첨부파일명': ''
            }
            
            if item.get('_상세페이지URL'):
                detail_info = self.get_detail_data(item['_상세페이지URL'])
                final_item['내용'] = detail_info.get('내용', '')
                # 담당부서: '>'로 분리해서 마지막 단어만 가져오기
                담당부서 = detail_info.get('담당부서', '')
                if '>' in 담당부서:
                    parts = [p.strip() for p in 담당부서.split('>')]
                    final_item['담당부서'] = parts[-1] if parts else 담당부서
                else:
                    final_item['담당부서'] = 담당부서.strip()
                final_item['첨부파일링크'] = detail_info.get('첨부파일링크', '')
                final_item['첨부파일명'] = detail_info.get('첨부파일명', '')
            else:
                logger.warning("상세 페이지 URL이 없습니다.")
            
            self.results.append(final_item)
            time.sleep(self.delay * 0.5)
        
        # 스크래핑 완료 후 현재 날짜 저장
        today = date.today()
        self.last_scrape_dates['fsc_guidance'] = today.strftime('%Y%m%d')
        
        logger.info(f"스크래핑 완료. 총 {len(self.results)}개 항목 수집.")
        print(f"\n스크래핑 완료. 총 {len(self.results)}개 항목 수집.")
        
        return self.results
    
    def save_results(self, filename: str = 'fsc_guideline_results.json'):
        """결과를 JSON과 CSV 파일로 저장 (Law_Scraper 형식)"""
        # Law_Scraper 형식으로 데이터 구성
        crawled_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # URL 목록 생성
        urls_list = [self.url_config['list_url'].format(page=1)]
        
        # 결과 데이터 구성
        result_data = {
            'urls': urls_list,
            'crawled_at': crawled_at,
            'total_count': len(self.results),
            'last_scrape_date': self.last_scrape_dates,  # 마지막 스크래핑 날짜
            'results': self.results
        }
        
        # JSON 저장
        json_path = self.output_dir / "json" / filename
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        logger.info(f"결과가 {json_path}에 저장되었습니다. (총 {len(self.results)}개)")
        print(f"\n결과가 {json_path}에 저장되었습니다. (총 {len(self.results)}개)")
        
        # CSV 저장
        try:
            csv_filename = filename.replace('.json', '.csv')
            csv_path = self.output_dir / "csv" / csv_filename
            
            if self.results:
                # 필요한 필드명만 사용
                fieldnames = ['출처', '제목', '시행일', '내용', '담당부서', '링크', '첨부파일링크', '첨부파일명']
                
                with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(
                        f, 
                        fieldnames=fieldnames, 
                        extrasaction='ignore',
                        quoting=csv.QUOTE_ALL
                    )
                    writer.writeheader()
                    
                    for item in self.results:
                        row = {}
                        for field in fieldnames:
                            value = item.get(field, '')
                            if value is None:
                                value = ''
                            str_value = str(value)
                            # 연속된 줄바꿈을 2개로 제한
                            str_value = re.sub(r'\n{3,}', '\n\n', str_value)
                            row[field] = str_value
                        writer.writerow(row)
                
                logger.info(f"CSV 파일도 {csv_path}에 저장되었습니다.")
                print(f"CSV 파일도 {csv_path}에 저장되었습니다.")
        except Exception as e:
            logger.error(f"CSV 저장 중 오류: {e}")
            print(f"CSV 저장 중 오류: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='금융위원회 행정지도 스크래퍼',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python fsc_guideline_scraper.py
        """
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='요청 간 대기 시간 (초, 기본값: 1.0)'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("스크래퍼 시작")
    logger.info("=" * 60)
    
    scraper = FSCGuidelineScraper(delay=args.delay)
    results = scraper.scrape_all()
    scraper.save_results()
    
    logger.info("=" * 60)
    logger.info("스크래핑 완료!")
    logger.info(f"총 {len(results)}개 데이터 수집")
    logger.info("=" * 60)
    
    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

