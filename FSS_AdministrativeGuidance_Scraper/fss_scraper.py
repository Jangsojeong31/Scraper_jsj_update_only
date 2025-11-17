import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import sys
import re
import csv
import logging

sys.stdout.reconfigure(encoding='utf-8')

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

class FSSAdministrativeGuidanceScraper:
    def __init__(self):
        self.base_url = "https://www.fss.or.kr"
        self.list_url = "https://www.fss.or.kr/fss/job/admnstgudc/list.do?menuNo=200492&pageIndex={page}&searchRegn=&searchYear=&searchCecYn=T&searchWrd="
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        self.results = []

    def get_page(self, url, retry=3):
        """페이지 가져오기 (재시도 로직 포함)"""
        for i in range(retry):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
                return response
            except Exception as e:
                logger.error(f"페이지 로드 실패 (시도 {i+1}/{retry}): {e}")
                print(f"페이지 로드 실패 (시도 {i+1}/{retry}): {e}")
                if i < retry - 1:
                    time.sleep(2)
                else:
                    raise
        return None

    def scrape_list_page(self, page_index):
        """목록 페이지 스크래핑"""
        url = self.list_url.format(page=page_index)
        
        logger.info(f"페이지 {page_index} 스크래핑 중...")
        print(f"\n페이지 {page_index} 스크래핑 중...")
        response = self.get_page(url)
        soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
        
        table = soup.find('table')
        if not table:
            logger.warning(f"페이지 {page_index}: 테이블을 찾을 수 없습니다")
            print(f"  페이지 {page_index}: 테이블을 찾을 수 없습니다")
            return []
        
        rows = table.find_all('tr')[1:]  # 첫 번째 행은 헤더
        items = []
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 6:  # 관리번호, 제목, 소관부서, 시행일, 시행여부, 첨부
                continue
            
            try:
                # 목록 정보 추출
                관리번호 = cells[0].get_text(strip=True)
                제목_셀 = cells[1]
                제목 = 제목_셀.get_text(strip=True)
                소관부서 = cells[2].get_text(strip=True)
                시행일 = cells[3].get_text(strip=True)
                시행여부 = cells[4].get_text(strip=True)
                첨부 = cells[5].get_text(strip=True) if len(cells) > 5 else ''
                
                # 제목 링크에서 상세 페이지 URL 추출
                link = 제목_셀.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    if href.startswith('./'):
                        detail_url = urljoin(self.base_url, '/fss/job/admnstgudc/' + href[2:])
                    elif href.startswith('/'):
                        detail_url = urljoin(self.base_url, href)
                    elif href.startswith('http'):
                        detail_url = href
                    else:
                        detail_url = urljoin(url, href)
                else:
                    detail_url = None
                
                items.append({
                    '관리번호': 관리번호,
                    '제목': 제목,
                    '소관부서': 소관부서,
                    '시행일': 시행일,
                    '시행여부': 시행여부,
                    '첨부': 첨부,
                    '상세페이지URL': detail_url
                })
                
            except Exception as e:
                logger.error(f"행 처리 중 오류: {e}")
                print(f"  행 처리 중 오류: {e}")
                continue
        
        logger.info(f"페이지 {page_index}: {len(items)}개 항목 발견")
        print(f"  페이지 {page_index}: {len(items)}개 항목 발견")
        return items

    def get_detail_data(self, detail_url):
        """상세 페이지에서 데이터 추출"""
        detail_info = {
            '문서번호': '',
            '유효기간': '',
            '첨부파일이름': '',
            '첨부파일링크': '',
            '담당부서': '',
            '담당팀': '',
            '담당자': '',
            '자료문의': '',
            '상세본문내용': ''
        }
        
        try:
            response = self.get_page(detail_url)
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
            
            # 전체 페이지 텍스트 추출 (본문에서 추출하기 위해)
            # <br> 태그를 줄바꿈으로 변환하여 줄바꿈 유지
            soup_copy = BeautifulSoup(str(soup), 'lxml')
            for br in soup_copy.find_all('br'):
                br.replace_with('\n')
            page_text = soup_copy.get_text(separator='\n', strip=False)  # 줄바꿈 유지
            
            # 방법 1: 테이블에서 정보 추출 (th/td 구조)
            table_selectors = [
                'table.view_table',
                'table.tbl_view',
                'table.table',
                '.view_area table',
                '#contents table',
                'table',
                '.view_info table',
                '.detail_info table'
            ]
            
            info_table = None
            for selector in table_selectors:
                try:
                    tables = soup.select(selector)
                    for table in tables:
                        rows = table.find_all('tr')
                        if rows and len(rows) > 0:
                            info_table = table
                            logger.debug(f"테이블 발견: {selector}")
                            break
                    if info_table:
                        break
                except:
                    continue
            
            if info_table:
                rows = info_table.find_all('tr')
                for row in rows:
                    th_elements = row.find_all('th')
                    td_elements = row.find_all('td')
                    
                    if th_elements and td_elements:
                        key = th_elements[0].get_text(strip=True)
                        value_td = td_elements[0]
                        value = value_td.get_text(strip=True)
                        
                        # 키워드 매칭
                        if ('문서번호' in key or '문서 번호' in key) and not detail_info['문서번호']:
                            detail_info['문서번호'] = value
                        elif ('유효기간' in key or '유효 기간' in key) and not detail_info['유효기간']:
                            detail_info['유효기간'] = value
                        elif '첨부파일' in key or '첨부 파일' in key or '첨부' in key:
                            if not detail_info['첨부파일이름']:
                                # 링크에서 파일명 추출
                                file_links = value_td.find_all('a', href=True)
                                file_names = []
                                file_urls = []
                                for link in file_links:
                                    file_name = link.get_text(strip=True)
                                    file_href = link.get('href', '')
                                    if file_name:
                                        file_names.append(file_name)
                                        # 상대 경로를 절대 경로로 변환
                                        if file_href.startswith('./'):
                                            file_url = urljoin(self.base_url, '/fss/job/admnstgudc/' + file_href[2:])
                                        elif file_href.startswith('/'):
                                            file_url = urljoin(self.base_url, file_href)
                                        elif file_href.startswith('http'):
                                            file_url = file_href
                                        else:
                                            file_url = urljoin(detail_url, file_href)
                                        file_urls.append(file_url)
                                
                                if file_names:
                                    detail_info['첨부파일이름'] = ' | '.join(file_names)
                                    detail_info['첨부파일링크'] = ' | '.join(file_urls)
                                else:
                                    detail_info['첨부파일이름'] = value
                        elif ('담당부서' in key or '소관부서' in key) and not detail_info['담당부서']:
                            detail_info['담당부서'] = value
                        elif '담당팀' in key and not detail_info['담당팀']:
                            detail_info['담당팀'] = value
                        elif '담당자' in key and not detail_info['담당자']:
                            detail_info['담당자'] = value
                        elif ('자료문의' in key or '문의' in key or '연락처' in key) and not detail_info['자료문의']:
                            detail_info['자료문의'] = value
            
            # 방법 2: dl/dt/dd 구조에서 추출
            try:
                dl_elements = soup.find_all('dl')
                for dl in dl_elements:
                    dt_elements = dl.find_all('dt')
                    dd_elements = dl.find_all('dd')
                    
                    for dt, dd in zip(dt_elements, dd_elements):
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        
                        if ('문서번호' in key or '문서 번호' in key) and not detail_info['문서번호']:
                            detail_info['문서번호'] = value
                        elif ('유효기간' in key or '유효 기간' in key) and not detail_info['유효기간']:
                            detail_info['유효기간'] = value
                        elif ('담당부서' in key or '소관부서' in key) and not detail_info['담당부서']:
                            detail_info['담당부서'] = value
                        elif '담당팀' in key and not detail_info['담당팀']:
                            detail_info['담당팀'] = value
                        elif '담당자' in key and not detail_info['담당자']:
                            detail_info['담당자'] = value
                        elif ('자료문의' in key or '문의' in key or '연락처' in key) and not detail_info['자료문의']:
                            detail_info['자료문의'] = value
            except:
                pass
            
            # 방법 3: 첨부파일 링크 직접 찾기
            if not detail_info['첨부파일링크']:
                try:
                    # 다양한 첨부파일 링크 패턴 시도
                    file_link_selectors = [
                        'a[href*="download"]',
                        'a[href*="file"]',
                        'a[href*=".hwp"]',
                        'a[href*=".pdf"]',
                        'a[href*=".doc"]',
                        '.file_list a',
                        '.attach a',
                        '.download a'
                    ]
                    
                    file_names = []
                    file_urls = []
                    
                    for selector in file_link_selectors:
                        try:
                            links = soup.select(selector)
                            for link in links:
                                href = link.get('href', '')
                                text = link.get_text(strip=True)
                                if href and ('.hwp' in href.lower() or '.pdf' in href.lower() or '.doc' in href.lower() or text):
                                    if text:
                                        file_names.append(text)
                                    elif '.hwp' in href.lower() or '.pdf' in href.lower() or '.doc' in href.lower():
                                        # URL에서 파일명 추출
                                        filename = href.split('/')[-1].split('?')[0]
                                        if filename:
                                            file_names.append(unquote(filename))
                                    
                                    # URL 정규화
                                    if href.startswith('./'):
                                        file_url = urljoin(self.base_url, '/fss/job/admnstgudc/' + href[2:])
                                    elif href.startswith('/'):
                                        file_url = urljoin(self.base_url, href)
                                    elif href.startswith('http'):
                                        file_url = href
                                    else:
                                        file_url = urljoin(detail_url, href)
                                    file_urls.append(file_url)
                        except:
                            continue
                    
                    if file_names:
                        detail_info['첨부파일이름'] = ' | '.join(file_names[:5])  # 최대 5개
                        detail_info['첨부파일링크'] = ' | '.join(file_urls[:5])
                except:
                    pass
            
            # 방법 4: 본문 텍스트에서 정규표현식으로 추출
            if page_text:
                # 문서번호 추출 (예: "문서번호지급결제제도팀-259", "문서번호 파생상품시장팀-713")
                if not detail_info['문서번호']:
                    match = re.search(r'문서번호\s*[:：]?\s*([^\s\n]+)', page_text)
                    if match:
                        detail_info['문서번호'] = match.group(1).strip()
                
                # 유효기간 추출 (예: "유효기간'26.12.31.까지", "[유효기간] 2025.9.1.부터 2026.8.31.까지")
                if not detail_info['유효기간']:
                    patterns = [
                        r'유효기간[:\s]*([^\n]+?)(?:시행여부|관련법령|$)',  # 더 포괄적인 패턴
                        r'\[유효기간\]\s*([^\n]+)',
                        r'유효기간[:\s]*\'?(\d{2,4}[.-]\d{1,2}[.-]\d{1,2}[.\s]*부터?[^\n]+)',
                        r'유효기간[:\s]*([^\n]{0,100})'
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, page_text, re.MULTILINE)
                        if match:
                            val = match.group(1).strip()
                            if len(val) < 100:  # 너무 긴 값 제외
                                detail_info['유효기간'] = val
                                break
                
                # 담당팀 추출 (예: "담당팀지급결제제도팀")
                if not detail_info['담당팀']:
                    match = re.search(r'담당팀\s*[:：]?\s*([^\s\n]+)', page_text)
                    if match:
                        detail_info['담당팀'] = match.group(1).strip()
                
                # 담당자 추출 (예: "담당자홍영오 선임조사역")
                if not detail_info['담당자']:
                    match = re.search(r'담당자\s*[:：]?\s*([^\n]{0,50})', page_text)
                    if match:
                        detail_info['담당자'] = match.group(1).strip()
                
                # 자료문의 추출 (예: "자료문의02-3145-8796")
                if not detail_info['자료문의']:
                    patterns = [
                        r'자료문의\s*[:：]?\s*([0-9-()\s]+)',
                        r'문의\s*[:：]?\s*([0-9-()\s]+)',
                        r'연락처\s*[:：]?\s*([0-9-()\s]+)'
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, page_text)
                        if match:
                            detail_info['자료문의'] = match.group(1).strip()
                            break
            
            # 상세 본문 내용 추출: "1. 관련근거" 또는 "- 아 래 -" 패턴으로 시작하는 본문 추출
            # 주의: 본문 추출 시 사용된 패턴과 태그 구조를 기록하여 다른 항목에서도 참고
            # 추출 패턴:
            #   1. "1. 관련근거" 패턴으로 시작 (다양한 형식: "1. 관련근거", "1) 관련근거", "① 관련근거")
            #   2. "- 아 래 -" 패턴으로 시작 (다양한 형식: "- 아 래 -", "- 아 래", "아 래")
            #   3. 담당부서 섹션 전까지 추출
            # 방법 1: 페이지 텍스트에서 시작 패턴 찾기
            if page_text:
                try:
                    # 다양한 시작 패턴 시도 (우선순위 순서)
                    start_patterns = [
                        r'1\.\s*관련근거',  # "1. 관련근거"
                        r'1\)\s*관련근거',  # "1) 관련근거"
                        r'①\s*관련근거',    # "① 관련근거"
                        r'1\.\s*관련\s*근거',  # "1. 관련 근거" (공백 포함)
                        r'1\s*\.\s*관련근거',  # "1 . 관련근거" (공백 포함)
                        r'-\s*아\s*래\s*-',  # "- 아 래 -"
                        r'-\s*아\s*래',  # "- 아 래"
                        r'아\s*래',  # "아 래"
                    ]
                    
                    # 끝 패턴 (담당부서 섹션)
                    end_patterns = [
                        r'\n\s*담당부서',
                        r'\n\s*소관부서',
                        r'\n담당부서',
                        r'\n소관부서',
                    ]
                    
                    content_found = None
                    earliest_start = len(page_text)
                    best_pattern = None
                    
                    # 모든 시작 패턴을 찾아서 가장 앞에 나오는 것을 선택
                    for start_pattern in start_patterns:
                        matches = list(re.finditer(start_pattern, page_text, re.IGNORECASE))
                        for match in matches:
                            if match.start() < earliest_start:
                                earliest_start = match.start()
                                best_pattern = start_pattern
                    
                    # 가장 앞에 나오는 패턴으로 본문 추출
                    if best_pattern:
                        start_match = re.search(best_pattern, page_text, re.IGNORECASE)
                        if start_match:
                            start_pos = start_match.start()
                            
                            # 그 이후부터 담당부서 섹션 전까지 추출
                            remaining_text = page_text[start_pos:]
                            
                            # 담당부서 섹션 찾기
                            end_pos = len(remaining_text)
                            for end_pattern in end_patterns:
                                end_match = re.search(end_pattern, remaining_text, re.IGNORECASE)
                                if end_match:
                                    end_pos = min(end_pos, end_match.start())
                            
                            # 본문 추출 (줄바꿈 유지)
                            content = remaining_text[:end_pos]
                            
                            # 줄바꿈을 유지하면서 불필요한 부분 제거
                            # 연속된 공백과 탭 정리 (단, 줄바꿈은 유지)
                            lines = content.split('\n')
                            filtered_lines = []
                            skip_keywords = [
                                '사이버 홍보관', '관련부속사이트', 'e-금융교육센터',
                                '금융중심지지원센터', '공인회계사시험', '본문검색',
                                '메뉴검색', '검색결과', '금융민원상담', '정보공개청구',
                                '분쟁조정정보', '인허가', '불공정 금융관행', '불법사금융',
                                '보이스피싱', '불법금융신고센터', '옴부즈만', 'Q&A',
                                '고객의 소리', '금융소비자리포터', '국민검사청구제도',
                                '업무자료', '금융감독법규정보', '금융행정지도', '행정지도 내역',
                                '금융거래 시 필요한', '업무처리 절차', '공통업무자료'
                            ]
                            
                            for line in lines:
                                original_line = line
                                line_stripped = line.strip()
                                
                                # 빈 줄은 제거하지 않음 (문단 구분을 위해 일부 유지)
                                if not line_stripped:
                                    # 연속된 빈 줄은 하나로
                                    if filtered_lines and filtered_lines[-1] != '':
                                        filtered_lines.append('')
                                    continue
                                
                                # 유효한 줄만 포함
                                if len(line_stripped) > 3:
                                    # 메뉴나 사이드바 관련 텍스트 제외
                                    if not any(keyword in line_stripped for keyword in skip_keywords):
                                        # 줄 앞뒤 공백은 제거하되 내용은 유지
                                        filtered_lines.append(line_stripped)
                            
                            # 마지막 빈 줄 제거
                            while filtered_lines and filtered_lines[-1] == '':
                                filtered_lines.pop()
                            
                            if filtered_lines:
                                content_found = '\n'.join(filtered_lines)
                    
                    if content_found:
                        detail_info['상세본문내용'] = content_found
                except Exception as e:
                    logger.debug(f"패턴 매칭에서 본문 추출 중 오류: {e}")
            
            # 방법 2: pre/dd 태그에서 시작 패턴 찾기
            if not detail_info['상세본문내용']:
                try:
                    # 모든 pre와 dd 태그 찾기
                    all_elements = soup.find_all(['pre', 'dd', 'div'])
                    
                    for elem in all_elements:
                        # HTML 구조를 유지하면서 줄바꿈 처리
                        # <br> 태그를 줄바꿈으로 변환
                        elem_copy = BeautifulSoup(str(elem), 'lxml')
                        for br in elem_copy.find_all('br'):
                            br.replace_with('\n')
                        text = elem_copy.get_text(separator='\n', strip=False)
                        
                        # 시작 패턴 찾기 ("1. 관련근거" 또는 "- 아 래 -")
                        start_patterns = [
                            r'1\.\s*관련근거',
                            r'1\)\s*관련근거',
                            r'①\s*관련근거',
                            r'-\s*아\s*래\s*-',
                            r'-\s*아\s*래',
                            r'아\s*래',
                        ]
                        
                        earliest_start = len(text)
                        best_match = None
                        
                        # 모든 패턴을 찾아서 가장 앞에 나오는 것을 선택
                        for pattern in start_patterns:
                            match = re.search(pattern, text, re.IGNORECASE)
                            if match and match.start() < earliest_start:
                                earliest_start = match.start()
                                best_match = match
                        
                        if best_match:
                            start_pos = best_match.start()
                            
                            # 담당부서 섹션 전까지 추출
                            remaining = text[start_pos:]
                            end_match = re.search(r'\n\s*담당부서|\n\s*소관부서', remaining, re.IGNORECASE)
                            if end_match:
                                content = remaining[:end_match.start()].strip()
                            else:
                                content = remaining.strip()
                            
                            # 필터링 (줄바꿈 유지)
                            lines = content.split('\n')
                            filtered_lines = []
                            skip_keywords = [
                                '사이버 홍보관', '관련부속사이트', '본문검색', '메뉴검색'
                            ]
                            
                            for line in lines:
                                line_stripped = line.strip()
                                
                                # 빈 줄은 제거하지 않음
                                if not line_stripped:
                                    if filtered_lines and filtered_lines[-1] != '':
                                        filtered_lines.append('')
                                    continue
                                
                                if len(line_stripped) > 3:
                                    if not any(keyword in line_stripped for keyword in skip_keywords):
                                        filtered_lines.append(line_stripped)
                            
                            # 마지막 빈 줄 제거
                            while filtered_lines and filtered_lines[-1] == '':
                                filtered_lines.pop()
                            
                            if filtered_lines:
                                detail_info['상세본문내용'] = '\n'.join(filtered_lines)
                                break
                except Exception as e:
                    logger.debug(f"pre/dd 태그에서 본문 추출 중 오류: {e}")
            
            # 방법 3-1: <!-- 내용 주석 이후 <div bd-view 내 <dl> 태그에서 추출
            if not detail_info['상세본문내용']:
                try:
                    # <!-- 내용 주석 찾기
                    comments = soup.find_all(string=lambda text: isinstance(text, str) and '내용' in text)
                    
                    # HTML을 문자열로 변환하여 주석 찾기
                    html_str = str(soup)
                    content_comment_pattern = r'<!--\s*내용[^-]*-->'
                    comment_match = re.search(content_comment_pattern, html_str, re.IGNORECASE)
                    
                    if comment_match:
                        # 주석 이후의 HTML 추출
                        after_comment = html_str[comment_match.end():]
                        
                        # <div bd-view 찾기 (다양한 형태: <div class="bd-view", <div bd-view 등)
                        div_patterns = [
                            r'<div[^>]*bd-view[^>]*>',
                            r'<div[^>]*class="[^"]*bd-view[^"]*"[^>]*>',
                            r'<div[^>]*class=\'[^\']*bd-view[^\']*\'[^>]*>',
                        ]
                        
                        div_match = None
                        for pattern in div_patterns:
                            div_match = re.search(pattern, after_comment, re.IGNORECASE)
                            if div_match:
                                break
                        
                        if div_match:
                            # div 이후의 HTML에서 dl 태그 찾기
                            after_div = after_comment[div_match.end():]
                            
                            # BeautifulSoup으로 파싱
                            div_soup = BeautifulSoup(after_div[:50000], 'lxml')  # 처음 50000자만
                            
                            # dl 태그 찾기
                            dl_tags = div_soup.find_all('dl')
                            
                            for dl in dl_tags:
                                # dl 태그 내의 텍스트 추출 (줄바꿈 유지)
                                # <br> 태그를 줄바꿈으로 변환
                                dl_copy = BeautifulSoup(str(dl), 'lxml')
                                for br in dl_copy.find_all('br'):
                                    br.replace_with('\n')
                                # <dt>, <dd> 태그 사이에도 줄바꿈 추가
                                for dt in dl_copy.find_all('dt'):
                                    dt.append('\n')
                                for dd in dl_copy.find_all('dd'):
                                    dd.append('\n')
                                dl_text = dl_copy.get_text(separator='\n', strip=False)
                                
                                # 첨부파일과 담당부서 사이의 내용인지 확인
                                if '첨부파일' in dl_text or '담당부서' in dl_text:
                                    # 첨부파일 다음부터 담당부서 전까지 추출
                                    lines = dl_text.split('\n')
                                    
                                    attachment_idx = None
                                    department_idx = None
                                    
                                    for idx, line in enumerate(lines):
                                        line_stripped = line.strip()
                                        if '첨부파일' in line_stripped or '첨부 파일' in line_stripped or ('첨부' in line_stripped and '파일' in line_stripped):
                                            attachment_idx = idx
                                        elif ('담당부서' in line_stripped or '소관부서' in line_stripped) and department_idx is None:
                                            department_idx = idx
                                    
                                    if attachment_idx is not None and department_idx is not None and department_idx > attachment_idx:
                                        # 첨부파일 다음부터 담당부서 전까지 추출
                                        content_lines = lines[attachment_idx + 1:department_idx]
                                        
                                        # 필터링
                                        filtered_lines = []
                                        for line in content_lines:
                                            line_stripped = line.strip()
                                            if line_stripped and len(line_stripped) > 3:
                                                if '담당부서' not in line_stripped and '소관부서' not in line_stripped:
                                                    filtered_lines.append(line_stripped)
                                        
                                        if filtered_lines:
                                            detail_info['상세본문내용'] = '\n'.join(filtered_lines)
                                            logger.debug("<!-- 내용 주석 이후 <div bd-view 내 <dl> 태그에서 본문 추출 성공")
                                            break
                                
                                # 첨부파일/담당부서 패턴이 없지만 내용이 있으면 추출
                                elif dl_text.strip() and len(dl_text.strip()) > 20:
                                    # 줄바꿈 유지하면서 정리
                                    lines = dl_text.split('\n')
                                    filtered_lines = []
                                    for line in lines:
                                        line_stripped = line.strip()
                                        if line_stripped and len(line_stripped) > 3:
                                            if '담당부서' not in line_stripped and '소관부서' not in line_stripped:
                                                filtered_lines.append(line_stripped)
                                    
                                    if filtered_lines:
                                        detail_info['상세본문내용'] = '\n'.join(filtered_lines)
                                        logger.debug("<!-- 내용 주석 이후 <div bd-view 내 <dl> 태그에서 본문 추출 성공 (패턴 없음)")
                                        break
                except Exception as e:
                    logger.debug(f"<!-- 내용 주석 이후 <div bd-view 내 <dl> 태그에서 본문 추출 중 오류: {e}")
            
            # 방법 3-2: 더 간단한 방법 - div[bd-view] 또는 div.bd-view 내 dl 태그 직접 찾기
            if not detail_info['상세본문내용']:
                try:
                    # div.bd-view 또는 div[bd-view] 찾기
                    bd_view_divs = soup.find_all('div', class_=re.compile(r'bd-view', re.I))
                    if not bd_view_divs:
                        bd_view_divs = soup.find_all('div', attrs={'bd-view': True})
                    
                    for div in bd_view_divs:
                        # div 내의 dl 태그 찾기
                        dl_tags = div.find_all('dl')
                        
                        for dl in dl_tags:
                            # 줄바꿈 유지하면서 텍스트 추출
                            # <br> 태그를 줄바꿈으로 변환
                            dl_copy = BeautifulSoup(str(dl), 'lxml')
                            for br in dl_copy.find_all('br'):
                                br.replace_with('\n')
                            # <dt>, <dd> 태그 사이에도 줄바꿈 추가
                            for dt in dl_copy.find_all('dt'):
                                dt.append('\n')
                            for dd in dl_copy.find_all('dd'):
                                dd.append('\n')
                            dl_text = dl_copy.get_text(separator='\n', strip=False)
                            
                            if dl_text.strip() and len(dl_text.strip()) > 20:
                                # 첨부파일과 담당부서 사이 확인
                                if '첨부파일' in dl_text or '담당부서' in dl_text:
                                    lines = dl_text.split('\n')
                                    attachment_idx = None
                                    department_idx = None
                                    
                                    for idx, line in enumerate(lines):
                                        line_stripped = line.strip()
                                        if '첨부파일' in line_stripped or ('첨부' in line_stripped and '파일' in line_stripped):
                                            attachment_idx = idx
                                        elif ('담당부서' in line_stripped or '소관부서' in line_stripped) and department_idx is None:
                                            department_idx = idx
                                    
                                    if attachment_idx is not None and department_idx is not None and department_idx > attachment_idx:
                                        content_lines = lines[attachment_idx + 1:department_idx]
                                        filtered_lines = []
                                        for line in content_lines:
                                            line_stripped = line.strip()
                                            if line_stripped and len(line_stripped) > 3:
                                                if '담당부서' not in line_stripped and '소관부서' not in line_stripped:
                                                    filtered_lines.append(line_stripped)
                                        
                                        if filtered_lines:
                                            detail_info['상세본문내용'] = '\n'.join(filtered_lines)
                                            logger.debug("div.bd-view 내 dl 태그에서 본문 추출 성공")
                                            break
                                else:
                                    # 패턴이 없어도 내용이 충분하면 추출
                                    lines = dl_text.split('\n')
                                    filtered_lines = []
                                    for line in lines:
                                        line_stripped = line.strip()
                                        if line_stripped and len(line_stripped) > 3:
                                            if '담당부서' not in line_stripped and '소관부서' not in line_stripped:
                                                filtered_lines.append(line_stripped)
                                    
                                    if filtered_lines and len('\n'.join(filtered_lines)) > 30:
                                        detail_info['상세본문내용'] = '\n'.join(filtered_lines)
                                        logger.debug("div.bd-view 내 dl 태그에서 본문 추출 성공 (패턴 없음)")
                                        break
                        
                        if detail_info['상세본문내용']:
                            break
                except Exception as e:
                    logger.debug(f"div.bd-view 내 dl 태그에서 본문 추출 중 오류: {e}")
            
            # 방법 4: 테이블 구조에서 추출 (첨부파일 아래, 담당부서 위)
            if not detail_info['상세본문내용'] and info_table:
                try:
                    attachment_row = None
                    department_row = None
                    
                    rows = info_table.find_all('tr')
                    for idx, row in enumerate(rows):
                        th_elements = row.find_all('th')
                        if th_elements:
                            key = th_elements[0].get_text(strip=True)
                            if '첨부파일' in key or '첨부 파일' in key or '첨부' in key:
                                attachment_row = idx
                            elif '담당부서' in key or '소관부서' in key:
                                department_row = idx
                    
                    # 첨부파일 행과 담당부서 행 사이의 내용 추출
                    if attachment_row is not None and department_row is not None and department_row > attachment_row:
                        content_parts = []
                        for idx in range(attachment_row + 1, department_row):
                            if idx < len(rows):
                                row = rows[idx]
                                tds = row.find_all('td')
                                ths = row.find_all('th')
                                if tds and not ths:
                                    # 줄바꿈 유지하면서 텍스트 추출
                                    td_copy = BeautifulSoup(str(tds[0]), 'lxml')
                                    for br in td_copy.find_all('br'):
                                        br.replace_with('\n')
                                    text = td_copy.get_text(separator='\n', strip=False).strip()
                                    if text and len(text) > 10:
                                        # 시작 패턴이 있는지 확인 ("1. 관련근거" 또는 "- 아 래 -")
                                        if re.search(r'1\.\s*관련근거|1\)\s*관련근거|-\s*아\s*래', text, re.IGNORECASE):
                                            content_parts.append(text)
                                        elif not content_parts:  # 아직 시작 패턴을 못 찾았으면 추가
                                            content_parts.append(text)
                                elif ths and tds:
                                    th_text = ths[0].get_text(strip=True)
                                    # 줄바꿈 유지하면서 텍스트 추출
                                    td_copy = BeautifulSoup(str(tds[0]), 'lxml')
                                    for br in td_copy.find_all('br'):
                                        br.replace_with('\n')
                                    td_text = td_copy.get_text(separator='\n', strip=False).strip()
                                    if td_text and len(td_text) > 50 and '담당' not in th_text and '첨부' not in th_text:
                                        if re.search(r'1\.\s*관련근거|1\)\s*관련근거|-\s*아\s*래', td_text, re.IGNORECASE):
                                            content_parts.append(td_text)
                                        elif not content_parts:
                                            content_parts.append(td_text)
                        
                        if content_parts:
                            combined = '\n'.join(content_parts).strip()
                            # 시작 패턴으로 시작하도록 정리 ("1. 관련근거" 또는 "- 아 래 -")
                            patterns = [
                                r'1\.\s*관련근거',
                                r'1\)\s*관련근거',
                                r'-\s*아\s*래\s*-',
                                r'-\s*아\s*래',
                                r'아\s*래',
                            ]
                            
                            earliest_match = None
                            earliest_pos = len(combined)
                            
                            for pattern in patterns:
                                match = re.search(pattern, combined, re.IGNORECASE)
                                if match and match.start() < earliest_pos:
                                    earliest_pos = match.start()
                                    earliest_match = match
                            
                            if earliest_match:
                                detail_info['상세본문내용'] = combined[earliest_match.start():].strip()
                            else:
                                detail_info['상세본문내용'] = combined
                except Exception as e:
                    logger.debug(f"테이블에서 본문 추출 중 오류: {e}")
            
        except Exception as e:
            logger.error(f"상세 페이지 처리 중 오류: {e}")
            print(f"  상세 페이지 처리 중 오류: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            traceback.print_exc()
        
        return detail_info

    def get_total_pages(self):
        """총 페이지 수 확인"""
        try:
            # 첫 페이지에서 페이지네이션 정보 확인
            url = self.list_url.format(page=1)
            response = self.get_page(url)
            soup = BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
            
            max_page = 1
            
            # 방법 1: 총 건수로 계산 (예: "총 554건", "전체 554건")
            page_text = soup.get_text()
            total_count = None
            
            # 다양한 패턴 시도
            patterns = [
                r'총\s*(\d+)\s*건',
                r'전체\s*(\d+)\s*건',
                r'(\d+)\s*건\s*전체',
                r'총\s*(\d+)\s*개',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    try:
                        total_count = int(match.group(1))
                        logger.info(f"총 건수 발견: {total_count}건 (패턴: {pattern})")
                        break
                    except:
                        continue
            
            if total_count:
                items_per_page = 10  # 페이지당 10개
                calculated_pages = (total_count + items_per_page - 1) // items_per_page
                max_page = calculated_pages
                logger.info(f"총 건수 {total_count}건으로 계산된 페이지 수: {calculated_pages}페이지")
            else:
                # 방법 2: 페이지네이션 링크 찾기
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
                    
                    # 링크 텍스트에서도 확인
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        try:
                            page_num = int(text)
                            max_page = max(max_page, page_num)
                        except:
                            pass
                
                # 방법 3: "끝" 또는 마지막 페이지 링크 찾기
                last_links = soup.find_all('a', string=re.compile(r'끝|마지막|Last', re.I))
                for link in last_links:
                    href = link.get('href', '')
                    match = re.search(r'pageIndex=(\d+)', href)
                    if match:
                        try:
                            page_num = int(match.group(1))
                            max_page = max(max_page, page_num)
                        except:
                            pass
            
            # 최소값 확인 (554건이면 최소 56페이지)
            if max_page < 55:
                logger.warning(f"감지된 페이지 수({max_page})가 적습니다. 554건을 모두 수집하기 위해 60페이지로 설정합니다.")
                max_page = 60  # 554건 / 10 = 약 56페이지, 여유있게 60
            
            logger.info(f"감지된 최대 페이지 수: {max_page}페이지")
            return max_page
        except Exception as e:
            logger.warning(f"총 페이지 수 확인 실패: {e}, 기본값 60페이지로 진행")
            return 60  # 기본값 (554건 / 10 = 약 56페이지, 여유있게 60)
    
    def scrape_all(self):
        """전체 스크래핑 실행"""
        logger.info("=" * 60)
        logger.info("금융감독원 행정지도 내역 스크래핑 시작")
        logger.info("=" * 60)
        print("=" * 60)
        print("금융감독원 행정지도 내역 스크래핑 시작")
        print("=" * 60)
        
        # 총 페이지 수 확인
        logger.info("총 페이지 수 확인 중...")
        print("총 페이지 수 확인 중...")
        total_pages = self.get_total_pages()
        logger.info(f"총 {total_pages}페이지를 스크랩핑합니다.")
        print(f"총 {total_pages}페이지를 스크랩핑합니다.")
        
        all_items = []
        seen_numbers = set()
        page = 1
        empty_pages = 0
        max_empty_pages = 3  # 연속 3페이지에서 항목이 없으면 종료
        consecutive_empty = 0  # 연속 빈 페이지 카운터
        
        logger.info(f"554건을 모두 수집하기 위해 최대 {total_pages}페이지까지 순회합니다.")
        print(f"554건을 모두 수집하기 위해 최대 {total_pages}페이지까지 순회합니다.")
        
        while page <= total_pages:
            items = self.scrape_list_page(page)
            
            if not items:
                consecutive_empty += 1
                if consecutive_empty >= max_empty_pages:
                    logger.info(f"페이지 {page}에서 연속 {consecutive_empty}페이지에서 항목이 없어 수집을 종료합니다.")
                    print(f"\n페이지 {page}에서 연속 {consecutive_empty}페이지에서 항목이 없어 수집을 종료합니다.")
                    break
                logger.info(f"페이지 {page}: 항목 없음 (연속 빈 페이지: {consecutive_empty}/{max_empty_pages})")
                page += 1
                time.sleep(1)
                continue
            
            consecutive_empty = 0  # 항목이 있으면 카운터 리셋
            
            # 중복 제거
            new_items = []
            for item in items:
                관리번호 = item.get('관리번호')
                if 관리번호:
                    if 관리번호 not in seen_numbers:
                        seen_numbers.add(관리번호)
                        new_items.append(item)
                    else:
                        logger.debug(f"중복 항목 스킵: {관리번호}")
                else:
                    # 관리번호가 없는 경우도 추가
                    new_items.append(item)
            
            all_items.extend(new_items)
            logger.info(f"페이지 {page}/{total_pages}: {len(items)}개 항목 발견, {len(new_items)}개 신규 항목, 누적 수집: {len(all_items)}건")
            print(f"  페이지 {page}/{total_pages}: {len(items)}개 항목 발견, {len(new_items)}개 신규 항목, 누적 수집: {len(all_items)}건")
            
            # 목표 건수에 도달했는지 확인 (554건)
            if len(all_items) >= 554:
                logger.info(f"목표 건수(554건)에 도달했습니다. 수집을 종료합니다.")
                print(f"\n목표 건수(554건)에 도달했습니다. 수집을 종료합니다.")
                break
            
            time.sleep(1)  # 서버 부하 방지
            page += 1
        
        logger.info(f"총 {len(all_items)}개 항목 수집 완료")
        print(f"\n총 {len(all_items)}개 항목 수집 완료")
        
        # 상세 정보 추출
        logger.info("상세 정보 추출 시작...")
        print("\n상세 정보 추출 시작...")
        
        # 기존 결과 로드하여 빈 항목 확인
        existing_results = {}
        if os.path.exists('fss_results.json'):
            try:
                with open('fss_results.json', 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    for item in existing_data:
                        관리번호 = item.get('관리번호')
                        if 관리번호:
                            existing_results[관리번호] = item
                logger.info(f"기존 결과 {len(existing_results)}건 로드 완료")
            except:
                pass
        
        for idx, item in enumerate(all_items, 1):
            title_preview = item.get('제목', '')[:50]
            관리번호 = item.get('관리번호', '')
            
            # 기존 결과가 있고 상세본문내용이 있으면 재사용
            if 관리번호 and 관리번호 in existing_results:
                existing_item = existing_results[관리번호]
                existing_content = existing_item.get('상세본문내용', '')
                
                # 상세본문내용이 있고 충분히 긴 경우 재사용
                if existing_content and len(existing_content) > 50:
                    logger.info(f"[{idx}/{len(all_items)}] {title_preview} - 기존 결과 재사용 (내용 길이: {len(existing_content)})")
                    item.update(existing_item)
                    self.results.append(item)
                    continue
            
            logger.info(f"[{idx}/{len(all_items)}] {title_preview} 처리 중...")
            print(f"\n[{idx}/{len(all_items)}] {title_preview} 처리 중...")
            
            if item.get('상세페이지URL'):
                detail_info = self.get_detail_data(item['상세페이지URL'])
                item.update(detail_info)
                
                # 상세본문내용이 없거나 너무 짧으면 경고
                if not detail_info.get('상세본문내용') or len(detail_info.get('상세본문내용', '')) < 10:
                    logger.warning(f"  상세본문내용이 없거나 짧습니다. (길이: {len(detail_info.get('상세본문내용', ''))})")
            else:
                logger.warning("상세 페이지 URL이 없습니다.")
                print("  상세 페이지 URL이 없습니다.")
            
            self.results.append(item)
            time.sleep(0.5)  # 서버 부하 방지
        
        return self.results

    def save_results(self, filename='fss_results.json'):
        """결과를 JSON과 CSV 파일로 저장"""
        # JSON 저장
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        logger.info(f"결과가 {filename}에 저장되었습니다. (총 {len(self.results)}개)")
        print(f"\n결과가 {filename}에 저장되었습니다. (총 {len(self.results)}개)")
        
        # CSV 저장
        try:
            csv_filename = filename.replace('.json', '.csv')
            if self.results:
                # 모든 필드명 수집
                fieldnames = [
                    '관리번호', '제목', '소관부서', '시행일', '시행여부', '첨부',
                    '문서번호', '유효기간', '첨부파일이름', '첨부파일링크',
                    '담당부서', '담당팀', '담당자', '자료문의', '상세본문내용', '상세페이지URL'
                ]
                
                with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
                    # CSV writer 설정: quoting=csv.QUOTE_ALL로 모든 필드를 큰따옴표로 감싸줌
                    writer = csv.DictWriter(
                        f, 
                        fieldnames=fieldnames, 
                        extrasaction='ignore',
                        quoting=csv.QUOTE_ALL,
                        escapechar=None
                    )
                    writer.writeheader()
                    
                    for item in self.results:
                        row = {}
                        for field in fieldnames:
                            value = item.get(field, '')
                            if value is None:
                                value = ''
                            # 문자열로 변환하되, 줄바꿈은 유지
                            # 줄바꿈이 여러 개 연속된 경우 정리 (최대 2개까지만)
                            str_value = str(value)
                            # 연속된 줄바꿈을 2개로 제한 (가독성을 위해)
                            str_value = re.sub(r'\n{3,}', '\n\n', str_value)
                            row[field] = str_value
                        writer.writerow(row)
                
                logger.info(f"CSV 파일도 {csv_filename}에 저장되었습니다.")
                print(f"CSV 파일도 {csv_filename}에 저장되었습니다.")
        except Exception as e:
            logger.error(f"CSV 저장 중 오류 (무시): {e}")
            print(f"CSV 저장 중 오류 (무시): {e}")
            import traceback
            logger.debug(traceback.format_exc())
            traceback.print_exc()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("스크래퍼 시작")
    logger.info("=" * 60)
    
    scraper = FSSAdministrativeGuidanceScraper()
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

