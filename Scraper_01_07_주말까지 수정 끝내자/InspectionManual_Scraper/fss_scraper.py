import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fss.or.kr"
LIST_PATH = "/fss/bbs/B0000167/list.do"
DETAIL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
}
DEFAULT_TIMEOUT = 30
SLEEP_SECONDS = 0.3

# 스크랩 대상 리스트
SCRAPE_TARGETS = [
    "은행 검사매뉴얼",
    "여신전문금융 검사업무 안내서",
    "금융투자 검사업무 안내서",
    "저축은행 검사업무 안내서",
    "신용정보업 검사업무 안내서",
    "IT 검사업무 안내서",
    "금융소비자보호법 검사업무 안내서",
    "자금세탁방지 검사업무 안내서",
    "퇴직연금 검사매뉴얼"
]


class ScraperError(Exception):
    """스크레이퍼 전용 예외."""


def fetch_soup(session: requests.Session, url: str, *, params: Optional[Dict[str, str]] = None) -> BeautifulSoup:
    """지정한 URL을 요청하고 BeautifulSoup 객체로 반환."""
    try:
        response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT, headers=DETAIL_HEADERS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScraperError(f"요청 실패: {url} | {exc}") from exc

    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "lxml")


def extract_category_from_title(title: str) -> str:
    """제목의 첫 단어를 구분으로 추출"""
    if not title:
        return ""
    # 공백으로 분리하여 첫 단어 추출
    first_word = title.split()[0] if title.split() else ""
    return first_word


def normalize_title_for_matching(title: str) -> str:
    """제목 매칭을 위한 정규화 (공백 제거, 소문자 변환)"""
    if not title:
        return ""
    return re.sub(r"\s+", "", title).lower()


def is_target_item(title: str) -> bool:
    """제목이 스크랩 대상인지 확인"""
    if not title:
        return False
    normalized_title = normalize_title_for_matching(title)
    for target in SCRAPE_TARGETS:
        normalized_target = normalize_title_for_matching(target)
        # 대상이 제목에 포함되거나 제목이 대상에 포함되는지 확인
        if normalized_target in normalized_title or normalized_title in normalized_target:
            return True
    return False


def parse_bd_list(bd_list) -> List[Dict[str, str]]:
    """bd-list에서 title을 추출하여 게시글 정보 파싱"""
    rows: List[Dict[str, str]] = []
    
    # bd-list 내부의 각 항목 찾기 (li, div, tr 등 다양한 구조 지원)
    items = bd_list.find_all(["li", "div", "tr"], recursive=True)
    
    for item in items:
        # title 찾기 (class에 title이 포함된 요소 또는 a 태그)
        title_elem = item.find(class_=re.compile(r"title", re.I))
        if not title_elem:
            title_elem = item.find("a")
        
        if not title_elem:
            continue
        
        title = title_elem.get_text(strip=True)
        if not title:
            continue
        
        # 링크 찾기
        link_elem = title_elem if title_elem.name == "a" else title_elem.find("a")
        if not link_elem or not link_elem.get("href"):
            continue
        
        detail_url = urljoin(BASE_URL, link_elem["href"])
        
        # 구분은 제목의 첫 단어로 추출
        category = extract_category_from_title(title)
        
        # 등록일, 담당부서 등 추가 정보 찾기
        reg_date = ""
        dept = ""
        views = ""
        number = ""
        
        # 등록일 찾기
        date_elem = item.find(class_=re.compile(r"date|등록일", re.I))
        if date_elem:
            reg_date = date_elem.get_text(strip=True)
        else:
            # td나 다른 요소에서 등록일 찾기 시도
            # span.only-m이 포함된 td 찾기
            for td in item.find_all("td"):
                span = td.find("span", class_=re.compile(r"only-m|등록일", re.I))
                if span and "등록일" in span.get_text():
                    # 정규식으로 날짜 패턴 추출 (YYYY-MM-DD, YYYY.MM.DD 등)
                    date_pattern = re.search(r'(\d{4}[-.]\d{1,2}[-.]\d{1,2})', td.get_text())
                    if date_pattern:
                        reg_date = date_pattern.group(1).replace(".", "-")
                    else:
                        # span을 제거하고 텍스트만 가져오기
                        text = td.get_text(strip=True)
                        reg_date = re.sub(r'등록일\s*', '', text).strip()
                    break
        
        # 담당부서 찾기
        dept_elem = item.find(class_=re.compile(r"dept|부서", re.I))
        if dept_elem:
            dept = dept_elem.get_text(strip=True)
        
        # 조회수 찾기
        views_elem = item.find(class_=re.compile(r"view|조회", re.I))
        if views_elem:
            views = views_elem.get_text(strip=True)
        
        # nttId 추출
        parsed = urlparse(detail_url)
        query = parse_qs(parsed.query)
        ntt_id = query.get("nttId", [""])[0]
        
        rows.append({
            "번호": number,
            "구분": category,
            "제목": title,
            "담당부서": dept,
            "등록일": reg_date,
            "조회수": views,
            "상세페이지URL": detail_url,
            "nttId": ntt_id,
        })
    
    return rows


def parse_list_row(tr) -> Optional[Dict[str, str]]:
    tds = tr.find_all("td")
    if not tds:
        return None

    number = tds[0].get_text(strip=True)

    title_td = tds[2]
    title_link = title_td.find("a")
    if title_link is None or not title_link.get("href"):
        return None
    title = title_link.get_text(strip=True)
    detail_url = urljoin(BASE_URL, title_link["href"])

    # 구분은 제목의 첫 단어로 추출
    category = extract_category_from_title(title)

    dept = tds[3].get_text(strip=True)
    
    # 등록일 추출: 5번째 td (인덱스 4)에서 span 태그 안의 날짜 추출
    reg_date_td = tds[4] if len(tds) > 4 else None
    reg_date = ""
    if reg_date_td:
        # span 태그 찾기
        span = reg_date_td.find("span")
        if span:
            # span의 텍스트를 제외한 나머지 텍스트 가져오기 (날짜 부분)
            # span을 제거한 후 텍스트 추출
            span_text = span.get_text(strip=True)
            full_text = reg_date_td.get_text(strip=True)
            # span 텍스트("등록일")를 제거
            reg_date = full_text.replace(span_text, "").strip()
        else:
            # span이 없으면 정규식으로 날짜 패턴 추출
            date_pattern = re.search(r'(\d{4}[-.]\d{1,2}[-.]\d{1,2})', reg_date_td.get_text())
            if date_pattern:
                reg_date = date_pattern.group(1).replace(".", "-")
            else:
                # 전체 텍스트에서 "등록일" 제거
                text = reg_date_td.get_text(strip=True)
                reg_date = re.sub(r'등록일\s*', '', text).strip()
    
    views = tds[6].get_text(strip=True) if len(tds) > 6 else ""

    parsed = urlparse(detail_url)
    query = parse_qs(parsed.query)
    ntt_id = query.get("nttId", [""])[0]

    return {
        "번호": number,
        "구분": category,
        "제목": title,
        "담당부서": dept,
        "등록일": reg_date,
        "조회수": views,
        "상세페이지URL": detail_url,
        "nttId": ntt_id,
    }


def parse_date(date_str: str) -> Optional[tuple]:
    """등록일 문자열을 (년, 월, 일) 튜플로 변환 (비교용)"""
    if not date_str or date_str == "-":
        return None
    # "2024.01.15" 형식 가정
    try:
        parts = date_str.replace(".", "-").split("-")
        if len(parts) == 3:
            year, month, day = map(int, parts)
            return (year, month, day)
    except (ValueError, AttributeError):
        pass
    return None


def extract_date_from_title(title: str) -> Optional[tuple]:
    """
    제목에서 날짜를 추출하여 (년, 월) 튜플로 반환
    
    예: "대부업 검사업무 안내서('25.7월)" -> (2025, 7)
         "은행 검사매뉴얼('23.4월)" -> (2023, 4)
         "자금세탁방지 검사업무 안내서('25년 6월)" -> (2025, 6)
    """
    if not title:
        return None
    
    # 패턴: '25.7월, 25.7월, 2025.7월, '25년 6월, 25년 6월 등
    patterns = [
        r"'?(\d{2,4})\s*년\s*(\d{1,2})\s*월",  # '25년 6월, 25년 6월, 2025년 6월 (우선순위 높음)
        r"'?(\d{2,4})\.(\d{1,2})월",  # '25.7월, 2025.7월
        r"'?(\d{2,4})\s*\.\s*(\d{1,2})\s*월",  # 공백 포함
        r"'?(\d{2,4})-(\d{1,2})월",  # 하이픈 사용
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            try:
                year_str = match.group(1)
                month = int(match.group(2))
                
                # 2자리 연도를 4자리로 변환
                if len(year_str) == 2:
                    year_int = int(year_str)
                    # 50 이상이면 1900년대, 미만이면 2000년대
                    if year_int >= 50:
                        year = 1900 + year_int
                    else:
                        year = 2000 + year_int
                else:
                    year = int(year_str)
                
                return (year, month)
            except (ValueError, IndexError):
                continue
    
    return None


def scrape_all(
    session: requests.Session,
    limit: Optional[int] = None,
    *,
    output_dir: Optional[Path] = None,
) -> List[Dict[str, str]]:
    # 모든 게시글을 먼저 수집
    all_posts: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    page = 1

    def log(message: str) -> None:
        print(message, flush=True)

    log(f"[정보] 모든 게시글 수집 시작 (대상: {len(SCRAPE_TARGETS)}개)")
    
    # 1단계: 모든 게시글 수집
    while True:
        params = {"menuNo": "200177", "pageIndex": str(page)}
        try:
            soup = fetch_soup(session, urljoin(BASE_URL, LIST_PATH), params=params)
        except ScraperError as exc:
            log(f"[경고] 목록 페이지 요청 실패: {exc}")
            break

        # bd-list에서 항목 찾기 (테이블일 수도 있고, 내부에 테이블이 있을 수도 있음)
        bd_list = soup.select_one(".bd-list, [class*='bd-list'], div.bd-list, table.bd-list")
        if not bd_list:
            # bd-list가 없으면 기존 방식(테이블) 시도
            table = soup.find("table")
            if not table:
                log(f"[정보] 목록 테이블이 없습니다 (page={page}).")
                break
            body = table.find("tbody")
            if not body:
                log(f"[정보] tbody가 없습니다 (page={page}).")
                break
            rows = [parse_list_row(tr) for tr in body.find_all("tr")]
        else:
            # bd-list가 테이블인 경우
            if bd_list.name == "table":
                body = bd_list.find("tbody")
                if body:
                    rows = [parse_list_row(tr) for tr in body.find_all("tr")]
                else:
                    rows = []
            else:
                # bd-list 내부에 테이블이 있는지 확인
                inner_table = bd_list.find("table")
                if inner_table:
                    body = inner_table.find("tbody")
                    if body:
                        rows = [parse_list_row(tr) for tr in body.find_all("tr")]
                    else:
                        rows = []
                else:
                    # bd-list에서 title 추출 (div, ul 등)
                    rows = parse_bd_list(bd_list)
        
        rows = [row for row in rows if row]
        if not rows:
            log(f"[정보] 더 이상 데이터가 없습니다 (page={page}).")
            break

        for row in rows:
            ntt_id = row.get("nttId")
            if ntt_id and ntt_id in seen_ids:
                continue
            seen_ids.add(ntt_id)
            all_posts.append(row)

        log(f"[정보] {page}페이지 수집 완료 - 총 {len(all_posts)}개 게시글")
        page += 1
        time.sleep(SLEEP_SECONDS)

    log(f"[정보] 전체 게시글 수집 완료: {len(all_posts)}개")
    
    # 2단계: 대상에 맞는 게시글 필터링
    target_posts: List[Dict[str, str]] = []
    for post in all_posts:
        title = post.get("제목", "")
        if is_target_item(title):
            target_posts.append(post)
    
    log(f"[정보] 대상 게시글 필터링 완료: {len(target_posts)}개")
    
    # 3단계: 각 대상별로 최신 데이터만 선택
    # 대상별로 그룹화
    target_groups: Dict[str, List[Dict[str, str]]] = {}
    for post in target_posts:
        title = post.get("제목", "")
        # 어떤 대상에 해당하는지 찾기
        matched_target = None
        normalized_title = normalize_title_for_matching(title)
        for target in SCRAPE_TARGETS:
            normalized_target = normalize_title_for_matching(target)
            if normalized_target in normalized_title or normalized_title in normalized_target:
                matched_target = target
                break
        
        if matched_target:
            if matched_target not in target_groups:
                target_groups[matched_target] = []
            target_groups[matched_target].append(post)
    
    # 각 대상별로 최신 데이터 1건만 선택
    selected_posts: List[Dict[str, str]] = []
    for target, posts in target_groups.items():
        # 제목에서 날짜 추출하여 정렬 (최신순)
        posts_with_title_date = []
        for post in posts:
            title = post.get("제목", "")
            title_date = extract_date_from_title(title)
            # 제목 날짜가 없으면 등록일 사용
            if not title_date:
                reg_date = post.get("등록일", "")
                date_tuple = parse_date(reg_date)
                if date_tuple:
                    # 등록일을 (년, 월) 형식으로 변환 (비교용)
                    title_date = (date_tuple[0], date_tuple[1])
            
            posts_with_title_date.append((title_date, post))
        
        # 날짜가 있는 것만 정렬, 날짜가 없으면 맨 뒤로
        posts_with_title_date.sort(key=lambda x: x[0] if x[0] else (0, 0), reverse=True)
        
        # 최신 날짜의 첫 번째 게시글 1개만 선택
        if posts_with_title_date and posts_with_title_date[0][0]:
            latest_post = posts_with_title_date[0][1]
            selected_posts.append(latest_post)
        elif posts_with_title_date:
            # 날짜가 없어도 1건은 선택
            latest_post = posts_with_title_date[0][1]
            selected_posts.append(latest_post)
    
    log(f"[정보] 최신 데이터 선택 완료: {len(selected_posts)}개")
    
    # 4단계: 이전 결과 로드
    previous_results = {}
    if output_dir:
        previous_results = load_previous_results(output_dir)
        if previous_results:
            log(f"[정보] 이전 결과 파일에서 {len(previous_results)}개 항목 로드 완료")
    
    # 5단계: 선택된 게시글의 정보 수집 (목록 페이지에서 이미 구분과 제목을 가져왔으므로 상세 페이지 방문 불필요)
    results: List[Dict[str, str]] = []
    for idx, row in enumerate(selected_posts, 1):
        ntt_id = row.get("nttId")
        게시글번호 = row.get("번호", "-")
        구분 = row["구분"] or "-"
        제목 = row["제목"] or "-"
        등록일 = row.get("등록일", "-") or "-"
        
        log(f"[진행] [{idx}/{len(selected_posts)}] 게시글 {게시글번호}번 처리 시작: nttId={ntt_id} | 제목={제목}")
        
        # 갱신 여부 확인
        갱신 = is_updated(구분, 제목, 등록일, previous_results)
        
        # 수집 항목: 구분, 제목, 등록일, 갱신
        record = {
            "구분": 구분,
            "제목": 제목,
            "등록일": 등록일,
            "갱신": 갱신,
        }
        results.append(record)
        
        log(f"[완료] 게시글 {게시글번호}번 수집 완료: nttId={ntt_id} | 갱신={갱신}")
        
        # 각 게시글 완료 후 즉시 파일에 저장
        if output_dir:
            try:
                save_results(results, output_dir)
                log(f"[저장] 게시글 {게시글번호}번 결과 저장 완료 (총 {len(results)}개 레코드)")
            except Exception as exc:
                log(f"[경고] 파일 저장 실패: {exc}")

    return results


def parse_date(date_str: str) -> Optional[tuple]:
    """등록일 문자열을 (년, 월, 일) 튜플로 변환 (비교용)"""
    if not date_str or date_str == "-":
        return None
    # "2024.01.15" 형식 가정
    try:
        parts = date_str.replace(".", "-").split("-")
        if len(parts) == 3:
            year, month, day = map(int, parts)
            return (year, month, day)
    except (ValueError, AttributeError):
        pass
    return None


def extract_date_from_title(title: str) -> Optional[tuple]:
    """
    제목에서 날짜를 추출하여 (년, 월) 튜플로 반환
    
    예: "대부업 검사업무 안내서('25.7월)" -> (2025, 7)
         "은행 검사매뉴얼('23.4월)" -> (2023, 4)
         "자금세탁방지 검사업무 안내서('25년 6월)" -> (2025, 6)
    """
    if not title:
        return None
    
    # 패턴: '25.7월, 25.7월, 2025.7월, '25년 6월, 25년 6월 등
    patterns = [
        r"'?(\d{2,4})\s*년\s*(\d{1,2})\s*월",  # '25년 6월, 25년 6월, 2025년 6월 (우선순위 높음)
        r"'?(\d{2,4})\.(\d{1,2})월",  # '25.7월, 2025.7월
        r"'?(\d{2,4})\s*\.\s*(\d{1,2})\s*월",  # 공백 포함
        r"'?(\d{2,4})-(\d{1,2})월",  # 하이픈 사용
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            try:
                year_str = match.group(1)
                month = int(match.group(2))
                
                # 2자리 연도를 4자리로 변환
                if len(year_str) == 2:
                    year_int = int(year_str)
                    # 50 이상이면 1900년대, 미만이면 2000년대
                    if year_int >= 50:
                        year = 1900 + year_int
                    else:
                        year = 2000 + year_int
                else:
                    year = int(year_str)
                
                return (year, month)
            except (ValueError, IndexError):
                continue
    
    return None


def load_previous_results(output_dir: Path) -> Dict[str, Dict[str, str]]:
    """
    이전 스크랩 결과 파일을 로드하여 구분을 키로 하는 딕셔너리로 반환
    
    Returns:
        {구분: {"제목": "...", "날짜": (년, 월), "등록일": "..."}} 형식의 딕셔너리
    """
    json_path = output_dir / "inspection_results.json"
    previous_results: Dict[str, Dict[str, str]] = {}
    
    if not json_path.exists():
        return previous_results
    
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                구분 = item.get("구분", "")
                제목 = item.get("제목", "")
                등록일 = item.get("등록일", "")
                if 구분:
                    previous_results[구분] = {
                        "제목": 제목,
                        "날짜": extract_date_from_title(제목),
                        "등록일": 등록일,
                    }
    except Exception as exc:
        print(f"[경고] 이전 결과 파일 읽기 실패: {exc}")
    
    return previous_results


def is_updated(구분: str, 제목: str, 등록일: str, previous_results: Dict[str, Dict[str, str]]) -> str:
    """
    현재 항목이 이전 결과보다 업데이트되었는지 확인
    
    Returns:
        "Y" (갱신됨) 또는 "N" (갱신 안됨)
    """
    if 구분 not in previous_results:
        # 이전에 없던 항목이면 갱신
        return "Y"
    
    previous_item = previous_results[구분]
    previous_date = previous_item.get("날짜")
    previous_reg_date = previous_item.get("등록일", "")
    current_date = extract_date_from_title(제목)
    
    # 제목에 날짜가 있으면 날짜 비교
    if current_date:
        # 이전 날짜가 없으면 갱신
        if not previous_date:
            return "Y"
        
        # 현재 날짜가 이전 날짜보다 최신이면 갱신
        if current_date > previous_date:
            return "Y"
        
        # 같은 날짜라도 제목이 다르면 갱신 (같은 날짜에 여러 버전이 있을 수 있음)
        if current_date == previous_date and 제목 != previous_item.get("제목", ""):
            return "Y"
        
        # 같은 날짜, 같은 제목이면 갱신 안됨
        return "N"
    
    # 제목에 날짜가 없으면 등록일로 비교
    if not 등록일 or 등록일 == "-":
        # 등록일도 없으면 제목으로만 비교 (제목이 다르면 갱신)
        if 제목 != previous_item.get("제목", ""):
            return "Y"
        return "N"
    
    # 이전 등록일이 없으면 갱신
    if not previous_reg_date or previous_reg_date == "-":
        return "Y"
    
    # 등록일 파싱하여 비교
    previous_reg_date_tuple = parse_date(previous_reg_date)
    current_reg_date_tuple = parse_date(등록일)
    
    if not current_reg_date_tuple:
        # 등록일 파싱 실패 시 제목으로만 비교
        if 제목 != previous_item.get("제목", ""):
            return "Y"
        return "N"
    
    if not previous_reg_date_tuple:
        return "Y"
    
    # 현재 등록일이 이전 등록일보다 최신이면 갱신
    if current_reg_date_tuple > previous_reg_date_tuple:
        return "Y"
    
    # 같은 등록일이면 제목으로 비교
    if current_reg_date_tuple == previous_reg_date_tuple and 제목 != previous_item.get("제목", ""):
        return "Y"
    
    return "N"


def save_results(results: List[Dict[str, str]], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "inspection_results.json"
    csv_path = output_dir / "inspection_results.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 수집 항목: 구분, 제목, 등록일, 갱신
    fieldnames = ["구분", "제목", "등록일", "갱신"]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            csv_row = {key: row.get(key, "-") for key in fieldnames}
            writer.writerow(csv_row)

    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검사업무 메뉴얼 게시판 스크레이퍼")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="결과 파일을 저장할 경로 (기본값: 현재 디렉터리)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="수집할 게시글 수 제한 (기본값: 제한 없음)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    session = requests.Session()
    results = scrape_all(
        session,
        limit=args.limit,
        output_dir=output_dir,
    )
    print(f"[정보] 총 {len(results)}건 수집 완료")

    json_path, csv_path = save_results(results, output_dir)
    print(f"[정보] JSON 저장: {json_path}")
    print(f"[정보] CSV 저장: {csv_path}")


if __name__ == "__main__":
    main()

