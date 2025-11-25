"""
한국은행 스크래퍼
CSV 목록 기반으로 법규 정보 스크래핑
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
import json
import csv
import time
import re
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor
from common.file_comparator import FileComparator


class BokScraper(BaseScraper):
    """한국은행 스크래퍼 - CSV 목록 기반으로 법규 정보 수집"""
    
    BASE_URL = "https://www.bok.or.kr"
    # 검색 URL 템플릿 (검색어를 파라미터로 받음)
    SEARCH_URL_TEMPLATE = "https://www.bok.or.kr/portal/singl/law/listSearch.do?menuNo=200200&parentlawseq=&detaillawseq=&lawseq=&search_text={search_text}"
    DEFAULT_CSV_PATH = "BOK_Scraper/input/list.csv"
    
    def __init__(self, delay: float = 1.0, csv_path: Optional[str] = None):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        self.previous_dir = os.path.join("output", "downloads", "previous", "bok")
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.previous_dir, exist_ok=True)
        # FileExtractor 초기화 (session 전달)
        self.file_extractor = FileExtractor(download_dir=self.download_dir, session=self.session)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=self.download_dir)
        # CSV에서 대상 규정 목록 로드
        self.csv_path = csv_path or self.DEFAULT_CSV_PATH
        self.target_laws = self._load_target_laws(self.csv_path)
        if self.target_laws:
            print(f"✓ CSV에서 {len(self.target_laws)}개의 대상 규정을 불러왔습니다: {self.csv_path}")
        else:
            print("⚠ 대상 CSV를 찾지 못했거나 비어 있습니다. 전체 목록을 대상으로 진행합니다.")
    
    def _load_target_laws(self, csv_path: str) -> List[Dict]:
        """CSV 파일에서 스크래핑 대상 규정명을 로드한다."""
        if not csv_path:
            return []
        csv_file = Path(csv_path)
        if not csv_file.is_absolute():
            csv_file = find_project_root() / csv_path
        if not csv_file.exists():
            print(f"⚠ BOK 대상 CSV를 찾을 수 없습니다: {csv_file}")
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
            print(f"⚠ BOK 대상 CSV 로드 실패: {exc}")
            return []
        return targets
    
    def _normalize_title(self, text: Optional[str]) -> str:
        """비교를 위한 규정명 정규화"""
        if not text:
            return ""
        cleaned = re.sub(r"[\s\W]+", "", text)
        return cleaned.lower()
    
    def is_target_regulation(self, title: str) -> bool:
        """제목이 대상 규정인지 확인 (CSV 목록 기반)"""
        if not title or not self.target_laws:
            return True  # CSV가 없으면 모든 항목 허용
        
        title_normalized = self._normalize_title(title)
        for target in self.target_laws:
            target_normalized = self._normalize_title(target["law_name"])
            # 정규화된 이름이 일치하거나 포함 관계인지 확인
            if target_normalized == title_normalized or target_normalized in title_normalized or title_normalized in target_normalized:
                return True
        return False
    
    def extract_regulation_list(self, soup: BeautifulSoup) -> List[Dict]:
        """법규 목록에서 대상 규정만 추출"""
        results = []
        
        # 페이지 구조에 따라 다양한 선택자 시도
        # 검색 결과 페이지는 보통 리스트 형태로 표시됨
        selectors = [
            "ul li",  # 리스트 항목
            "table tbody tr",  # 테이블 행
            ".list-item",
            ".law-item",
            ".regulation-item",
            "div.list li",
            "li a",  # 링크가 있는 리스트 항목
        ]
        
        found_items = []
        for selector in selectors:
            items = soup.select(selector)
            if items and len(items) > 0:
                # 빈 항목이나 헤더 제외하고 실제 데이터 항목만 필터링
                valid_items = []
                for item in items:
                    # 링크가 있거나 텍스트가 있는 항목만 포함
                    link = item.select_one("a")
                    text = item.get_text(strip=True)
                    if (link or text) and len(text) > 10:  # 최소한의 텍스트 길이 확인
                        valid_items.append(item)
                
                if valid_items:
                    found_items = valid_items
                    print(f"  ✓ 선택자 '{selector}'로 {len(valid_items)}개 항목 발견")
                    break
        
        if not found_items:
            # 디버깅을 위해 HTML 일부 저장
            self.save_debug_html(soup, filename="debug_bok_list.html")
            print("  ⚠ 목록 항목을 찾지 못했습니다. 디버그 HTML 저장: output/debug/debug_bok_list.html")
            print("  💡 디버그 HTML을 확인하여 실제 페이지 구조를 파악해주세요.")
            return results
        
        for item in found_items:
            try:
                # 제목 추출 (다양한 방법 시도)
                title = None
                title_elem = (
                    item.select_one("a") or
                    item.select_one(".title") or
                    item.select_one("td:first-child") or
                    item.select_one(".name") or
                    item.select_one("strong") or
                    item  # 전체 항목에서 텍스트 추출
                )
                
                if title_elem:
                    # 링크가 있으면 링크 텍스트 우선, 없으면 전체 텍스트
                    if title_elem.name == "a":
                        title = title_elem.get_text(strip=True)
                    else:
                        # 링크 텍스트를 먼저 시도
                        link_in_elem = title_elem.select_one("a")
                        if link_in_elem:
                            title = link_in_elem.get_text(strip=True)
                        else:
                            title = title_elem.get_text(strip=True)
                
                # 제목이 없으면 스킵
                if not title or len(title) < 5:
                    continue
                
                # 모든 규정을 추출 (필터링은 나중에 _filter_regulations_by_targets에서 수행)
                # print(f"  ✓ 규정 발견: {title}")
                
                # 상세 링크 추출
                detail_link = ""
                link_elem = item.select_one("a[href]")
                if link_elem:
                    href = link_elem.get("href", "")
                    if href:
                        # 상대 경로인 경우 절대 경로로 변환
                        if href.startswith("/"):
                            detail_link = self.BASE_URL + href
                        elif href.startswith("http"):
                            detail_link = href
                        else:
                            detail_link = urljoin(self.BASE_URL, href)
                
                # 추가 정보 추출 (개정일, 번호 등)
                regulation_info = {
                    "title": title,
                    "regulation_name": title,
                    "organization": "한국은행",
                    "detail_link": detail_link,
                    "content": "",
                    "department": "",
                    "file_names": [],
                    "download_links": [],
                    "enactment_date": "",
                    "revision_date": "",
                }
                
                # 개정일 추출 시도 (다양한 패턴)
                date_text = None
                date_elem = (
                    item.select_one(".date") or
                    item.select_one(".revision-date") or
                    item.select_one("td:nth-child(3)") or
                    item.select_one("td:nth-child(2)") or
                    item.select_one("span.date") or
                    item.select_one("em.date")
                )
                
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                else:
                    # 전체 텍스트에서 날짜 패턴 찾기 (YYYY-MM-DD 형식)
                    import re
                    full_text = item.get_text()
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', full_text)
                    if date_match:
                        date_text = date_match.group(1)
                
                if date_text:
                    regulation_info["revision_date"] = date_text
                    print(f"    개정일: {date_text}")
                
                results.append(regulation_info)
                
            except Exception as e:
                print(f"  ⚠ 항목 추출 중 오류: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return results
    
    def extract_regulation_detail(self, url: str, regulation_name: str = "") -> Dict:
        """상세 페이지에서 규정 내용 추출"""
        detail_info = {
            "content": "",  # PDF에서 추출한 본문 내용
            "file_names": [],
            "download_links": [],
            "revision_date": "",
            "enactment_date": "",  # 제정일
            "department": "",  # 소관부서
        }
        
        try:
            soup = self.fetch_page(url, use_selenium=True)
            
            # 파일링크와 파일명 추출: #main-container > div.content > div.bdView > div > div > table > tbody > tr:nth-child(1) > td:nth-child(3) > a
            file_selector = "#main-container > div.content > div.bdView > div > div > table > tbody > tr:nth-child(1) > td:nth-child(3) > a"
            file_elem = soup.select_one(file_selector)
            
            if file_elem:
                href = file_elem.get("href", "")
                if href:
                    # 상대 경로인 경우 절대 경로로 변환
                    if href.startswith("/"):
                        file_url = self.BASE_URL + href
                    elif href.startswith("http"):
                        file_url = href
                    else:
                        file_url = urljoin(self.BASE_URL, href)
                    
                    # 파일명 추출: href의 fileNm 파라미터에서 추출
                    file_name = None
                    from urllib.parse import urlparse, parse_qs, unquote
                    
                    try:
                        # URL 파싱
                        parsed_url = urlparse(href)
                        query_params = parse_qs(parsed_url.query)
                        
                        # fileNm 파라미터 추출
                        if 'fileNm' in query_params:
                            file_name = query_params['fileNm'][0]
                            # URL 디코딩 (한글 등이 인코딩되어 있을 수 있음)
                            file_name = unquote(file_name)
                        else:
                            # fileNm이 없으면 href에서 직접 추출 시도
                            if 'fileNm=' in href:
                                file_nm_part = href.split('fileNm=')[1]
                                # & 또는 &amp; 또는 끝까지
                                if '&' in file_nm_part:
                                    file_name = file_nm_part.split('&')[0]
                                elif '&amp;' in file_nm_part:
                                    file_name = file_nm_part.split('&amp;')[0]
                                else:
                                    file_name = file_nm_part
                                file_name = unquote(file_name)
                    except Exception as e:
                        print(f"  ⚠ 파일명 추출 중 오류: {e}")
                    
                    # 파일명을 찾지 못한 경우 fallback
                    if not file_name:
                        # span 텍스트는 "첨부파일 있습니다"이므로 사용하지 않음
                        # href에서 파일 확장자로 파일명 추정
                        if '.pdf' in href.lower():
                            file_name = "파일.pdf"
                        elif '.hwp' in href.lower():
                            file_name = "파일.hwp"
                        else:
                            file_name = "파일"
                    
                    detail_info["download_links"].append(file_url)
                    detail_info["file_names"].append(file_name)
                    print(f"  ✓ 첨부파일 발견: {file_name}")
                    print(f"    링크: {file_url}")
                    
                    # 파일 다운로드 및 비교
                    downloaded_file_path = self._download_and_compare_file(file_url, file_name, regulation_name=regulation_name)
                    
                    # PDF 파일이면 내용 추출
                    if downloaded_file_path and downloaded_file_path.get('file_path'):
                        file_path = downloaded_file_path['file_path']
                        if file_path.lower().endswith('.pdf'):
                            print(f"  PDF 내용 추출 중...")
                            pdf_content = self.file_extractor.extract_pdf_content(file_path)
                            if pdf_content:
                                detail_info["content"] = pdf_content
                                print(f"  ✓ PDF에서 {len(pdf_content)}자 추출 완료")
                                
                                # PDF에서 소관부서와 제정일 추출
                                extracted_info = self._extract_info_from_pdf_content(pdf_content)
                                if extracted_info.get("department"):
                                    detail_info["department"] = extracted_info["department"]
                                    print(f"  ✓ 소관부서: {extracted_info['department']}")
                                if extracted_info.get("enactment_date"):
                                    detail_info["enactment_date"] = extracted_info["enactment_date"]
                                    print(f"  ✓ 제정일: {extracted_info['enactment_date']}")
                            else:
                                print(f"  ⚠ PDF 내용 추출 실패")
            else:
                print(f"  ⚠ 파일 링크를 찾지 못했습니다 (셀렉터: {file_selector})")
            
            # 최근개정일 추출: #main-container > div.content > div.bdView > div > div > table > tbody > tr:nth-child(1) > td:nth-child(1) > a
            date_selector = "#main-container > div.content > div.bdView > div > div > table > tbody > tr:nth-child(1) > td:nth-child(1) > a"
            date_elem = soup.select_one(date_selector)
            
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                if date_text:
                    detail_info["revision_date"] = date_text
                    print(f"  ✓ 최근개정일: {date_text}")
            else:
                print(f"  ⚠ 최근개정일을 찾지 못했습니다 (셀렉터: {date_selector})")
            
        except Exception as e:
            print(f"  ⚠ 상세 페이지 추출 실패: {e}")
            import traceback
            traceback.print_exc()
        
        return detail_info
    
    def _extract_info_from_pdf_content(self, content: str) -> Dict[str, str]:
        """PDF 내용에서 소관부서와 제정일 추출"""
        result = {
            "department": "",
            "enactment_date": "",
        }
        
        if not content:
            return result
        
        # 제정일 패턴 찾기 (YYYY년 MM월 DD일 또는 YYYY-MM-DD 형식)
        # 예: "2023년 1월 12일", "2023-01-12", "제정일: 2023.01.12"
        date_patterns = [
            r'제정일[:\s]*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
            r'제정일[:\s]*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',
            r'제정일[:\s]*(\d{4})-(\d{1,2})-(\d{1,2})',
            r'제정[:\s]*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
            r'제정[:\s]*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})',
            r'제정[:\s]*(\d{4})-(\d{1,2})-(\d{1,2})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content)
            if match:
                year, month, day = match.groups()
                # YYYY-MM-DD 형식으로 변환
                result["enactment_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                break
        
        # 소관부서 패턴 찾기 (마지막 개정일 부분에서 추출)
        # 예: "개정 2025. 6. 24. 국장결재 국제총괄팀- 793"
        # 예: "개정2023.12.20.총재결재 외환정보팀-1028"
        # 패턴: 개정 + 날짜 + 결재 + 팀명 + "-" + 숫자
        department_patterns = [
            r'개정\s*\d{4}\.?\s*\d{1,2}\.?\s*\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)\s*-',  # 공백 포함
            r'개정\s*\d{4}\.?\s*\d{1,2}\.?\s*\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)-',  # 공백 없음
            r'개정\d{4}\.?\d{1,2}\.?\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)\s*-',  # 공백 없음 (날짜 부분)
            r'개정\d{4}\.?\d{1,2}\.?\d{1,2}\.?\s*[가-힣]*결재\s+([가-힣]+팀)-',  # 공백 없음 (전체)
        ]
        
        # 모든 개정일 패턴을 찾아서 마지막 것을 사용
        all_matches = []
        for pattern in department_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                team_name = match.group(1).strip()
                if team_name:
                    all_matches.append((match.start(), team_name))
        
        # 마지막 개정일에서 추출한 팀명 사용
        if all_matches:
            # 위치 기준으로 정렬하여 마지막 것 선택
            all_matches.sort(key=lambda x: x[0])
            result["department"] = all_matches[-1][1]
        
        return result
    
    def _get_safe_filename(self, filename: str, regulation_name: str = "") -> str:
        """
        파일명을 안전한 형식으로 변환 (경로에 사용 가능한 문자만)
        
        Args:
            filename: 원본 파일명
            regulation_name: 규정명 (파일명 생성용)
            
        Returns:
            안전한 파일명
        """
        import re
        # 규정명이 있으면 규정명 기반으로 파일명 생성
        if regulation_name:
            # 규정명에서 안전한 문자만 추출
            safe_reg_name = re.sub(r'[^\w\s-]', '', regulation_name)
            safe_reg_name = safe_reg_name.replace(' ', '_')
            # 파일 확장자 추출
            ext = Path(filename).suffix if filename else '.pdf'
            return f"{safe_reg_name}{ext}"
        else:
            # 원본 파일명에서 안전한 문자만 추출
            safe_name = re.sub(r'[^\w\s.-]', '', filename)
            return safe_name.replace(' ', '_')
    
    def _download_and_compare_file(self, file_url: str, file_name: str, regulation_name: str = "") -> Optional[Dict]:
        """
        파일 다운로드 및 이전 파일과 비교
        
        Args:
            file_url: 다운로드 URL
            file_name: 파일명
            regulation_name: 규정명 (이전 파일 매칭용)
            
        Returns:
            비교 결과 딕셔너리 또는 None
        """
        try:
            # 안전한 파일명 생성
            safe_filename = self._get_safe_filename(file_name, regulation_name)
            
            # 새 파일 다운로드 경로
            new_file_path = os.path.join(self.download_dir, safe_filename)
            
            # 이전 파일 경로 (규정명 기반으로 찾기)
            previous_file_path = os.path.join(self.previous_dir, safe_filename)
            
            # 파일 다운로드
            print(f"  파일 다운로드 중: {file_name}")
            # FileExtractor.download_file는 (filepath, actual_filename) 튜플 반환
            downloaded_result = self.file_extractor.download_file(
                file_url,
                safe_filename,
                use_selenium=False,  # requests로 다운로드
                driver=None
            )
            
            # 튜플 언패킹
            if downloaded_result:
                downloaded_path, actual_filename = downloaded_result
            else:
                downloaded_path, actual_filename = None, None
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                print(f"  ⚠ 파일 다운로드 실패")
                return None
            
            # 다운로드한 파일을 새 파일 경로로 이동/복사
            if downloaded_path != new_file_path:
                import shutil
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)  # 기존 파일 삭제
                shutil.move(downloaded_path, new_file_path)
                print(f"  ✓ 파일 저장: {new_file_path}")
            
            # 이전 파일과 비교
            comparison_result = None
            if os.path.exists(previous_file_path):
                print(f"  이전 파일과 비교 중...")
                comparison_result = self.file_comparator.compare_and_report(
                    new_file_path,
                    previous_file_path,
                    save_diff=True
                )
                
                if comparison_result['changed']:
                    print(f"  ✓ 파일 변경 감지: {comparison_result['diff_summary']}")
                    if 'diff_file' in comparison_result:
                        print(f"    Diff 파일: {comparison_result['diff_file']}")
                else:
                    print(f"  ✓ 파일 동일 (변경 없음)")
                
                # 이전 파일을 새 파일로 교체 (다음 비교를 위해)
                import shutil
                shutil.copy2(new_file_path, previous_file_path)
                print(f"  ✓ 이전 파일 업데이트 완료")
            else:
                print(f"  ✓ 새 파일 (이전 파일 없음)")
                # 이전 파일 디렉토리에 복사 (다음 비교를 위해)
                import shutil
                os.makedirs(self.previous_dir, exist_ok=True)
                shutil.copy2(new_file_path, previous_file_path)
                print(f"  ✓ 이전 파일로 저장 완료")
            
            return {
                'file_path': new_file_path,
                'previous_file_path': previous_file_path if os.path.exists(previous_file_path) else None,
                'comparison': comparison_result,
            }
            
        except Exception as e:
            print(f"  ⚠ 파일 다운로드/비교 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def crawl_regulations(self) -> List[Dict]:
        """
        법규정보 - 규정 스크래핑
        CSV 목록 기반으로 각 규정명을 검색어로 사용하여 수집
        """
        print(f"\n=== 한국은행 법규 스크래핑 시작 ===")
        if not self.target_laws:
            print("⚠ CSV 목록이 없습니다.")
            return []
        
        print(f"대상 규정: {len(self.target_laws)}개")
        for i, target in enumerate(self.target_laws, 1):
            print(f"  {i}. {target['law_name']}")
        print()
        
        results = []
        
        try:
            # 각 규정명을 검색어로 사용하여 검색 및 추출
            for idx, target in enumerate(self.target_laws, 1):
                regulation_name = target["law_name"]
                print(f"\n[{idx}/{len(self.target_laws)}] {regulation_name}")
                
                # 검색어를 URL 인코딩
                search_text_encoded = quote(regulation_name)
                search_url = self.SEARCH_URL_TEMPLATE.format(search_text=search_text_encoded)
                
                print(f"  검색 URL: {search_url}")
                
                # 검색 결과 페이지 접근
                soup = self.fetch_page(search_url, use_selenium=True)
                
                # 디버깅 HTML 저장 (첫 번째 검색만)
                if idx == 1:
                    self.save_debug_html(soup, filename="debug_bok_search.html")
                
                # 검색 결과에서 규정 목록 추출
                regulation_list = self.extract_regulation_list(soup)
                
                if not regulation_list:
                    print(f"  ⚠ 검색 결과에서 규정을 찾지 못했습니다.")
                    # 빈 항목으로 추가 (나중에 save_bok_results에서 처리)
                    empty_item = {
                        "title": regulation_name,
                        "regulation_name": regulation_name,
                        "organization": "한국은행",
                        "target_name": regulation_name,
                        "target_category": target.get("category", ""),
                        "detail_link": "",
                        "content": "",
                        "department": "",
                        "file_names": [],
                        "download_links": [],
                        "enactment_date": "",
                        "revision_date": "",
                    }
                    results.append(empty_item)
                    continue
                
                # 검색 결과에서 정확히 일치하는 규정 찾기
                matched_regulation = None
                for reg in regulation_list:
                    reg_name = reg.get("regulation_name") or reg.get("title", "")
                    if self._normalize_title(reg_name) == self._normalize_title(regulation_name):
                        matched_regulation = reg
                        break
                
                # 정확히 일치하는 것이 없으면 첫 번째 결과 사용
                if not matched_regulation and regulation_list:
                    matched_regulation = regulation_list[0]
                    print(f"  ⚠ 정확히 일치하는 규정을 찾지 못해 첫 번째 결과 사용: {matched_regulation.get('title', '')}")
                
                if matched_regulation:
                    matched_regulation["target_name"] = regulation_name
                    matched_regulation["target_category"] = target.get("category", "")
                    if target.get("law_name"):
                        matched_regulation["regulation_name"] = target["law_name"]
                    
                    # 상세 정보 추출
                    detail_link = matched_regulation.get("detail_link", "")
                    if detail_link:
                        print(f"  상세 페이지 접근: {detail_link}")
                        detail_info = self.extract_regulation_detail(detail_link, regulation_name=regulation_name)
                        matched_regulation.update(detail_info)
                    else:
                        print(f"  ⚠ 상세 링크가 없습니다.")
                    
                    results.append(matched_regulation)
                else:
                    print(f"  ⚠ 검색 결과에서 규정을 찾지 못했습니다.")
                    # 빈 항목으로 추가
                    empty_item = {
                        "title": regulation_name,
                        "regulation_name": regulation_name,
                        "organization": "한국은행",
                        "target_name": regulation_name,
                        "target_category": target.get("category", ""),
                        "detail_link": "",
                        "content": "",
                        "department": "",
                        "file_names": [],
                        "download_links": [],
                        "enactment_date": "",
                        "revision_date": "",
                    }
                    results.append(empty_item)
                
                time.sleep(self.delay)
            
        except Exception as e:
            print(f"✗ 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def _filter_regulations_by_targets(self, regulation_list: List[Dict]) -> List[Dict]:
        """CSV 목록에 포함된 규정만 순서대로 반환한다."""
        if not self.target_laws:
            return regulation_list

        normalized_tree: Dict[str, List[Dict]] = {}
        for reg in regulation_list:
            reg_name = reg.get("regulation_name") or reg.get("title", "")
            key = self._normalize_title(reg_name)
            if not key:
                continue
            normalized_tree.setdefault(key, []).append(reg)

        selected_regulations: List[Dict] = []
        missing_targets: List[str] = []

        for target in self.target_laws:
            target_name = target["law_name"]
            key = self._normalize_title(target_name)
            matches = normalized_tree.get(key)
            if matches and len(matches) > 0:
                # 같은 이름의 규정이 여러 개 있을 수 있으므로 첫 번째 사용
                reg = dict(matches[0])  # 딕셔너리 복사
                reg["target_name"] = target_name
                reg["target_category"] = target.get("category", "")
                if target.get("law_name"):
                    reg["regulation_name"] = target["law_name"]
                selected_regulations.append(reg)
            else:
                missing_targets.append(target_name)

        if missing_targets:
            print(f"  ⚠ CSV에 있으나 목록에서 찾지 못한 규정: {len(missing_targets)}개")
            for name in missing_targets[:5]:
                print(f"     - {name}")
            if len(missing_targets) > 5:
                print("     ...")
            print(f"     (찾지 못한 항목은 결과에 빈 내용으로 포함됩니다)")

        return selected_regulations


def save_bok_results(records: List[Dict], crawler: Optional[BokScraper] = None):
    """JSON 및 CSV로 한국은행 법규 데이터를 저장한다.
    
    Args:
        records: 스크래핑된 법규정보 리스트
        crawler: BokScraper 인스턴스 (CSV의 모든 항목을 포함하기 위해 사용)
    """
    # CSV의 모든 항목을 포함하도록 정렬 (CSV 순서 유지)
    if crawler and crawler.target_laws:
        # CSV 항목 순서대로 정렬하기 위한 딕셔너리 생성
        records_dict = {}
        for item in records:
            reg_name = item.get("target_name") or item.get("regulation_name") or item.get("title", "")
            if reg_name:
                records_dict[reg_name] = item
        
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
                    "organization": "한국은행",
                    "target_name": target_name,
                    "target_category": target.get("category", ""),
                    "content": "",  # 빈 본문
                    "department": "",
                    "file_names": [],
                    "download_links": [],
                    "enactment_date": "",
                    "revision_date": "",
                }
                ordered_records.append(empty_item)
                print(f"디버깅: 찾지 못한 항목 추가 - {target_name}")
        
        if missing_count > 0:
            print(f"디버깅: 총 {missing_count}개 항목을 빈 본문으로 추가했습니다.")
        
        records = ordered_records
    
    if not records:
        print("저장할 법규 데이터가 없습니다.")
        return
    
    # 출력 디렉토리 생성
    json_dir = os.path.join("output", "json")
    csv_dir = os.path.join("output", "csv")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)
    
    # 법규 정보 데이터 정리 (CSV와 동일한 한글 필드명으로 정리)
    law_results = []
    for idx, item in enumerate(records, 1):
        # 여러 첨부파일을 세미콜론으로 구분
        file_names_str = "; ".join(item.get("file_names", [])) if item.get("file_names") else ""
        download_links_str = "; ".join(item.get("download_links", [])) if item.get("download_links") else ""
        
        law_item = {
            "번호": str(idx),  # 순번으로 번호 생성
            "규정명": item.get("regulation_name", item.get("title", "")),
            "기관명": item.get("organization", "한국은행"),
            "본문": (item.get("content", "") or "").replace("\n", " ").replace("\r", " "),
            "제정일": item.get("enactment_date", ""),
            "최근 개정일": item.get("revision_date", ""),
            "소관부서": item.get("department", ""),
            "파일 다운로드 링크": download_links_str,
            "파일 이름": file_names_str,
        }
        law_results.append(law_item)
    
    # JSON 저장 (한글 필드명으로)
    json_path = os.path.join(json_dir, "bok_scraper.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": BokScraper.SEARCH_URL_TEMPLATE,
                "total_count": len(law_results),
                "results": law_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n✓ JSON 저장 완료: {json_path}")
    
    # CSV 저장 (정리된 law_results 사용)
    csv_headers = [
        "번호",
        "규정명",
        "기관명",
        "본문",
        "제정일",
        "최근 개정일",
        "소관부서",
        "파일 다운로드 링크",
        "파일 이름",
    ]
    csv_path = os.path.join(csv_dir, "bok_scraper.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for law_item in law_results:
            writer.writerow(law_item)
    print(f"✓ CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="한국은행 법규정보 스크래퍼 (CSV 목록 기반)")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체)")
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="대상 규정 목록 CSV 경로 (기본: BOK_Scraper/input/list.csv)",
    )
    args = parser.parse_args()
    
    scraper = BokScraper(csv_path=args.csv)
    results = scraper.crawl_regulations()
    
    print(f"\n총 {len(results)}개의 법규정보를 수집했습니다.")
    save_bok_results(results, crawler=scraper)

