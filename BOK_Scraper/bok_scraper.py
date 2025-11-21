"""
한국은행 스크래퍼
특정 법규 항목만 스크래핑: 전자방식 외상매출채권담보대출 관련 규정
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
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from common.base_scraper import BaseScraper
from common.file_extractor import FileExtractor
from common.file_comparator import FileComparator


class BokScraper(BaseScraper):
    """한국은행 스크래퍼 - 전자방식 외상매출채권담보대출 관련 규정만 수집"""
    
    BASE_URL = "https://www.bok.or.kr"
    # 검색어가 포함된 URL 사용 (금융기관 전자방식으로 검색하면 대상 규정 2개만 나옴)
    LIST_URL = "https://www.bok.or.kr/portal/singl/law/listSearch.do?menuNo=200200&parentlawseq=&detaillawseq=&lawseq=&search_text=%EA%B8%88%EC%9C%B5%EA%B8%B0%EA%B4%80+%EC%A0%84%EC%9E%90%EB%B0%A9%EC%8B%9D"
    
    # 스크래핑할 대상 규정명 (정확히 일치하거나 포함되는 항목)
    TARGET_REGULATIONS = [
        "금융기관 전자방식 외상매출채권담보대출 취급절차",
        "금융기관 전자방식 외상매출채권담보대출 취급세칙",
    ]
    
    def __init__(self, delay: float = 1.0):
        super().__init__(delay)
        self.download_dir = os.path.join("output", "downloads")
        self.previous_dir = os.path.join("output", "downloads", "previous", "bok")
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.previous_dir, exist_ok=True)
        # FileExtractor 초기화 (session 전달)
        self.file_extractor = FileExtractor(download_dir=self.download_dir, session=self.session)
        # 파일 비교기 초기화
        self.file_comparator = FileComparator(base_dir=self.download_dir)
    
    def is_target_regulation(self, title: str) -> bool:
        """제목이 대상 규정인지 확인"""
        if not title:
            return False
        
        title_clean = title.strip()
        for target in self.TARGET_REGULATIONS:
            if target in title_clean or title_clean in target:
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
                
                # 대상 규정인지 확인
                if not self.is_target_regulation(title):
                    continue
                
                print(f"  ✓ 대상 규정 발견: {title}")
                
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
            "content": "",  # 본문 내용은 비워둠
            "file_names": [],
            "download_links": [],
            "revision_date": "",
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
                    self._download_and_compare_file(file_url, file_name, regulation_name=regulation_name)
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
                'comparison': comparison_result if os.path.exists(previous_file_path) else None,
            }
            
        except Exception as e:
            print(f"  ⚠ 파일 다운로드/비교 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def crawl_regulations(self) -> List[Dict]:
        """
        법규정보 - 규정 스크래핑
        대상 규정만 필터링하여 수집
        """
        print(f"\n=== 한국은행 법규 스크래핑 시작 ===")
        print(f"대상 규정: {len(self.TARGET_REGULATIONS)}개")
        for i, reg in enumerate(self.TARGET_REGULATIONS, 1):
            print(f"  {i}. {reg}")
        print()
        
        results = []
        
        try:
            # 목록 페이지 접근
            print(f"[1단계] 목록 페이지 접근: {self.LIST_URL}")
            soup = self.fetch_page(self.LIST_URL, use_selenium=True)
            
            # 디버깅 HTML 저장
            self.save_debug_html(soup, filename="debug_bok_list.html")
            
            # 대상 규정 목록 추출
            print(f"[2단계] 대상 규정 목록 추출 중...")
            regulation_list = self.extract_regulation_list(soup)
            
            if not regulation_list:
                print("  ⚠ 대상 규정을 찾지 못했습니다.")
                return results
            
            print(f"  ✓ {len(regulation_list)}개 규정 발견")
            
            # 각 규정의 상세 정보 추출
            print(f"[3단계] 상세 정보 추출 중...")
            for idx, regulation in enumerate(regulation_list, 1):
                title = regulation.get("title", "")
                detail_link = regulation.get("detail_link", "")
                
                print(f"\n[{idx}/{len(regulation_list)}] {title}")
                
                if detail_link:
                    print(f"  상세 페이지 접근: {detail_link}")
                    regulation_name = regulation.get("regulation_name", regulation.get("title", ""))
                    detail_info = self.extract_regulation_detail(detail_link, regulation_name=regulation_name)
                    regulation.update(detail_info)
                    
                    # 첨부파일 정보는 이미 detail_info에 포함되어 있음
                    # 본문 내용은 비워두므로 파일 다운로드 및 추출은 생략
                else:
                    print(f"  ⚠ 상세 링크가 없습니다.")
                
                results.append(regulation)
                time.sleep(self.delay)
            
        except Exception as e:
            print(f"✗ 스크래핑 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        
        return results


def save_bok_results(records: List[Dict]):
    """JSON 및 CSV로 한국은행 법규 데이터를 저장한다."""
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
    json_path = os.path.join(json_dir, "bok_regulations.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": BokScraper.LIST_URL,
                "total_count": len(law_results),
                "target_regulations": BokScraper.TARGET_REGULATIONS,
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
    csv_path = os.path.join(csv_dir, "bok_regulations.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for law_item in law_results:
            writer.writerow(law_item)
    print(f"✓ CSV 저장 완료: {csv_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="한국은행 법규정보 스크래퍼 (전자방식 외상매출채권담보대출 관련 규정)")
    parser.add_argument("--limit", type=int, default=0, help="가져올 개수 제한 (0=전체, 기본값: 대상 규정만)")
    args = parser.parse_args()
    
    scraper = BokScraper()
    results = scraper.crawl_regulations()
    
    print(f"\n총 {len(results)}개의 법규정보를 수집했습니다.")
    save_bok_results(results)

