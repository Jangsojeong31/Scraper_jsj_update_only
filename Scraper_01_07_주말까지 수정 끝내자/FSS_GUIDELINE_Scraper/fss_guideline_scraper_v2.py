# fss_guideline_scraper_v2

"""
금융감독원 행정지도 및 행정작용 스크래퍼
금융감독원의 행정지도와 행정작용 데이터를 수집합니다.
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


class FSSGuidelineScraper(BaseScraper):
    """금융감독원 행정지도 및 행정작용 스크래퍼"""
    
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
        
        # 두 개의 대상 URL
        self.urls = {
            'fss_action': {
                'name': '금융감독원_행정작용',
                'base_url': 'https://www.fss.or.kr',
                'list_url': 'https://www.fss.or.kr/fss/job/admnstgudcDtls/list.do?menuNo=200494&pageIndex={page}&searchRegn=&searchYear=&searchCecYn=Y&searchWrd=',
                'detail_base': 'https://www.fss.or.kr/fss/job/admnstgudcDtls/'
            },
            'fss_guidance': {
                'name': '금융감독원_행정지도',
                'base_url': 'https://www.fss.or.kr',
                'list_url': 'https://www.fss.or.kr/fss/job/admnstgudc/list.do?menuNo=200492&pageIndex={page}&searchRegn=&searchYear=&searchCecYn=Y&searchWrd=',
                'detail_base': 'https://www.fss.or.kr/fss/job/admnstgudc/'
            }
        }
        
        self.results = []
        self.all_results = []  # 모든 소스의 결과를 통합
        self.last_scrape_dates = {}  # 각 소스별 마지막 스크래핑 날짜
        
        # 결과 파일 경로
        self.result_file = self.output_dir / "json" / "fss_guideline_results.json"
    
    def get_last_scrape_date(self, source_key: str) -> Optional[date]:
        """결과 JSON 파일에서 마지막 스크래핑 날짜를 읽어옵니다"""
        if not self.result_file.exists():
            return None
        
        try:
            with open(self.result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Law_Scraper 형식: 메타데이터에 last_scrape_date가 있음
                if isinstance(data, dict) and 'last_scrape_date' in data:
                    date_dict = data.get('last_scrape_date', {})
                    date_str = date_dict.get(source_key)
                    if date_str:
                        return datetime.strptime(date_str, '%Y%m%d').date()
        except Exception as e:
            logger.warning(f"마지막 스크래핑 날짜 읽기 실패: {e}")
        
        return None
    
    def parse_date(self, date_str: str) -> Optional[date]:
        """시행일 문자열을 date 객체로 변환합니다 (YYYYMMDD 형식)"""
        if not date_str or len(date_str) != 8:
            return None
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except:
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
    
    def scrape_list_page(self, url_config: Dict, page_index: int) -> List[Dict]:
        """금융감독원 목록 페이지 스크래핑"""
        url = url_config['list_url'].format(page=page_index)
        
        logger.info(f"[{url_config['name']}] 페이지 {page_index} 스크래핑 중...")
        print(f"\n[{url_config['name']}] 페이지 {page_index} 스크래핑 중...")
        
        response = self.get_page(url)
        if not response:
            return []
        
        soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
        
        table = soup.find('table')
        if not table:
            logger.warning(f"페이지 {page_index}: 테이블을 찾을 수 없습니다")
            return []
        
        rows = table.find_all('tr')[1:]  # 첫 번째 행은 헤더
        items = []
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 5:
                continue
            
            try:
                # 목록 정보 추출 - 필요한 필드만
                제목_셀 = cells[1]
                제목 = 제목_셀.get_text(strip=True)
                시행일 = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                
                # 제목 링크에서 상세 페이지 URL 추출
                link = 제목_셀.find('a', href=True)
                detail_url = None
                if link:
                    href = link.get('href', '')
                    if href.startswith('./'):
                        detail_url = urljoin(url_config['detail_base'], href[2:])
                    elif href.startswith('/'):
                        detail_url = urljoin(url_config['base_url'], href)
                    elif href.startswith('http'):
                        detail_url = href
                    else:
                        detail_url = urljoin(url, href)
                
                items.append({
                    '제목': 제목,
                    '시행일': 시행일,
                    '링크': detail_url,
                    '_상세페이지URL': detail_url  # 내부용
                })
                
            except Exception as e:
                logger.error(f"행 처리 중 오류: {e}")
                continue
        
        logger.info(f"페이지 {page_index}: {len(items)}개 항목 발견")
        return items
    
    def get_detail_data(self, detail_url: str, source_name: str) -> Dict:
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
            response = self.get_page(detail_url)
            if not response:
                return detail_info
            
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
            
            # 디버그용 HTML 저장 (첫 번째 페이지만)
            debug_file = self.output_dir / "debug" / f"detail_{source_name.replace(' ', '_')}.html"
            if not debug_file.exists():
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(soup.prettify())
            
            # 방법 1: CSS 셀렉터를 사용한 dl/dt/dd 구조에서 추출
            bd_view = soup.select_one('#content > div.bd-view')
            if bd_view:
                # 담당부서 추출: dl:nth-child(4)의 dt가 "담당부서"이고 dd가 값
                dl_elements = bd_view.find_all('dl')
                for dl in dl_elements:
                    dt_elements = dl.find_all('dt')
                    dd_elements = dl.find_all('dd')
                    
                    for dt, dd in zip(dt_elements, dd_elements):
                        dt_text = dt.get_text(strip=True)
                        if ('담당부서' in dt_text or '소관부서' in dt_text) and not detail_info['담당부서']:
                            detail_info['담당부서'] = dd.get_text(strip=True)
                            break
                    
                    # 첨부파일 추출: dl:nth-child(7)의 dd 안에 있는 링크들
                    if not detail_info['첨부파일명']:
                        # dd 안의 모든 링크 찾기
                        dd_elements = dl.find_all('dd')
                        for dd in dd_elements:
                            file_links = dd.find_all('a', href=True)
                            if file_links:
                                file_names = []
                                file_urls = []
                                for link in file_links:
                                    # 첨부파일명: span > span 구조에서 추출 시도
                                    span_spans = link.find_all('span')
                                    file_name = ''
                                    if span_spans:
                                        # 가장 안쪽 span의 텍스트
                                        for span in reversed(span_spans):
                                            span_text = span.get_text(strip=True)
                                            if span_text:
                                                file_name = span_text
                                                break
                                    # span이 없거나 텍스트가 없으면 링크 텍스트 사용
                                    if not file_name:
                                        file_name = link.get_text(strip=True)
                                    
                                    file_href = link.get('href', '')
                                    if file_name or file_href:
                                        if file_name:
                                            file_names.append(file_name)
                                        else:
                                            # 파일명이 없으면 href에서 추출
                                            file_name = file_href.split('/')[-1].split('?')[0]
                                            if file_name:
                                                file_names.append(unquote(file_name))
                                        
                                        # URL 정규화
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
                                    break
                    
                    if detail_info['담당부서'] and detail_info['첨부파일명']:
                        break
            
            # 방법 2: 테이블에서 정보 추출 (fallback)
            if not detail_info['담당부서'] or not detail_info['첨부파일명']:
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
                            # 담당부서 추출
                            elif ('담당부서' in key or '소관부서' in key) and not detail_info['담당부서']:
                                detail_info['담당부서'] = value
            
            # 본문 내용 추출: #content > div.bd-view > dl:nth-child(6) > dd > pre
            if bd_view:
                # dl:nth-child(6) 찾기 (6번째 dl 요소)
                dl_elements = bd_view.find_all('dl')
                if len(dl_elements) >= 6:
                    # 6번째 dl (인덱스 5)
                    target_dl = dl_elements[5]
                    dd_elements = target_dl.find_all('dd')
                    for dd in dd_elements:
                        pre_elements = dd.find_all('pre')
                        if pre_elements:
                            # pre 태그에서 내용 추출 (줄바꿈 유지)
                            content_parts = []
                            for pre in pre_elements:
                                # <br> 태그를 줄바꿈으로 변환
                                pre_copy = BeautifulSoup(str(pre), 'lxml')
                                for br in pre_copy.find_all('br'):
                                    br.replace_with('\n')
                                text = pre_copy.get_text(separator='\n', strip=False)
                                if text:
                                    content_parts.append(text)
                            
                            if content_parts:
                                detail_info['내용'] = '\n'.join(content_parts).strip()
                                break
            
            # Fallback: 기존 방식으로 추출 시도
            if not detail_info['내용']:
                soup_copy = BeautifulSoup(str(soup), 'lxml')
                for br in soup_copy.find_all('br'):
                    br.replace_with('\n')
                page_text = soup_copy.get_text(separator='\n', strip=False)
                
                if page_text:
                    # 시작 패턴 찾기
                    start_patterns = [
                        r'1\.\s*관련근거',
                        r'1\)\s*관련근거',
                        r'①\s*관련근거',
                        r'-\s*아\s*래\s*-',
                        r'-\s*아\s*래',
                    ]
                    
                    earliest_start = len(page_text)
                    best_pattern = None
                    
                    for start_pattern in start_patterns:
                        matches = list(re.finditer(start_pattern, page_text, re.IGNORECASE))
                        for match in matches:
                            if match.start() < earliest_start:
                                earliest_start = match.start()
                                best_pattern = start_pattern
                    
                    if best_pattern:
                        start_match = re.search(best_pattern, page_text, re.IGNORECASE)
                        if start_match:
                            start_pos = start_match.start()
                            remaining_text = page_text[start_pos:]
                            
                            # 담당부서 섹션 전까지 추출
                            end_patterns = [
                                r'\n\s*담당부서',
                                r'\n\s*소관부서',
                            ]
                            
                            end_pos = len(remaining_text)
                            for end_pattern in end_patterns:
                                end_match = re.search(end_pattern, remaining_text, re.IGNORECASE)
                                if end_match:
                                    end_pos = min(end_pos, end_match.start())
                            
                            content = remaining_text[:end_pos]
                            lines = content.split('\n')
                            filtered_lines = []
                            skip_keywords = [
                                '사이버 홍보관', '관련부속사이트', '본문검색', '메뉴검색'
                            ]
                            
                            for line in lines:
                                line_stripped = line.strip()
                                if not line_stripped:
                                    if filtered_lines and filtered_lines[-1] != '':
                                        filtered_lines.append('')
                                    continue
                                
                                if len(line_stripped) > 3:
                                    if not any(keyword in line_stripped for keyword in skip_keywords):
                                        filtered_lines.append(line_stripped)
                            
                            while filtered_lines and filtered_lines[-1] == '':
                                filtered_lines.pop()
                            
                            if filtered_lines:
                                detail_info['내용'] = '\n'.join(filtered_lines)
                
                # 추가 Fallback: content div에서 추출
                if not detail_info['내용']:
                    content_selectors = [
                        '.view_content',
                        '.content',
                        '#contents',
                        'div[class*="view"]',
                        'div[class*="content"]'
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
            
        except Exception as e:
            logger.error(f"상세 페이지 처리 중 오류: {e}")
            print(f"  상세 페이지 처리 중 오류: {e}")
        
        return detail_info
    
    def get_total_pages(self, url_config: Dict) -> int:
        """총 페이지 수 확인 - #content > div.count-total 셀렉터 사용"""
        try:
            url = url_config['list_url'].format(page=1)
            response = self.get_page(url)
            if not response:
                return 1
            
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
            
            # #content > div.count-total 셀렉터에서 정보 추출
            count_total = soup.select_one('#content > div.count-total')
            if count_total:
                count_text = count_total.get_text(strip=True)
                logger.info(f"count-total 텍스트: {count_text}")
                
                # 총 건수 추출 (예: "총 123건", "전체 123건")
                total_count = None
                count_patterns = [
                    r'총\s*(\d+)\s*건',
                    r'전체\s*(\d+)\s*건',
                    r'(\d+)\s*건',
                ]
                
                for pattern in count_patterns:
                    match = re.search(pattern, count_text)
                    if match:
                        try:
                            total_count = int(match.group(1).replace(',', ''))
                            logger.info(f"총 건수: {total_count}")
                            break
                        except:
                            continue
                
                # 페이지 수 추출 (예: "1/10", "전체 10페이지")
                total_pages = None
                page_patterns = [
                    r'(\d+)\s*/\s*(\d+)',  # "1/10" 형식
                    r'전체\s*(\d+)\s*페이지',
                    r'총\s*(\d+)\s*페이지',
                ]
                
                for pattern in page_patterns:
                    match = re.search(pattern, count_text)
                    if match:
                        try:
                            # "1/10" 형식인 경우 두 번째 숫자 사용
                            if '/' in match.group(0):
                                total_pages = int(match.group(2))
                            else:
                                total_pages = int(match.group(1))
                            logger.info(f"총 페이지 수: {total_pages}")
                            break
                        except:
                            continue
                
                # 총 건수로 페이지 수 계산 (페이지당 10개 가정)
                if total_pages:
                    return max(total_pages, 1)
                elif total_count:
                    items_per_page = 10
                    calculated_pages = (total_count + items_per_page - 1) // items_per_page
                    logger.info(f"총 건수({total_count})로 계산한 페이지 수: {calculated_pages}")
                    return max(calculated_pages, 1)
            
            # fallback: 기존 방식으로 페이지네이션 링크 찾기
            max_page = 1
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
            
            logger.info(f"페이지네이션에서 찾은 최대 페이지: {max_page}")
            return max(max_page, 1)
        except Exception as e:
            logger.warning(f"총 페이지 수 확인 실패: {e}, 기본값 1페이지로 진행")
            return 1
    
    def scrape_source(self, source_key: str) -> List[Dict]:
        """특정 소스의 모든 데이터 스크래핑"""
        url_config = self.urls[source_key]
        
        # 마지막 스크래핑 날짜 확인
        last_scrape_date = self.get_last_scrape_date(source_key)
        if last_scrape_date:
            logger.info(f"마지막 스크래핑 날짜: {last_scrape_date.strftime('%Y-%m-%d')} 이후의 항목만 수집합니다.")
            print(f"마지막 스크래핑 날짜: {last_scrape_date.strftime('%Y-%m-%d')} 이후의 항목만 수집합니다.")
        else:
            logger.info("마지막 스크래핑 날짜가 없어 모든 항목을 수집합니다.")
            print("마지막 스크래핑 날짜가 없어 모든 항목을 수집합니다.")
        
        logger.info("=" * 60)
        logger.info(f"{url_config['name']} 스크래핑 시작")
        logger.info("=" * 60)
        print("=" * 60)
        print(f"{url_config['name']} 스크래핑 시작")
        print("=" * 60)
        
        # 총 페이지 수 확인
        total_pages = self.get_total_pages(url_config)
        logger.info(f"총 {total_pages}페이지를 스크랩핑합니다.")
        print(f"총 {total_pages}페이지를 스크랩핑합니다.")
        
        all_items = []
        seen_numbers = set()
        page = 1
        consecutive_empty = 0
        max_empty_pages = 3
        old_items_count = 0  # 마지막 스크래핑 날짜 이전 항목 수
        
        while page <= total_pages:
            items = self.scrape_list_page(url_config, page)
            
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
                '출처': url_config['name'],
                '제목': item.get('제목', ''),
                '시행일': item.get('시행일', ''),
                '내용': '',
                '담당부서': '',
                '링크': item.get('링크', ''),
                '첨부파일링크': '',
                '첨부파일명': ''
            }
            
            if item.get('_상세페이지URL'):
                detail_info = self.get_detail_data(item['_상세페이지URL'], url_config['name'])
                final_item['내용'] = detail_info.get('내용', '')
                final_item['담당부서'] = detail_info.get('담당부서', '')
                final_item['첨부파일링크'] = detail_info.get('첨부파일링크', '')
                final_item['첨부파일명'] = detail_info.get('첨부파일명', '')
            else:
                logger.warning("상세 페이지 URL이 없습니다.")
            
            self.results.append(final_item)
            time.sleep(self.delay * 0.5)
        
        logger.info(f"스크래핑 완료. 총 {len(self.results)}개 항목 수집.")
        print(f"\n스크래핑 완료. 총 {len(self.results)}개 항목 수집.")
        
        return self.results
    
    def scrape_all(self, source_keys: Optional[List[str]] = None) -> List[Dict]:
        """모든 소스의 데이터 스크래핑
        
        Args:
            source_keys: 스크래핑할 소스 키 리스트. None이면 모든 소스 스크래핑
        """
        logger.info("=" * 60)
        logger.info("금융감독원 행정지도 및 행정작용 스크래핑 시작")
        logger.info("=" * 60)
        print("=" * 60)
        print("금융감독원 행정지도 및 행정작용 스크래핑 시작")
        print("=" * 60)
        
        # 소스 키가 지정되지 않으면 모든 소스 스크래핑
        if source_keys is None:
            source_keys = ['fss_action', 'fss_guidance']
        
        # 유효한 소스 키만 필터링
        valid_source_keys = [key for key in source_keys if key in self.urls]
        if not valid_source_keys:
            logger.warning("유효한 소스 키가 없습니다. 모든 소스를 스크래핑합니다.")
            valid_source_keys = ['fss_action', 'fss_guidance']
        
        logger.info(f"스크래핑 대상: {', '.join([self.urls[key]['name'] for key in valid_source_keys])}")
        print(f"스크래핑 대상: {', '.join([self.urls[key]['name'] for key in valid_source_keys])}")
        
        all_results = []
        last_scrape_dates = {}  # 각 소스별 마지막 스크래핑 날짜 추적
        
        # 각 소스별로 스크래핑
        for source_key in valid_source_keys:
            self.results = []  # 소스별로 초기화
            source_results = self.scrape_source(source_key)
            all_results.extend(source_results)
            # 스크래핑 완료 후 현재 날짜 저장
            today = date.today()
            last_scrape_dates[source_key] = today.strftime('%Y%m%d')
            logger.info(f"{self.urls[source_key]['name']}: {len(source_results)}개 항목 수집 완료")
            print(f"\n{self.urls[source_key]['name']}: {len(source_results)}개 항목 수집 완료")
            time.sleep(2)  # 소스 간 대기
        
        self.all_results = all_results
        self.last_scrape_dates = last_scrape_dates  # 마지막 스크래핑 날짜 저장
        return all_results
    
    def save_results(self, filename: str = 'fss_guideline_results.json'):
        """결과를 JSON과 CSV 파일로 저장 (Law_Scraper 형식)"""
        # Law_Scraper 형식으로 데이터 구성
        crawled_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # URL 목록 생성
        urls_list = []
        for source_key in self.urls.keys():
            url_config = self.urls[source_key]
            urls_list.append(url_config['list_url'].format(page=1))
        
        # 결과 데이터 구성
        result_data = {
            'urls': urls_list,
            'crawled_at': crawled_at,
            'total_count': len(self.all_results),
            'last_scrape_date': self.last_scrape_dates,  # 각 소스별 마지막 스크래핑 날짜
            'results': self.all_results
        }
        
        # JSON 저장
        json_path = self.output_dir / "json" / filename
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        logger.info(f"결과가 {json_path}에 저장되었습니다. (총 {len(self.all_results)}개)")
        print(f"\n결과가 {json_path}에 저장되었습니다. (총 {len(self.all_results)}개)")
        
        # CSV 저장
        try:
            csv_filename = filename.replace('.json', '.csv')
            csv_path = self.output_dir / "csv" / csv_filename
            
            if self.all_results:
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
                    
                    for item in self.all_results:
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

# -------------------------------------------------
# Health Check 모드
# -------------------------------------------------
from datetime import datetime
from typing import Dict
import time

from datetime import datetime
from typing import Dict

from common.common_http import check_url_status
from common.url_health_mapper import map_urlstatus_to_health_error

from common.constants import URLStatus, LegalDocProvided
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error


def fss_guideline_check() -> Dict:
    """
    금융감독원 행정지도 / 행정작용 헬스체크
    - HealthErrorType을 스크래퍼 내부에서 명시적으로 raise
    - 동일 오류 연속 발생 Alert 대응 가능 구조
    """
     # 두 개의 대상 URL
    urls = {
        'fss_guidance': {
            'name': '금융감독원_행정지도',
            'base_url': 'https://www.fss.or.kr',
            'list_url': 'https://www.fss.or.kr/fss/job/admnstgudc/list.do?menuNo=200492&pageIndex={page}&searchRegn=&searchYear=&searchCecYn=Y&searchWrd=',
            'detail_base': 'https://www.fss.or.kr/fss/job/admnstgudc/'
        }
     }
    
    LIST_URL = (
        "https://www.fss.or.kr/fss/job/admnstgudc/"
        "list.do?menuNo=200492&pageIndex={page}"
        "&searchRegn=&searchYear=&searchCecYn=Y&searchWrd="
    )

    result = base_health_output(
        auth_src="금융감독원 > 행정지도 · 행정작용",
        scraper_id="FSS_GUIDELINE",
        target_url=LIST_URL,
    )

    try:
        scraper = FSSGuidelineScraper()
        session = scraper.session

        # ==================================================
        # 1️⃣ HTTP 체크 (항상 생성)
        # ==================================================
        http_result = check_url_status(LIST_URL)

        result["checks"]["http"] = {
            "ok": http_result["status"] == URLStatus.OK,
            "status_code": http_result["http_code"],
            "verify_ssl": True,
        }

        if http_result["status"] != URLStatus.OK:
            raise HealthCheckError(
                map_urlstatus_to_health_error(http_result["status"]),
                "목록 페이지 HTTP 접근 실패",
                LIST_URL,
            )
        
#        for source_key, cfg in scraper.urls.items():
        for source_key, cfg in scraper.urls.items():
            # ======================================================
            # 1️⃣ 목록 페이지 점검 (1건)
            # ======================================================
            list_items = scraper.scrape_list_page(cfg, page_index=1)

            if not list_items:
                raise HealthCheckError(
                    HealthErrorType.NO_LIST_DATA,
                    f"[{cfg['name']}] 목록 데이터 없음",
                    selector="table > tbody > tr"
                )

            first = list_items[0]

#            result["checks"][f"{source_key}_list"] = {
            result["checks"]["list"] = {                
                "url": cfg["list_url"].format(page=1),
                "success": True,
                "title": first.get("제목", "")
            }

            # ======================================================
            # 2️⃣ 상세 페이지 점검
            # ======================================================
            detail_url = first.get("_상세페이지URL")
            if not detail_url:
                raise HealthCheckError(
                    HealthErrorType.NO_DETAIL_URL,
                    "상세 페이지 URL 누락",
                    field="_상세페이지URL"
                )

            detail_data = scraper.get_detail_data(detail_url, cfg["name"])
            content = detail_data.get("내용", "").strip()

            if not content:
                raise HealthCheckError(
                    HealthErrorType.CONTENT_EMPTY,
                    "상세 페이지 본문 비어 있음",
                    url=detail_url
                )

            result["checks"]["detail"] = {                
                "url": detail_url,
                "success": True,
                "content_length": len(content)
            }

            # ======================================================
            # 3️⃣ 첨부파일 점검 (HEAD)
            # ======================================================
            file_links = detail_data.get("첨부파일링크", "")
            if file_links:
                file_url = file_links.split(" | ")[0]

                try:
                    resp = session.head(
                        file_url,
                        timeout=15,
                        allow_redirects=True,
                        verify=False
                    )

                    if resp.status_code >= 400:
                        raise HealthCheckError(
                            HealthErrorType.FILE_DOWNLOAD_FAILED,
                            f"첨부파일 접근 실패 (HTTP {resp.status_code})",
                            url=file_url
                        )

                    result["checks"]["file_download"] = {                        
                        "url": file_url,
                        "success": True
                    }

                except HealthCheckError:
                    raise
                except Exception as e:
                    raise HealthCheckError(
                        HealthErrorType.FILE_DOWNLOAD_FAILED,
                        str(e),
                        url=file_url
                    )

            else:
                # result["checks"][f"{source_key}_file"] = {
                result["checks"]["file_download"] = {                    
                    "url": None,
                    "success": True,
                    "message": "첨부파일 없음"
                }

        # ==================================================
        # SUCCESS
        # ==================================================
        result["ok"] = True
        result["status"] = "OK"
        
    # ======================================================
    # HealthCheckError 단일 처리
    # ======================================================
    except HealthCheckError as he:
        apply_health_error(result, he)

    except Exception as e:
        print(f"except Exception as e")
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.UNKNOWN,
                str(e)
            )
        )

    return result


# ==================================================
# scheduler call
# ==================================================
def run():
    logger.info("=" * 60)
    logger.info("스크래퍼 시작")
    logger.info("=" * 60)
    
    scraper = FSSGuidelineScraper()
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

if __name__ == "__main__":
    # 커맨드라인 인자 파싱
    parser = argparse.ArgumentParser(
        description='금융감독원 행정지도 및 행정작용 스크래퍼',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python fss_guideline_scraper.py                    # 모든 소스 스크래핑
  python fss_guideline_scraper.py --fss-action      # 금융감독원 행정작용만
  python fss_guideline_scraper.py --fss-guidance    # 금융감독원 행정지도만
  python fss_guideline_scraper.py --fss-action --fss-guidance  # 모든 소스 선택
        """
    )
    
    parser.add_argument(
        '--fss-action',
        action='store_true',
        help='금융감독원 행정작용만 스크래핑'
    )
    parser.add_argument(
        '--fss-guidance',
        action='store_true',
        help='금융감독원 행정지도만 스크래핑'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='요청 간 대기 시간 (초, 기본값: 1.0)'
    )
    
    parser.add_argument(
        '--check',
        action='store_true',
        help='헬스체크 실행 (스크래핑 미실행)'
    )

    args = parser.parse_args()
    
    if args.check:
        health_result = fss_guideline_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 선택된 소스 키 수집
    selected_sources = []
    if args.fss_action:
        selected_sources.append('fss_action')
    if args.fss_guidance:
        selected_sources.append('fss_guidance')
    
    # 아무것도 선택되지 않으면 None (모든 소스 스크래핑)
    source_keys = selected_sources if selected_sources else None
    
    logger.info("=" * 60)
    logger.info("스크래퍼 시작")
    logger.info("=" * 60)
    
    scraper = FSSGuidelineScraper(delay=args.delay)
    results = scraper.scrape_all(source_keys=source_keys)
    scraper.save_results()
    
    logger.info("=" * 60)
    logger.info("스크래핑 완료!")
    logger.info(f"총 {len(results)}개 데이터 수집")
    logger.info("=" * 60)
    
    print("\n" + "=" * 60)
    print("스크래핑 완료!")
    print(f"총 {len(results)}개 데이터 수집")
    print("=" * 60)

