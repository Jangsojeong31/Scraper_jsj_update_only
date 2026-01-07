"""
은행연합회 스크래퍼
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


class KfbScraper(BaseScraper):
    """은행연합회 스크래퍼"""
    
    SOURCE_CODE = "KFB"  # 출처 코드
    BASE_URL = "https://www.kfb.or.kr"
    
    def __init__(self, delay: float = 1.0):
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
        
        # API 클라이언트 초기화 (환경변수에서)
        try:
            from common.regulation_api_client import RegulationAPIClient
            self.api_client = RegulationAPIClient()
            print(f"✓ API 클라이언트 초기화 완료")
        except (ValueError, Exception) as e:
            print(f"⚠ API 클라이언트 초기화 실패 (CSV 사용): {e}")
            self.api_client = None
        
        # 목록 로드 (API 우선, 실패 시 빈 리스트 반환 - 전체 목록 사용)
        self.target_laws = self._load_target_laws()
    
    def _load_target_laws(self) -> List[Dict]:
        """API에서 스크래핑 대상 규정명을 로드한다.
        API 우선 시도, 실패 시 빈 리스트 반환 (전체 목록 사용)
        """
        # API 사용 가능하면 API에서 가져오기
        if self.api_client:
            try:
                print(f"✓ API에서 법규 목록 가져오는 중... (출처: {self.SOURCE_CODE})")
                regulations = self.api_client.get_regulations(srce_cd=self.SOURCE_CODE)
                
                # 기존 형식으로 변환
                targets = []
                for reg in regulations:
                    regu_nm = reg.get('reguNm', '').strip()
                    dvcd = reg.get('dvcd', '').strip()
                    outs_regu_pk = reg.get('outsReguPk', '')
                    
                    if not regu_nm:
                        continue
                    
                    targets.append({
                        'law_name': regu_nm,
                        'category': dvcd,
                        'outsReguPk': outs_regu_pk  # API 업데이트용 ID
                    })
                
                print(f"✓ API에서 {len(targets)}개의 법규를 가져왔습니다.")
                return targets
                
            except Exception as e:
                print(f"⚠ API 로드 실패, 전체 목록 사용: {e}")
                # 폴백: 빈 리스트 반환 (전체 목록 사용)
        
        # API가 없거나 실패한 경우 빈 리스트 반환 (전체 목록 사용)
        print(f"✓ 전체 목록을 대상으로 진행합니다.")
        return []
    
    # 파일 처리 메서드들은 common.file_extractor.FileExtractor로 이동됨
    # 아래 메서드들은 하위 호환성을 위해 FileExtractor로 위임
    def download_file(self, url: str, filename: str, use_selenium: bool = False, driver=None) -> tuple[Optional[str], Optional[str]]:
        """파일 다운로드 (FileExtractor로 위임)"""
        return self.file_extractor.download_file(
            url, filename, use_selenium=use_selenium, driver=driver,
            referer='https://www.kfb.or.kr/publicdata/reform_info.php'
        )
    
    def extract_files_from_zip(self, zip_path: str) -> Optional[str]:
        """ZIP 파일에서 파일 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_files_from_zip(zip_path)
    
    def extract_hwp_from_zip(self, zip_path: str) -> Optional[str]:
        """ZIP 파일에서 HWP 추출 (하위 호환성, FileExtractor로 위임)"""
        return self.file_extractor.extract_files_from_zip(zip_path)
    
    def extract_pdf_content(self, filepath: str) -> str:
        """PDF 내용 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_pdf_content(filepath)
    
    def extract_hwp_content(self, filepath: str) -> str:
        """HWP 내용 추출 (FileExtractor로 위임)"""
        return self.file_extractor.extract_hwp_content(filepath)
    
    def _extract_hwp_content_internal(self, filepath: str) -> str:
        """HWP 내부 추출 (FileExtractor로 위임)"""
        return self.file_extractor._extract_hwp_content_internal(filepath)
    
    def extract_law_info_from_content(self, content: str, title: str = "") -> Dict:
        """
        HWP 파일 내용에서 법규 정보 추출 (규정명, 기관명, 본문, 제정일, 최근 개정일)
        
        Args:
            content: HWP 파일에서 추출한 텍스트 내용
            title: 제목 (기본값으로 사용)
            
        Returns:
            추출된 정보 딕셔너리
        """
        import re
        
        info = {
            'regulation_name': title,  # 규정명 (기본값: 제목)
            'organization': '은행연합회',  # 기관명 (항상 은행연합회)
            'content': content,  # 본문
            'enactment_date': '',  # 제정일
            'revision_date': ''  # 최근 개정일
        }
        
        if not content:
            return info
        
        # 제정일 추출 (제정 2025.1.15. 또는 제정 2003. 12. 19. 같은 패턴)
        enactment_patterns = [
            r'제\s*정\s+(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)',  # 제정 2003. 12. 19. 또는 제정 2025.1.15.
            r'제\s*정\s+(\d{4}\.\d{1,2}\.\d{1,2}\.?)',  # 제정 2025.1.15. (공백 없는 형식)
            r'제\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'제\s*정\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)\s*제\s*정',  # 2003. 12. 19. 제정
            r'(\d{4}\.\d{1,2}\.\d{1,2}\.?)\s*제\s*정',  # 2025.1.15. 제정
            r'(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)\s*제\s*정',
        ]
        
        for pattern in enactment_patterns:
            match = re.search(pattern, content[:2000], re.IGNORECASE)
            if match:
                date_str = match.group(1) if match.groups() else match.group(0)
                # 날짜 정리
                date_str = re.sub(r'[년월일]', '', date_str).strip()
                date_str = date_str.replace(' ', '').replace('-', '.')
                # 마지막 점이 없으면 추가
                if date_str and not date_str.endswith('.'):
                    # YYYY.M.D 형식인지 확인
                    if re.match(r'\d{4}\.\d{1,2}\.\d{1,2}$', date_str):
                        date_str += '.'
                info['enactment_date'] = date_str
                break
        
        # 최근 개정일 추출 (개정일 패턴)
        revision_patterns = [
            r'개\s*정\s+(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)',  # 개정 2003. 12. 19. 또는 개정 2025. 11. 28.
            r'개\s*정\s+(\d{4}\.\d{1,2}\.\d{1,2}\.?)',  # 개정 2025.1.15. (공백 없는 형식)
            r'개\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'최\s*근\s*개\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'최종\s*개\s*정\s*일\s*[:：]\s*(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)',
            r'(\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)\s*개\s*정',  # 2003. 12. 19. 개정
            r'(\d{4}\.\d{1,2}\.\d{1,2}\.?)\s*개\s*정',  # 2025.1.15. 개정
            r'(\d{4}[\.\-년]\s*\d{1,2}[\.\-월]\s*\d{1,2}[일]?)\s*개\s*정',
        ]
        
        # 여러 개정일이 있을 수 있으므로 모두 찾아서 가장 최근 것 사용
        revision_dates_raw = []
        for pattern in revision_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1) if match.groups() else match.group(0)
                # 날짜 정리
                date_str = re.sub(r'[년월일]', '', date_str).strip()
                date_str = date_str.replace(' ', '').replace('-', '.')
                # 마지막 점 제거 (나중에 다시 추가)
                date_str = date_str.rstrip('.')
                if date_str:
                    revision_dates_raw.append(date_str)
        
        # 날짜를 파싱해서 가장 최근 날짜 선택
        if revision_dates_raw:
            # 중복 제거 및 날짜 파싱
            parsed_dates = []
            seen = set()
            for date_str in revision_dates_raw:
                # YYYY.M.D 형식 파싱
                parts = date_str.split('.')
                if len(parts) >= 3:
                    try:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        # 중복 체크용 키
                        date_key = (year, month, day)
                        if date_key not in seen:
                            seen.add(date_key)
                            parsed_dates.append((year, month, day, date_str))
                    except ValueError:
                        continue
            
            if parsed_dates:
                # 날짜를 비교해서 가장 최근 날짜 선택
                latest = max(parsed_dates, key=lambda x: (x[0], x[1], x[2]))
                # 정규화된 형식으로 변환 (YYYY.MM.DD.)
                latest_date_str = f"{latest[3]}"
                # 마지막 점이 없으면 추가
                if not latest_date_str.endswith('.'):
                    latest_date_str += '.'
                info['revision_date'] = latest_date_str
        
        # 규정명 추출 (제목이 없거나 개선이 필요한 경우)
        if not info['regulation_name'] or info['regulation_name'] == title:
            # HWP 내용 앞부분에서 규정명 패턴 찾기
            regulation_patterns = [
                r'규\s*정\s*명\s*[:：]\s*(.+?)(?:\n|$)',
                r'제\s*목\s*[:：]\s*(.+?)(?:\n|$)',
            ]
            
            for pattern in regulation_patterns:
                match = re.search(pattern, content[:500], re.IGNORECASE)
                if match:
                    reg_name = match.group(1).strip()
                    if reg_name and len(reg_name) < 200:  # 너무 길면 제외
                        info['regulation_name'] = reg_name
                        break
        
        return info
    
    def extract_table_data(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """
        테이블에서 데이터 추출 (CSS Selector 사용)
        
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL
            
        Returns:
            추출된 데이터 리스트
        """
        results = []
        
        if soup is None:
            return results
        
        # CSS Selector로 테이블 찾기 (여러 가능한 선택자 시도)
        table_selectors = [
            'table',
            '#Content table',
            '.contentArea table',
            'div.contentArea table',
            'table tbody',
        ]
        
        table = None
        for selector in table_selectors:
            try:
                table = soup.select_one(selector)
                if table:
                    break
            except:
                continue
        
        if not table:
            return results
        
        # CSS Selector로 테이블 행 추출 (tbody가 있으면 tbody 내부, 없으면 직접)
        rows = table.select('tbody > tr') or table.select('tr')
        if not rows:
            return results
        
        # 헤더 행 확인 (CSS Selector로 첫 번째 행 확인)
        if rows:
            first_row = rows[0]
            first_row_text = first_row.get_text(strip=True).lower()
            if '번호' in first_row_text or 'no' in first_row_text or '제목' in first_row_text:
                rows = rows[1:]
        
        for row in rows:
            # CSS Selector로 셀 추출
            cells = row.select('td, th')
            if len(cells) < 2:
                continue
            
            item = {}
            
            # 번호 (첫 번째 셀) - CSS Selector로 직접 접근
            no_cell = row.select_one('td:first-child, th:first-child')
            if no_cell:
                no_text = no_cell.get_text(strip=True)
                if not no_text or no_text.lower() in ['번호', 'no', '']:
                    continue
                item['no'] = no_text
            else:
                continue
            
            # 제목 (두 번째 셀) - CSS Selector로 직접 접근
            title_cell = row.select_one('td:nth-child(2), th:nth-child(2)')
            if title_cell:
                title_link = title_cell.select_one('a')
            if title_link:
                item['title'] = title_link.get_text(strip=True)
                href = title_link.get('href', '')
                if href:
                        if href.startswith('javascript:') or href.startswith('Javascript:'):
                            item['detail_link'] = href
                        elif href.startswith('http'):
                            item['detail_link'] = href
                        else:
                            item['detail_link'] = urljoin(base_url, href)
            else:
                item['title'] = title_cell.get_text(strip=True)
            
            # 다운로드 링크 (세 번째 셀) - CSS Selector로 직접 접근
            download_cell = row.select_one('td:nth-child(3), th:nth-child(3)')
            if download_cell:
                download_link = download_cell.select_one('a')
                if download_link:
                    href = download_link.get('href', '')
                    if href:
                        item['download_link'] = href if href.startswith('http') else urljoin(base_url, href)
            
            # 제목이 있고 번호가 숫자인 경우만 추가
            if item.get('title') and item.get('no') and item['no'].isdigit():
                results.append(item)
        
        return results
    
    def extract_detail_page_info(self, soup: BeautifulSoup) -> Dict:
        """
        상세 페이지에서 본문 내용과 소관부서 추출
        
        Args:
            soup: BeautifulSoup 객체 (상세 페이지)
            
        Returns:
            추출된 정보 딕셔너리 (content, department)
        """
        info = {
            'content': '',  # 본문 내용
            'department': '',  # 소관부서
            'file_name': ''  # 파일명
        }
        
        if soup is None:
            return info
        
        # 본문 내용 추출 (리스트/CSS 구조 우선 확인)
        primary_content_selectors = [
            '#Content > div > div.contentArea > div.conInfoArea > div.panViewArea.mt30 > ul.viewInfo > li.txt',
            '#Content ul.viewInfo li.txt',
            '.conInfoArea ul.viewInfo li.txt',
            'ul.viewInfo li.txt',
        ]
        for css_selector in primary_content_selectors:
            try:
                elem = soup.select_one(css_selector)
                if elem:
                    content_text = elem.get_text(strip=True)
                    if content_text and len(content_text) > 5 and '홈 >' not in content_text[:50]:
                        info['content'] = content_text
                        print(f"  CSS 선택자로 본문 발견 ({css_selector}): {content_text[:100]}...")
                        break
            except Exception as e:
                continue
        
        if not info['content']:
            # ul.viewInfo > li.txt 구조 확인 (추가 보조) - CSS Selector 사용
            view_info_ul = soup.select_one('ul.viewInfo')
            if view_info_ul:
                txt_li = view_info_ul.select_one('li.txt')
                if txt_li:
                    content_text = txt_li.get_text(strip=True)
                    if content_text and len(content_text) > 5 and '홈 >' not in content_text[:50]:
                        info['content'] = content_text
                        print(f"  리스트 구조에서 본문 발견: {content_text[:100]}...")
        
        # 본문 내용 추출 (CSS Selector만 사용)
        if not info['content']:
            # CSS Selector로 본문 영역 찾기
            css_selectors = [
                'div#content',
                'div#viewContent',
                'div#detailContent',
                'div#conts',
                'div#view',
                'div#detail',
                'div#mainContent',
                'div#articleContent',
                'div.content',
                'div.viewContent',
                'div.detailContent',
                'div.conts',
                'div.view',
                'div.detail',
                'div.mainContent',
                'div.articleContent',
                'div[id*="content"]',
                'div[class*="content"]',
                'div[id*="view"]',
                'div[class*="view"]',
                'div[id*="detail"]',
                'div[class*="detail"]',
            ]
            
            content_div = None
            for css_selector in css_selectors:
                try:
                    content_div = soup.select_one(css_selector)
                    if content_div:
                        # 내용이 있는지 확인 (너무 짧으면 건너뛰기)
                        text = content_div.get_text(strip=True)
                        # 네비게이션 경로가 아닌지 확인
                        if text and len(text) > 10 and '홈 >' not in text[:100]:
                            break
                        else:
                            content_div = None
                except:
                    continue
        
            # 본문 내용 추출
            if content_div:
                # 스크립트, 스타일, 주석 태그 제거 - CSS Selector 사용
                for script in content_div.select('script, style, noscript'):
                    script.decompose()
                # 주석 제거 (Comment는 특수 타입이므로 find_all 유지)
                from bs4 import Comment
                comments = content_div.find_all(string=lambda text: isinstance(text, Comment))
                for comment in comments:
                    comment.extract()
                
                # 텍스트 추출
                info['content'] = content_div.get_text(separator='\n', strip=True)
        else:
            # 본문 영역을 찾지 못한 경우 더 넓은 범위에서 추출 시도 - CSS Selector 사용
            # main, article 태그 시도
            main_content = soup.select_one('main') or soup.select_one('article')
            if main_content:
                for script in main_content.select('script, style, noscript'):
                    script.decompose()
                info['content'] = main_content.get_text(separator='\n', strip=True)
            else:
                # body에서 본문 같은 부분 찾기 (테이블, 헤더, 푸터 제외) - CSS Selector 사용
                body = soup.select_one('body')
                if body:
                    # 헤더, 푸터, 네비게이션 제거
                    for tag in body.select('header, footer, nav, script, style'):
                        tag.decompose()
                    
                    # 테이블에서 본문 찾기 (테이블의 특정 셀에 본문이 있을 수 있음) - CSS Selector 사용
                    tables = body.select('table')
                    for table in tables:
                        rows = table.select('tr')
                        for row in rows:
                            cells = row.select('td, th')
                            # 테이블 행에서 라벨과 값 찾기
                            if len(cells) >= 2:
                                label = cells[0].get_text(strip=True)
                                value = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                                
                                # "본문" 또는 "내용" 라벨이 있는 경우
                                if '본문' in label or '내용' in label:
                                    if value and len(value) > 10:
                                        # 네비게이션 경로가 아닌지 확인
                                        if '홈 >' not in value and '공시' not in value[:20]:
                                            info['content'] = value
                                            break
                                
                                # "ㅇ"으로 시작하는 본문 내용 찾기 (우선순위 높음)
                                if value.startswith('ㅇ') or value.startswith('○') or value.startswith('●'):
                                    # 본문 관련 키워드가 있으면 우선 선택
                                    keywords = ['규정', '대상', '종류', '정의', '수수료', '정보제공', '내부통제', '부과', 'PF']
                                    if any(keyword in value for keyword in keywords):
                                        # 네비게이션 경로가 아닌지 확인
                                        if '홈 >' not in value and '공시' not in value[:20]:
                                            if not info['content'] or len(value) > len(info['content']):
                                                info['content'] = value
                            
                            # 셀 단위로도 검색 (2개 이상의 셀이 있는 경우)
                            if len(cells) >= 2:
                                for cell_idx, cell in enumerate(cells):
                                    cell_text = cell.get_text(strip=True)
                                    # "ㅇ"으로 시작하는 본문 내용 찾기
                                    if cell_text.startswith('ㅇ') or cell_text.startswith('○') or cell_text.startswith('●'):
                                        if len(cell_text) > 20:
                                            keywords = ['규정', '대상', '종류', '정의', '수수료', '정보제공', '내부통제', '부과', 'PF']
                                            if any(keyword in cell_text for keyword in keywords):
                                                # 네비게이션 경로가 아닌지 확인
                                                if '홈 >' not in cell_text and '공시' not in cell_text[:20]:
                                                    if not info['content'] or len(cell_text) > len(info['content']):
                                                        info['content'] = cell_text
                        
                        if info['content']:
                            break
                    
                    # 테이블에서 찾지 못한 경우 body 전체 텍스트 사용
                    if not info['content']:
                        text = body.get_text(separator='\n', strip=True)
                        # 줄바꿈 정리
                        import re
                        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
                        # 너무 짧거나 너무 길면 건너뛰기
                        if 20 < len(text) < 50000:  # 20자 이상 50000자 미만
                            info['content'] = text
        
        # 담당부서 추출 (CSV에는 소관부서 컬럼으로 저장됨) - CSS Selector 사용
        # 리스트 구조에서 담당부서 찾기 (CSS Selector 사용)
        department_selectors = [
            'ul.viewInfo li.item span.type01:contains("담당부서") + span.type02',
            'ul.viewInfo li.item span:contains("담당부서") + span.type02',
            'ul.viewInfo li.item span.type02',
        ]
        
        # CSS Selector로 ul.viewInfo 찾기
        view_info_ul = soup.select_one('ul.viewInfo')
        if view_info_ul:
            item_li = view_info_ul.select_one('li.item')
            if item_li:
                # CSS Selector로 span들 찾기
                spans = item_li.select('span')
                for i, span in enumerate(spans):
                    span_text = span.get_text(strip=True)
                    if '담당부서' in span_text:
                        # 다음 span이 값 (CSS Selector로 다음 형제 찾기)
                        if i + 1 < len(spans):
                            next_span = spans[i + 1]
                            if 'type02' in next_span.get('class', []):
                                info['department'] = next_span.get_text(strip=True)
                                print(f"  리스트 구조에서 담당부서 발견: {info['department']}")
                                break
        
        # 테이블에서 담당부서 찾기 (CSS Selector 사용)
        if not info['department']:
            tables = soup.select('table')
            for table in tables:
                rows = table.select('tr')
                for row in rows:
                    # CSS Selector로 셀 추출
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        # 첫 번째 셀(라벨)과 두 번째 셀(값) 추출
                        label_cell = row.select_one('td:first-child, th:first-child')
                        value_cell = row.select_one('td:nth-child(2), th:nth-child(2)')
                        
                        if label_cell and value_cell:
                            label = label_cell.get_text(strip=True)
                            value = value_cell.get_text(strip=True)
                            
                            # "담당부서" 검색 (정확히 일치하거나 포함)
                            if '담당부서' in label:
                                info['department'] = value.strip()
                                # 빈 값이 아니고 너무 길지 않은지 확인
                                if info['department'] and len(info['department']) < 200:
                                    break
                                else:
                                    info['department'] = ''
                    
                    # 3개 이상의 셀이 있는 경우도 확인 (CSS Selector로 각 셀 확인)
                    if len(cells) >= 3:
                        for i in range(len(cells) - 1):
                            label_cell = row.select_one(f'td:nth-child({i+1}), th:nth-child({i+1})')
                            value_cell = row.select_one(f'td:nth-child({i+2}), th:nth-child({i+2})')
                            if label_cell and value_cell:
                                label = label_cell.get_text(strip=True)
                                value = value_cell.get_text(strip=True)
                                if '담당부서' in label:
                                    info['department'] = value.strip()
                                    if info['department'] and len(info['department']) < 200:
                                        break
                                    else:
                                        info['department'] = ''
                        if info['department']:
                            break
                    
                    if info['department']:
                        break
                if info['department']:
                    break
        
        # 테이블에서 찾지 못한 경우 텍스트에서 패턴으로 찾기
        if not info['department']:
            import re
            page_text = soup.get_text()
            # 담당부서 패턴 검색 (다양한 형식)
            patterns = [
                r'담당\s*부서\s*[:：]\s*([^\n\r]+)',
                r'담당부서\s*[:：]\s*([^\n\r]+)',
                r'담당\s*부서\s*[:\s]+([^\n\r]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    dept = match.group(1).strip()
                    # 너무 길면 제외 (200자 이상)
                    if dept and len(dept) < 200:
                        info['department'] = dept
                        break
        
        # 파일명 추출 (CSS Selector 사용)
        file_name_selectors = [
            '#Content > div > div.contentArea > div.conInfoArea > div.panViewArea.mt30 > ul.viewInfo > li.file > p > a',
            '#Content ul.viewInfo li.file p a',
            '.conInfoArea ul.viewInfo li.file p a',
            'ul.viewInfo li.file p a',
            'ul.viewInfo li.file a',
        ]
        
        for css_selector in file_name_selectors:
            try:
                file_link = soup.select_one(css_selector)
                if file_link:
                    file_name_text = file_link.get_text(strip=True)
                    if file_name_text and len(file_name_text) > 0:
                        info['file_name'] = file_name_text
                        print(f"  CSS 선택자로 파일명 발견 ({css_selector}): {file_name_text}")
                        break
            except Exception as e:
                continue
        
        # 제어 문자 제거
        if info['content']:
            import re
            info['content'] = info['content'].replace('\x00', '')
            info['content'] = re.sub(r'\n\s*\n\s*\n+', '\n\n', info['content'])
        
        return info
    
    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """
        페이지네이션에서 총 페이지 수 추출 (CSS Selector 사용)
        
        Args:
            soup: BeautifulSoup 객체
            
        Returns:
            총 페이지 수
        """
        if soup is None:
            return 1
        
        max_page = 1
        
        # CSS Selector로 페이지네이션 찾기 (여러 가능한 선택자 시도)
        pagination_selectors = [
            'div.pageArea',
            'div.paging',
            'div.pagination',
            '#pageArea',
            '#paging',
            '.pageArea',
            '.paging',
            '.pagination',
        ]
        
        pagination = None
        for selector in pagination_selectors:
            try:
                pagination = soup.select_one(selector)
                if pagination:
                    break
            except:
                continue
        
        if pagination:
            # CSS Selector로 페이지 링크 추출
            page_links = pagination.select('a[href]')
            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    max_page = max(max_page, int(text))
                
                # href에서 페이지 번호 찾기
                href = link.get('href', '')
                if href:
                    import re
                    # javascript:pageRun(숫자) 형식
                    if 'pageRun(' in href:
                        match = re.search(r'pageRun\((\d+)\)', href)
                        if match:
                            max_page = max(max_page, int(match.group(1)))
                    # ?page=숫자 형식
                    elif 'page=' in href:
                        match = re.search(r'page=(\d+)', href)
                        if match:
                            max_page = max(max_page, int(match.group(1)))
                    # &page=숫자 형식
                    elif '&page=' in href:
                        match = re.search(r'&page=(\d+)', href)
                        if match:
                            max_page = max(max_page, int(match.group(1)))
            
            # 페이지네이션 텍스트에서 "총 N 페이지" 같은 패턴 찾기
            pagination_text = pagination.get_text()
            import re
            total_match = re.search(r'총\s*(\d+)\s*페이지', pagination_text)
            if total_match:
                max_page = max(max_page, int(total_match.group(1)))
        
        # 페이지네이션을 찾지 못했으면 모든 링크에서 페이지 번호 찾기 (CSS Selector 사용)
        if max_page == 1:
            all_links = soup.select('a[href]')
            for link in all_links:
                href = link.get('href', '')
                if href:
                    import re
                    if 'pageRun(' in href:
                        match = re.search(r'pageRun\((\d+)\)', href)
                        if match:
                            max_page = max(max_page, int(match.group(1)))
                    elif 'page=' in href:
                        match = re.search(r'[?&]page=(\d+)', href)
                        if match:
                            max_page = max(max_page, int(match.group(1)))
        
        return max_page if max_page > 1 else 1
        
    def get_page_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        페이지네이션에서 실제 페이지 링크 추출 (CSS Selector 사용)
        
        Args:
            soup: BeautifulSoup 객체
            base_url: 기본 URL
            
        Returns:
            페이지 URL 리스트
        """
        page_urls = []
        
        if soup is None:
            return page_urls
        
        # CSS Selector로 페이지네이션 찾기
        pagination_selectors = [
            'div.pageArea',
            'div.paging',
            'div.pagination',
            '#pageArea',
            '#paging',
            '.pageArea',
            '.paging',
            '.pagination',
        ]
        
        pagination = None
        for selector in pagination_selectors:
            try:
                pagination = soup.select_one(selector)
                if pagination:
                    break
            except:
                continue
        
        if pagination:
            # CSS Selector로 페이지 링크 추출
            page_links = pagination.select('a[href]')
            seen_urls = set()
            
            for link in page_links:
                href = link.get('href', '')
                if not href:
                    continue
                
                # 절대 URL로 변환
                if href.startswith('http'):
                    page_url = href
                elif href.startswith('javascript:'):
                    # JavaScript 함수인 경우 URL 생성
                    import re
                    match = re.search(r'pageRun\((\d+)\)', href)
                    if match:
                        page_num = match.group(1)
                        page_url = f"{base_url}?page={page_num}"
                    else:
                        continue
                elif href.startswith('?'):
                    page_url = f"{base_url}{href}"
                elif href.startswith('&'):
                    page_url = f"{base_url}?{href[1:]}"
                else:
                    page_url = urljoin(base_url, href)
                
                if page_url and page_url not in seen_urls:
                    seen_urls.add(page_url)
                    page_urls.append(page_url)
        
        return page_urls
    
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
    
    def _download_and_compare_file(
        self, file_url: str, file_name: str, regulation_name: str = "", 
        use_selenium: bool = False, driver=None
    ) -> Optional[Dict]:
        """파일 다운로드 및 이전 파일과 비교
        Args:
            file_url: 다운로드 URL
            file_name: 파일명
            regulation_name: 규정명 (파일명 생성용)
            use_selenium: Selenium 사용 여부
            driver: Selenium WebDriver
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            import shutil
            
            # 파일 확장자 추출
            ext = Path(file_name).suffix if file_name else ''
            if not ext:
                # URL에서 확장자 확인
                url_lower = file_url.lower()
                if '.zip' in url_lower:
                    ext = '.zip'
                elif '.pdf' in url_lower:
                    ext = '.pdf'
                elif '.hwp' in url_lower:
                    ext = '.hwp'
                else:
                    ext = '.hwp'  # 기본값
            
            # 안전한 파일명 생성 (규정명 기반)
            if regulation_name:
                safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
                safe_reg_name = safe_reg_name.replace(' ', '_')
                safe_filename = f"{safe_reg_name}{ext}"
            else:
                # 규정명이 없으면 원본 파일명 사용 (정리)
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
            
            # 파일 다운로드
            print(f"  → 파일 다운로드 중: {file_name}")
            downloaded_result = self.file_extractor.download_file(
                file_url,
                safe_filename,
                use_selenium=use_selenium,
                driver=driver,
                referer='https://www.kfb.or.kr/publicdata/reform_info.php'
            )
            
            if downloaded_result:
                downloaded_path, actual_filename = downloaded_result
            else:
                downloaded_path, actual_filename = None, None
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                print(f"  ⚠ 파일 다운로드 실패")
                return None
            
            # 다운로드한 파일을 새 파일 경로로 이동/복사
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
    
    def crawl_self_regulation(self, limit: int = 0, download_files: bool = True, content_limit: int = 0) -> List[Dict]:
        """
        자율규제 스크래핑
        URL: https://www.kfb.or.kr/publicdata/reform_info.php
        
        Args:
            limit: 가져올 개수 제한 (0=전체)
            download_files: HWP 파일 다운로드 및 내용 추출 여부
            content_limit: 본문 길이 제한 (0=제한 없음, 문자 수)
        """
        # 스크래퍼 시작 시 current를 previous로 백업 (이전 실행 결과를 이전 버전으로)
        self._backup_current_to_previous()
        # 이전 실행의 diff 파일 정리
        self._clear_diffs_directory()
        
        base_url = "https://www.kfb.or.kr/publicdata/reform_info.php"
        all_results = []
        
        # Selenium 드라이버 생성 (페이지네이션 처리용, HWP 다운로드도 재사용)
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ko-KR')
            # 다운로드 경로 설정 (current 디렉토리)
            prefs = {
                "download.default_directory": os.path.abspath(str(self.current_dir)),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            # 폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용 (SeleniumManager 우회)
            driver = self._create_webdriver(chrome_options)
            print("Selenium 드라이버 생성 완료 (페이지네이션 및 다운로드용)")
        except Exception as e:
            print(f"⚠ Selenium 드라이버 생성 실패: {e}, requests로 시도합니다.")
            driver = None
        
        # 첫 페이지 가져오기
        url = base_url
        if driver:
            try:
                driver.get(url)
                time.sleep(2)  # 페이지 로딩 대기
                soup = BeautifulSoup(driver.page_source, 'lxml')
            except Exception as e:
                print(f"⚠ Selenium으로 첫 페이지 가져오기 실패: {e}, requests로 시도")
                soup = self.fetch_page(url, use_selenium=False)
        else:
            soup = self.fetch_page(url, use_selenium=False)
        
        if not soup:
            print("페이지를 가져오는데 실패했습니다.")
            if driver:
                driver.quit()
            return all_results
        
        # 총 페이지 수 확인
        total_pages = self.get_total_pages(soup)
        if total_pages is None:
            total_pages = 1  # 기본값 설정
        print(f"총 페이지 수: {total_pages}")
        
        # 디버깅: 페이지네이션 요소 확인
        pagination_elements = soup.select('div.pageArea, div.paging, div.pagination, #pageArea, #paging')
        if pagination_elements:
            print(f"페이지네이션 요소 발견: {len(pagination_elements)}개")
            for idx, elem in enumerate(pagination_elements[:3]):  # 처음 3개만
                print(f"  요소 {idx+1}: {elem.get_text(strip=True)[:100]}")
        else:
            print("⚠ 페이지네이션 요소를 찾지 못했습니다.")
        
        # 중복 방지를 위한 번호 추적
        seen_numbers = set()
        
        # 첫 페이지 데이터 추출
        page_results = self.extract_table_data(soup, self.BASE_URL)
        for item in page_results:
            item_no = item.get('no', '')
            if item_no and item_no not in seen_numbers:
                seen_numbers.add(item_no)
                all_results.append(item)
        print(f"페이지 1/{total_pages} 완료: {len(page_results)}개 추출 (누적: {len(all_results)}개)")
        
        # 나머지 페이지 처리 (Selenium으로 페이지네이션 클릭)
        if total_pages and total_pages > 1 and driver:
            print(f"\n=== 페이지네이션 스크래핑 시작 (총 {total_pages}페이지) ===")
            for page_num in range(2, total_pages + 1):
                try:
                    # 페이지네이션 링크 찾기 (여러 방법 시도)
                    page_clicked = False
                    
                    # 방법 1: 페이지 번호로 직접 찾기 - CSS Selector 우선 시도, 실패 시 XPath 사용
                    try:
                        # CSS Selector로 시도 (페이지 번호가 href나 data 속성에 있는 경우)
                        try:
                            page_link = driver.find_element(By.CSS_SELECTOR, f"a[href*='page={page_num}'], a[onclick*='{page_num}']")
                            driver.execute_script("arguments[0].click();", page_link)
                            page_clicked = True
                            print(f"페이지 {page_num}/{total_pages} 클릭 (방법 1: CSS Selector)")
                        except:
                            # CSS Selector 실패 시 XPath로 텍스트 매칭 (텍스트 내용으로 찾기)
                            page_link = driver.find_element(By.XPATH, f"//a[contains(text(), '{page_num}')]")
                            driver.execute_script("arguments[0].click();", page_link)
                            page_clicked = True
                            print(f"페이지 {page_num}/{total_pages} 클릭 (방법 1: XPath)")
                    except:
                        pass
                    
                    # 방법 2: JavaScript 함수 호출
                    if not page_clicked:
                        try:
                            driver.execute_script(f"pageRun({page_num});")
                            page_clicked = True
                            print(f"페이지 {page_num}/{total_pages} 클릭 (방법 2: JavaScript)")
                        except:
                            pass
                    
                    # 방법 3: URL로 직접 이동
                    if not page_clicked:
                        try:
                            page_url = f"{base_url}?page={page_num}"
                            driver.get(page_url)
                            page_clicked = True
                            print(f"페이지 {page_num}/{total_pages} 이동 (방법 3: URL)")
                        except:
                            pass
                    
                    if not page_clicked:
                        print(f"⚠ 페이지 {page_num}/{total_pages} 이동 실패, 다음 시도")
                        continue
                    
                    # 페이지 로딩 대기
                    time.sleep(2)
                    
                    # 페이지 소스 가져오기
                    page_soup = BeautifulSoup(driver.page_source, 'lxml')
                    
                    # 데이터 추출
                    page_data = self.extract_table_data(page_soup, self.BASE_URL)
                    new_items = []
                    for item in page_data:
                        item_no = item.get('no', '')
                        if item_no and item_no not in seen_numbers:
                            seen_numbers.add(item_no)
                            new_items.append(item)
                            all_results.append(item)
                    
                    if new_items:
                        print(f"  페이지 {page_num}/{total_pages} 완료: {len(new_items)}개 추출 (누적: {len(all_results)}개)")
                    else:
                        print(f"  페이지 {page_num}/{total_pages} 완료: 중복 데이터만 발견 (누적: {len(all_results)}개)")
                        # 중복만 있고 새 데이터가 없으면 종료
                        if len(page_data) > 0:
                            print(f"  모든 데이터가 중복이므로 스크래핑 종료")
                            break
                    
                    # 페이지 수 업데이트 확인
                    current_total = self.get_total_pages(page_soup)
                    if current_total > total_pages:
                        print(f"  페이지 수가 {total_pages}에서 {current_total}로 업데이트되었습니다.")
                        total_pages = current_total
                        
                except Exception as e:
                    print(f"  ✗ 페이지 {page_num}/{total_pages} 처리 중 오류: {e}")
                    # 오류가 발생해도 계속 진행
                    continue
        
        elif total_pages and total_pages > 1:
            # Selenium이 없으면 URL 생성 방식 사용
            print("페이지 링크를 찾을 수 없어 URL 생성 방식 사용")
            for page_num in range(2, total_pages + 1):
                # 다양한 URL 형식 시도
                page_urls = [
                    f"{base_url}?page={page_num}",
                    f"{base_url}?p={page_num}",
                ]
                
                page_soup = None
                for page_url in page_urls:
                    print(f"페이지 {page_num}/{total_pages} 스크래핑 시도: {page_url}")
                    page_soup = self.fetch_page(page_url, use_selenium=False)
                    if page_soup:
                        test_data = self.extract_table_data(page_soup, self.BASE_URL)
                        if test_data and len(test_data) > 0:
                            if test_data[0].get('no') not in seen_numbers:
                                break
                        else:
                            page_soup = None
                
                if page_soup:
                    page_data = self.extract_table_data(page_soup, self.BASE_URL)
                    new_items = []
                    for item in page_data:
                        item_no = item.get('no', '')
                        if item_no and item_no not in seen_numbers:
                            seen_numbers.add(item_no)
                            new_items.append(item)
                            all_results.append(item)
                    
                    if new_items:
                        print(f"  페이지 {page_num}/{total_pages} 완료: {len(new_items)}개 추출 (누적: {len(all_results)}개)")
                    else:
                        print(f"  페이지 {page_num}/{total_pages} 완료: 중복 데이터만 발견 (누적: {len(all_results)}개)")
                        # 중복만 있고 새 데이터가 없으면 종료
                        if len(new_items) == 0 and len(page_data) > 0:
                            print(f"  모든 데이터가 중복이므로 스크래핑 종료")
                        break
                    
                    # 페이지 수 업데이트 확인
                    current_total = self.get_total_pages(page_soup)
                    if current_total > total_pages:
                        print(f"  페이지 수가 {total_pages}에서 {current_total}로 업데이트되었습니다.")
                        total_pages = current_total
                else:
                    print(f"  페이지 {page_num}/{total_pages} 가져오기 실패")
                    # 연속으로 실패하면 종료
                    if page_num >= total_pages:
                        break
        
        # 제한 적용
        if limit > 0 and len(all_results) > limit:
            all_results = all_results[:limit]
            print(f"제한 적용: 처음 {limit}개 항목만 사용")
        
        # 모든 항목에 기본 정보 설정
        for item in all_results:
            if 'regulation_name' not in item:
                item['regulation_name'] = item.get('title', '')
            if 'organization' not in item:
                item['organization'] = '은행연합회'
            if 'content' not in item:
                item['content'] = ''
            if 'department' not in item:
                item['department'] = ''
            if 'file_download_link' not in item:
                item['file_download_link'] = item.get('download_link', '')
            if 'file_name' not in item:
                item['file_name'] = ''
            if 'enactment_date' not in item:
                item['enactment_date'] = ''
            if 'revision_date' not in item:
                item['revision_date'] = ''
        
        # 상세 페이지 스크래핑 (본문 내용 및 소관부서 추출)
        print(f"\n=== 상세 페이지 스크래핑 시작 ===")
        print(f"총 {len(all_results)}개 항목의 상세 페이지를 처리합니다...")
        
        for idx, item in enumerate(all_results, 1):
            detail_link = item.get('detail_link', '')
            if not detail_link:
                print(f"[{idx}/{len(all_results)}] 상세 링크 없음: {item.get('title', 'N/A')[:50]}...")
                continue
            
            print(f"[{idx}/{len(all_results)}] {item.get('title', 'N/A')[:50]}... 상세 페이지 스크래핑 중")
            
            # 상세 페이지 가져오기
            detail_soup = None
            
            # JavaScript 함수 호출인 경우 처리
            if detail_link.startswith('javascript:') or detail_link.startswith('Javascript:'):
                if driver:
                    try:
                        # JavaScript 함수 실행 (예: readRun(37))
                        import re
                        match = re.search(r'readRun\((\d+)\)', detail_link, re.IGNORECASE)
                        if match:
                            num = match.group(1)
                            # 현재 URL 저장 (변경 확인용)
                            before_url = driver.current_url
                            
                            # JavaScript 함수 실행
                            driver.execute_script(f"readRun({num});")
                            
                            # 페이지 변경 또는 팝업 표시 대기
                            time.sleep(2)
                            
                            # 팝업/모달이 열렸는지 확인 (다양한 방법 시도)
                            detail_soup = None
                            
                            # 방법 1: iframe 확인 - CSS Selector 사용
                            try:
                                iframes = driver.find_elements(By.CSS_SELECTOR, 'iframe')
                                if iframes:
                                    print(f"  iframe 발견: {len(iframes)}개")
                                    for iframe_idx, iframe in enumerate(iframes):
                                        try:
                                            driver.switch_to.frame(iframe)
                                            time.sleep(1)
                                            iframe_soup = BeautifulSoup(driver.page_source, 'lxml')
                                            # iframe 내부에 본문이 있는지 확인
                                            test_content = iframe_soup.get_text(strip=True)
                                            if len(test_content) > 50:  # 충분한 내용이 있으면
                                                detail_soup = iframe_soup
                                                print(f"  iframe {iframe_idx + 1}에서 본문 발견 ({len(test_content)}자)")
                                                break
                                            driver.switch_to.default_content()
                                        except Exception as e:
                                            driver.switch_to.default_content()
                                            continue
                            except Exception as e:
                                print(f"  iframe 확인 중 오류: {e}")
                            
                            # 방법 2: 팝업/모달 확인 (div.popup, div.modal 등)
                            if not detail_soup:
                                try:
                                    popup_selectors = [
                                        'div.popup', 'div.modal', 'div.dialog', 'div.popup-content',
                                        'div.modal-content', 'div.view-popup', 'div.detail-popup',
                                        '[class*="popup"]', '[class*="modal"]', '[class*="dialog"]',
                                        '[id*="popup"]', '[id*="modal"]', '[id*="dialog"]'
                                    ]
                                    for selector in popup_selectors:
                                        try:
                                            popup_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                            if popup_elements:
                                                print(f"  팝업/모달 발견: {selector}")
                                                # 첫 번째 팝업의 HTML 가져오기
                                                popup_html = popup_elements[0].get_attribute('outerHTML')
                                                if popup_html:
                                                    detail_soup = BeautifulSoup(popup_html, 'lxml')
                                                    test_content = detail_soup.get_text(strip=True)
                                                    if len(test_content) > 50:
                                                        print(f"  팝업에서 본문 발견 ({len(test_content)}자)")
                                                        break
                                                    else:
                                                        detail_soup = None
                                        except:
                                            continue
                                except Exception as e:
                                    print(f"  팝업 확인 중 오류: {e}")
                            
                            # 방법 3: 페이지 URL 변경 확인 및 재접근
                            if not detail_soup:
                                try:
                                    current_url = driver.current_url
                                    if current_url != before_url:
                                        print(f"  페이지 URL 변경: {before_url} -> {current_url}")
                                        # 변경된 URL로 다시 접근하여 페이지 로딩 대기
                                        driver.get(current_url)
                                        time.sleep(2)
                                        detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                                    else:
                                        detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                                except Exception as e:
                                    print(f"  페이지 소스 가져오기 실패: {e}")
                                    detail_soup = None
                        else:
                            # 다른 JavaScript 함수인 경우 직접 실행
                            js_code = detail_link.replace('javascript:', '').replace('Javascript:', '')
                            driver.execute_script(js_code)
                            time.sleep(3)
                            detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                    except Exception as e:
                        print(f"  ⚠ JavaScript 함수 실행 실패: {e}")
                        import traceback
                        traceback.print_exc()
                        detail_soup = None
                else:
                    print(f"  ⚠ JavaScript 링크는 Selenium이 필요합니다: {detail_link}")
                    detail_soup = None
            else:
                # 일반 URL인 경우
                if driver:
                    try:
                        driver.get(detail_link)
                        time.sleep(2)  # 페이지 로딩 대기
                        detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                    except Exception as e:
                        print(f"  ⚠ Selenium으로 상세 페이지 가져오기 실패: {e}, requests로 시도")
                        detail_soup = self.fetch_page(detail_link, use_selenium=False)
                else:
                    detail_soup = self.fetch_page(detail_link, use_selenium=False)
          
            if detail_soup:
                # 디버깅: 첫 번째 상세 페이지만 HTML 저장 (공통 메서드 사용)
                self.save_debug_html(detail_soup)
                
                # 상세 페이지에서 본문, 소관부서, 파일명 추출
                detail_info = self.extract_detail_page_info(detail_soup)
                # 본문 내용 처리 (개행 유지, 4000자 제한)
                content = detail_info.get('content', '') or ''
                # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                if len(content) > 4000:
                    content = content[:4000]
                item['content'] = content
                item['department'] = detail_info.get('department', '')
                # 상세 페이지에서 추출한 파일명 저장 (다운로드 시 사용)
                if detail_info.get('file_name'):
                    item['file_name'] = detail_info.get('file_name')
                    print(f"  ✓ 파일명 추출: {detail_info.get('file_name')}")
                
                if content:
                    content_preview = content[:100].replace('\n', ' ')
                    print(f"  ✓ 본문 내용 추출 완료 ({len(content)}자): {content_preview}...")
                else:
                    print(f"  ⚠ 본문 내용 추출 실패")
                
                if detail_info.get('department'):
                    print(f"  ✓ 담당부서 추출: {detail_info.get('department')}")
                else:
                    print(f"  ⚠ 담당부서 추출 실패")
            else:
                print(f"  ✗ 상세 페이지 가져오기 실패")
        
        print(f"\n=== 상세 페이지 스크래핑 완료 ===")
        
        # HWP 파일 다운로드 및 내용 추출 (제정일/최근개정일 추출용)
        if download_files:
            print(f"\n=== HWP 파일 다운로드 및 내용 추출 시작 ===")
            print(f"총 {len(all_results)}개 항목의 파일을 처리합니다...")
            
            # Selenium 드라이버가 없으면 생성 (HWP 다운로드용)
            if not driver:
                try:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options
                    chrome_options = Options()
                    chrome_options.add_argument('--headless')
                    chrome_options.add_argument('--no-sandbox')
                    chrome_options.add_argument('--disable-dev-shm-usage')
                    chrome_options.add_argument('--disable-gpu')
                    chrome_options.add_argument('--lang=ko-KR')
                    prefs = {
                        "download.default_directory": os.path.abspath(str(self.current_dir)),
                        "download.prompt_for_download": False,
                        "download.directory_upgrade": True,
                        "safebrowsing.enabled": True
                    }
                    chrome_options.add_experimental_option("prefs", prefs)
                    # 폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용 (SeleniumManager 우회)
                    driver = self._create_webdriver(chrome_options)
                except Exception as e:
                    print(f"  ⚠ Selenium 드라이버 생성 실패: {e}, requests로 시도합니다.")
                    driver = None
            
            for idx, item in enumerate(all_results, 1):
                download_link = item.get('download_link', '')
                
                # 다운로드 링크가 없어도 기본 정보는 설정
                if not download_link:
                    item['file_download_link'] = ''
                    item['file_name'] = ''
                    # 제정일/최근개정일은 파일에서 추출하지 못하므로 그대로 유지
                    continue
                
                # 파일 다운로드 링크 저장
                item['file_download_link'] = download_link
                
                # 파일명은 상세 페이지에서 추출한 것이 있으면 사용, 없으면 다운로드 후 업데이트
                if not item.get('file_name'):
                    item['file_name'] = ''
                
                if '.hwp' in download_link.lower() or '.pdf' in download_link.lower() or '.zip' in download_link.lower() or 'download.php' in download_link:
                    print(f"[{idx}/{len(all_results)}] {item.get('title', 'N/A')[:50]}... 파일 다운로드 중")
                    
                    # 규정명 추출 (파일명 생성용)
                    regulation_name = item.get('regulation_name', item.get('title', ''))
                    # 파일명은 상세 페이지에서 추출한 것이 있으면 사용, 없으면 규정명 사용
                    file_name_for_download = item.get('file_name', '').strip() if item.get('file_name') else ''
                    if not file_name_for_download:
                        file_name_for_download = item.get('title', 'file')
                    
                    # 파일 다운로드 및 비교
                    comparison_result = self._download_and_compare_file(
                        download_link,
                        file_name_for_download,
                        regulation_name=regulation_name,
                        use_selenium=(driver is not None),
                        driver=driver
                    )
                    
                    if comparison_result:
                        filepath = comparison_result.get('file_path')
                        if filepath and os.path.exists(filepath):
                            # 다운로드한 파일 형식 확인 (파일 시그니처 확인)
                            try:
                                with open(filepath, 'rb') as f:
                                    first_bytes = f.read(4)
                                    # PDF 시그니처: %PDF
                                    if first_bytes[:4] == b'%PDF':
                                        # PDF 파일로 확장자 업데이트
                                        if not filepath.lower().endswith('.pdf'):
                                            new_filepath = filepath.rsplit('.', 1)[0] + '.pdf'
                                            try:
                                                os.rename(filepath, new_filepath)
                                                filepath = new_filepath
                                                print(f"  파일 확장자를 .pdf로 변경: {os.path.basename(filepath)}")
                                            except:
                                                pass
                                    # ZIP 파일 시그니처: PK\x03\x04 또는 PK\x05\x06 (빈 ZIP)
                                    elif first_bytes[:2] == b'PK':
                                        # ZIP 파일로 확장자 업데이트
                                        if not filepath.lower().endswith('.zip'):
                                            new_filepath = filepath.rsplit('.', 1)[0] + '.zip'
                                            try:
                                                os.rename(filepath, new_filepath)
                                                filepath = new_filepath
                                                print(f"  파일 확장자를 .zip으로 변경: {os.path.basename(filepath)}")
                                            except:
                                                pass
                            except:
                                pass
                            
                            # 파일 내용 추출 (HWP, PDF, ZIP 모두 처리)
                            hwp_content = self.extract_hwp_content(filepath)
                            item['file_content'] = hwp_content
                            item['file_path'] = filepath
                            
                            # HWP 내용에서 법규 정보 추출 (제정일/최근개정일 추출)
                            if hwp_content:
                                law_info = self.extract_law_info_from_content(hwp_content, item.get('title', ''))
                                # 규정명은 파일에서 추출한 것이 더 정확할 수 있으므로 업데이트
                                if law_info.get('regulation_name') and law_info.get('regulation_name') != item.get('title', ''):
                                    item['regulation_name'] = law_info.get('regulation_name', item.get('title', ''))
                                # 제정일과 최근개정일만 파일에서 추출한 것으로 업데이트
                                if law_info.get('enactment_date'):
                                    item['enactment_date'] = law_info.get('enactment_date')
                                if law_info.get('revision_date'):
                                    item['revision_date'] = law_info.get('revision_date')
                                
                                # 본문은 파일 내용으로 설정 (4000자 제한, 개행 유지)
                                original_length = len(hwp_content)
                                # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                                hwp_content = hwp_content.replace("\r\n", "\n").replace("\r", "\n")
                                # 4000자 제한 (content_limit이 있으면 그것도 고려하되, 최대 4000자)
                                max_length = min(4000, content_limit) if content_limit > 0 else 4000
                                if len(hwp_content) > max_length:
                                    item['content'] = hwp_content[:max_length]
                                    if original_length > max_length:
                                        print(f"  ⚠ 본문 길이 제한 적용: {original_length}자 → {max_length}자")
                                else:
                                    item['content'] = hwp_content
                                
                                print(f"  ✓ 파일 내용 추출 완료 ({len(hwp_content)}자)")
                                if law_info.get('enactment_date'):
                                    print(f"    제정일: {law_info.get('enactment_date')}")
                                if law_info.get('revision_date'):
                                    print(f"    최근 개정일: {law_info.get('revision_date')}")
                            else:
                                # 파일 내용 추출 실패 시 제정일/최근개정일은 그대로 유지
                                # 본문은 상세 페이지에서 추출한 내용 유지 (파일이 없을 경우)
                                print(f"  ⚠ 파일 내용 추출 실패 또는 빈 파일")
                            
                            # 파일은 output/downloads/current 디렉토리에 보관
                            print(f"  ✓ 파일 저장 완료: {filepath}")
                        else:
                            print(f"  ✗ 파일 다운로드 실패")
                            item['file_content'] = ""
                            item['file_path'] = ""
                            # 기본 정보 설정
                            item['regulation_name'] = item.get('title', '')
                            item['organization'] = '은행연합회'
                            item['content'] = ''
                            item['enactment_date'] = ''
                            item['revision_date'] = ""
            
            print(f"\n=== HWP 파일 다운로드 및 내용 추출 완료 ===")
        
        # Selenium 드라이버 종료 (페이지네이션 및 다운로드용)
        if driver:
            try:
                driver.quit()
                print("Selenium 드라이버 종료 완료")
            except:
                pass
        
        return all_results
    
    def crawl_self_regulation_notice(self) -> List[Dict]:
        """
        자율규제 제정·개정 예고 스크래핑
        URL: https://www.kfb.or.kr/publicdata/reform_notice.php
        """
        url = "https://www.kfb.or.kr/publicdata/reform_notice.php"
        soup = self.fetch_page(url, use_selenium=True)
        
        results = []
        # TODO: 실제 페이지 구조에 맞춰 데이터 추출 구현
        return results
    
    def crawl_regulatory_review_committee(self) -> List[Dict]:
        """
        규제심의위원회 결과 스크래핑
        URL: https://www.kfb.or.kr/publicdata/reform_result.php
        """
        url = "https://www.kfb.or.kr/publicdata/reform_result.php"
        soup = self.fetch_page(url, use_selenium=True)
        
        results = []
        # TODO: 실제 페이지 구조에 맞춰 데이터 추출 구현
        return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='은행연합회 자율규제 스크래퍼')
    parser.add_argument('--limit', type=int, default=0, help='가져올 개수 제한 (0=전체)')
    parser.add_argument('--no-download', action='store_true', help='HWP 파일 다운로드 및 내용 추출 건너뛰기')
    parser.add_argument('--content', type=int, default=0, help='본문 길이 제한 (0=제한 없음, 문자 수)')
    args = parser.parse_args()
    
    crawler = KfbScraper()
    results = crawler.crawl_self_regulation(limit=args.limit, download_files=not args.no_download, content_limit=args.content)
    
    print(f"\n=== 최종 결과 ===")
    print(f"추출된 데이터: {len(results)}개")
    
    if results:
        print("\n=== 추출된 데이터 (처음 5개) ===")
        for i, item in enumerate(results[:5], 1):
            print(f"\n{i}. 번호: {item.get('no', 'N/A')}")
            print(f"   제목: {item.get('title', 'N/A')}")
            print(f"   상세링크: {item.get('detail_link', 'N/A')}")
            print(f"   다운로드링크: {item.get('download_link', 'N/A')}")
            if item.get('file_content'):
                content = item.get('file_content', '')
                print(f"   파일내용: {content[:100]}... ({len(content)}자)")
            if item.get('file_path'):
                print(f"   파일경로: {item.get('file_path', 'N/A')}")
    
    # 결과 저장
    if results:
        import json
        import os
        os.makedirs('output', exist_ok=True)
        
        # 날짜 정규화를 위한 scraper 인스턴스
        scraper = KfbScraper()
        
        # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
        law_results = []
        for item in results:
            law_item = {
                '번호': item.get('no', ''),
                '규정명': item.get('regulation_name', item.get('title', '')),
                '기관명': '은행연합회',  # 항상 은행연합회
                '본문': item.get('content', ''),
                '제정일': scraper.normalize_date_format(item.get('enactment_date', '')),
                '최근 개정일': scraper.normalize_date_format(item.get('revision_date', '')),
                '소관부서': item.get('department', ''),
                '파일 다운로드 링크': item.get('file_download_link', item.get('download_link', '')),
                '파일 이름': item.get('file_name', '')
            }
            law_results.append(law_item)
        
        # JSON 저장 (법규 정보만) - output/json 디렉토리에 저장
        json_dir = os.path.join('output', 'json')
        os.makedirs(json_dir, exist_ok=True)
        
        law_json_data = {
            'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'url': 'https://www.kfb.or.kr/publicdata/reform_info.php',
            'total_count': len(law_results),
            'results': law_results
        }
        
        json_path = os.path.join(json_dir, 'kfb_scraper.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(law_json_data, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 저장 완료: {json_path}")
        
        # CSV 저장 (법규 정보만: 번호, 규정명, 기관명, 본문, 제정일, 최근 개정일) - output/csv 디렉토리에 저장
        import csv
        csv_dir = os.path.join('output', 'csv')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'kfb_scraper.csv')
        
        # 헤더 정의 (번호, 규정명, 기관명, 본문, 제정일, 최근 개정일, 소관부서, 파일 다운로드 링크, 파일 이름)
        headers = ["번호", "규정명", "기관명", "본문", "제정일", "최근 개정일", "소관부서", "파일 다운로드 링크", "파일 이름"]
        
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for law_item in law_results:
                # 본문 내용 처리 (개행 유지, 4000자 제한)
                content = law_item.get('본문', '') or ''
                # \r\n을 \n으로 통일하고, \r만 있는 경우도 \n으로 변환
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                if len(content) > 4000:
                    content = content[:4000]
                
                csv_item = law_item.copy()
                csv_item['본문'] = content
                writer.writerow(csv_item)
        
        print(f"CSV 저장 완료: {csv_path}")

