import argparse
import csv
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    import olefile  # type: ignore
except ImportError:  # pragma: no cover
    olefile = None

try:
    from hwp5.hwp5txt import Hwp5File as _Hwp5File, TextTransform as _Hwp5TextTransform  # type: ignore
    from hwp5.hwp5html import HTMLTransform as _HTMLTransform  # type: ignore
    import io
    from contextlib import closing
except Exception:  # pragma: no cover
    _Hwp5File = None
    _Hwp5TextTransform = None
    _HTMLTransform = None
    io = None
    closing = None

import zipfile
import tempfile
import shutil
import zlib

BASE_URL = "https://www.fss.or.kr"
LIST_PATH = "/fss/bbs/B0000167/list.do"
DETAIL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
}
FILE_SIZE_PATTERN = re.compile(r"\((?:파일)?\s*크기\s*[:：]\s*([^)]+)\)")
DETAIL_KEY_MAP = {
    "등록일": "상세등록일",
    "조회수": "상세조회수",
    "담당부서": "상세담당부서",
    "담당팀": "상세담당팀",
    "담당자": "상세담당자",
    "문의": "상세문의",
    "문의이메일": "상세문의이메일",
    "문의 이메일": "상세문의이메일",
}
TABLE_FIELD_NAMES = ["항 목", "점 검 사 항", "점 검 방 식"]
DEFAULT_TIMEOUT = 30
SLEEP_SECONDS = 0.3
SUPPORTED_TEXT_EXTENSIONS = {"pdf", "hwp", "txt"}

HTML_TRANSFORM = _HTMLTransform() if '_HTMLTransform' in globals() and _HTMLTransform else None


# pyhwp 변환 시 불필요한 경고 로그가 과도하게 출력되는 문제 완화
logging.getLogger("hwp5").setLevel(logging.ERROR)


# 중복 첨부파일 재처리를 방지하기 위한 간단한 캐시
AttachmentCache = Dict[str, List[Dict[str, str]]]
_attachment_cache: AttachmentCache = {}


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


def parse_list_row(tr) -> Optional[Dict[str, str]]:
    tds = tr.find_all("td")
    if not tds:
        return None

    number = tds[0].get_text(strip=True)
    category = tds[1].get_text(strip=True)

    title_td = tds[2]
    title_link = title_td.find("a")
    if title_link is None or not title_link.get("href"):
        return None
    title = title_link.get_text(strip=True)
    detail_url = urljoin(BASE_URL, title_link["href"])

    dept = tds[3].get_text(strip=True)
    reg_date = tds[4].get_text(strip=True)
    views = tds[6].get_text(strip=True)

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


def extract_attachment_info(view: BeautifulSoup) -> Tuple[List[Dict[str, str]], List[str]]:
    attachments: List[Dict[str, str]] = []
    sizes: List[str] = []

    for item in view.select("dl.file-list div.file-list__set__item"):
        anchor = item.find("a", href=True)
        if not anchor:
            continue
        download_url = urljoin(BASE_URL, anchor["href"])
        name_span = anchor.select_one(".name")
        raw_name = name_span.get_text(" ", strip=True) if name_span else anchor.get_text(" ", strip=True)

        size_match = FILE_SIZE_PATTERN.search(raw_name)
        size = size_match.group(1).strip() if size_match else ""
        name = FILE_SIZE_PATTERN.sub("", raw_name).strip()

        attachments.append({
            "name": name,
            "url": download_url,
            "size": size,
        })
        if size:
            sizes.append(size)

    return attachments, sizes


def download_file(session: requests.Session, url: str, dest_path: Path) -> Path:
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT, headers=DETAIL_HEADERS, stream=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScraperError(f"첨부파일 다운로드 실패: {url} | {exc}") from exc

    with dest_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return dest_path


def extract_text_from_pdf(path: Path) -> str:
    if pdfplumber is None:
        print(f"[경고] pdfplumber 미설치로 PDF 파싱을 건너뜁니다: {path.name}")
        return ""
    try:
        text_parts: List[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as exc:
        print(f"[경고] PDF 파싱 실패 ({path.name}): {exc}")
        return ""


def extract_text_from_hwp(path: Path) -> str:
    if olefile is not None:
        try:
            with olefile.OleFileIO(str(path)) as ole:
                if not ole.exists("BodyText/Section0"):
                    return ""
                with ole.openstream("BodyText/Section0") as stream:
                    data = stream.read()
                    try:
                        decompressed = zlib.decompress(data, -15)
                    except zlib.error:
                        decompressed = data
                    return decompressed.decode("utf-16-le", errors="ignore")
        except Exception as exc:
            print(f"[경고] HWP 파싱 실패 ({path.name}): {exc}")

    if _Hwp5File and _Hwp5TextTransform and closing and io:
        try:
            text_transform = _Hwp5TextTransform()
            buffer = io.BytesIO()
            with closing(_Hwp5File(str(path))) as hwp:
                text_transform.transform_hwp5_to_text(hwp, buffer)
            raw_bytes = buffer.getvalue()
            try:
                return raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return raw_bytes.decode("cp949", errors="ignore")
        except Exception as exc:
            print(f"[경고] hwp5 텍스트 추출 실패 ({path.name}): {exc}")
    else:
        print(f"[경고] olefile 미설치로 HWP 파싱을 건너뜁니다: {path.name}")
    return ""


def extract_text_from_file(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return extract_text_from_pdf(path)
    if ext == "hwp":
        return extract_text_from_hwp(path)
    if ext in {"txt", "csv", "log"}:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def is_header_line(line: str) -> bool:
    normalized = line.replace(" ", "")
    return all(keyword in normalized for keyword in ["항목", "점검사항", "점검방식"])


def normalize_cell(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def parse_table_from_text(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    cleaned_lines = [normalize_cell(line) for line in text.splitlines()]
    lines = [line for line in cleaned_lines if line]
    header_index = None
    for idx, line in enumerate(lines):
        if is_header_line(line):
            header_index = idx
            break
    if header_index is None:
        return []

    rows: List[Dict[str, str]] = []
    current_row: Optional[Dict[str, str]] = None
    for line in lines[header_index + 1 :]:
        if is_header_line(line):
            current_row = None
            continue
        parts = re.split(r"\s{2,}|\t|\|", line)
        parts = [normalize_cell(p) for p in parts if normalize_cell(p)]
        if len(parts) >= 3:
            row = {
                "항 목": parts[0],
                "점 검 사 항": parts[1],
                "점 검 방 식": " ".join(parts[2:]).strip(),
            }
            rows.append(row)
            current_row = row
        elif current_row:
            current_row["점 검 방 식"] = normalize_cell(current_row["점 검 방 식"] + " " + line)
    return rows


def parse_table_from_html(html: str) -> List[Dict[str, str]]:
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml-xml")
    except Exception:
        soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")
    parsed_rows: List[Dict[str, str]] = []

    for table in tables:
        raw_rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = [normalize_cell(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            if cells:
                raw_rows.append(cells)

        if not raw_rows:
            continue

        headers = [cell.replace(" ", "") for cell in raw_rows[0]]

        def find_index(keyword: str) -> Optional[int]:
            for idx, header in enumerate(headers):
                if keyword in header:
                    return idx
            return None

        idx_item = find_index("항목")
        idx_check = find_index("점검사항")
        idx_method = find_index("점검방식")

        if None in (idx_item, idx_check, idx_method):
            continue

        bullet_tokens = {"", "-", "☑", "□", "◦", "•"}
        noise_items = {"필 수", "필수", "선 택", "선택", "구 분", "구분"}

        current_entry: Optional[Dict[str, str]] = None

        for row in raw_rows[1:]:
            item = row[idx_item] if idx_item < len(row) else ""
            check = row[idx_check] if idx_check < len(row) else ""

            method_parts: List[str] = []
            if idx_method < len(row):
                method_parts.append(row[idx_method])
            for col_idx, cell in enumerate(row):
                if col_idx in {idx_item, idx_check, idx_method}:
                    continue
                method_parts.append(cell)
            method = normalize_cell(" ".join(part for part in method_parts if part))

            def strip_bullets(text: str) -> str:
                return text.strip("□☑◦• ·").strip()

            item = strip_bullets(item)
            check = strip_bullets(check)
            method = strip_bullets(method)

            item_is_valid = item and item not in noise_items and item not in bullet_tokens
            if item_is_valid:
                if current_entry and current_entry.get("점 검 방 식"):
                    parsed_rows.append(current_entry)
                current_entry = {
                    "항 목": item,
                    "점 검 사 항": "",
                    "점 검 방 식": "",
                }
            elif not current_entry:
                continue

            if check and check not in bullet_tokens:
                current_entry["점 검 사 항"] = check
                method_for_entry = method
            elif method:
                # 일부 문서는 점검사항이 방법 열에 합쳐져 있는 경우가 있어 첫 문장을 할당
                current_entry["점 검 사 항"] = method.split(" [")[0].strip()
                method_for_entry = method[len(current_entry["점 검 사 항"]):].strip()
            else:
                method_for_entry = ""

            method_for_entry = strip_bullets(method_for_entry)
            if method_for_entry:
                if current_entry["점 검 방 식"]:
                    current_entry["점 검 방 식"] += " " + method_for_entry
                else:
                    current_entry["점 검 방 식"] = method_for_entry

        if current_entry and current_entry.get("점 검 방 식"):
            parsed_rows.append(current_entry)

        if parsed_rows:
            break

    return parsed_rows


def extract_table_rows_from_hwp(path: Path) -> List[Dict[str, str]]:
    text_rows = parse_table_from_text(extract_text_from_hwp(path))
    if text_rows:
        return text_rows

    if HTML_TRANSFORM and _Hwp5File and closing:
        try:
            with closing(_Hwp5File(str(path))) as hwp:
                buffer = io.BytesIO()
                HTML_TRANSFORM.transform_hwp5_to_xhtml(hwp, buffer)
            html = buffer.getvalue().decode("utf-8", errors="ignore")
            rows = parse_table_from_html(html)
            if rows:
                return rows
        except Exception as exc:
            print(f"[경고] HWP HTML 변환 실패 ({path.name}): {exc}")

    return []


def extract_table_rows_from_file(path: Path) -> List[Dict[str, str]]:
    text = extract_text_from_file(path)
    if not text:
        return []
    return parse_table_from_text(text)


def extract_table_rows_from_zip(
    path: Path,
    *,
    stop_when_found: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    try:
        with zipfile.ZipFile(path) as zf, tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for idx, member in enumerate(zf.namelist(), start=1):
                if member.endswith("/"):
                    continue
                inner_name = Path(member)
                suffix_lower = inner_name.suffix.lower()
                if suffix_lower not in {".hwp", ".pdf", ".zip"}:
                    continue
                safe_inner_name = re.sub(r"[^\w가-힣._-]", "_", inner_name.name) or f"file_{idx}"
                target_path = temp_path / safe_inner_name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, target_path.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
                inner_rows = extract_table_rows_from_path(
                    target_path,
                    stop_when_found=stop_when_found,
                    log=log,
                )
                if inner_rows:
                    rows.extend(inner_rows)
                    if stop_when_found:
                        return rows
    except Exception as exc:
        print(f"[경고] ZIP 파싱 실패 ({path.name}): {exc}")
    return rows


def extract_table_rows_from_path(
    path: Path,
    *,
    stop_when_found: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, str]]:
    ext = path.suffix.lower().lstrip(".")
    if ext == "zip":
        return extract_table_rows_from_zip(
            path,
            stop_when_found=stop_when_found,
            log=log,
        )
    if ext == "hwp":
        if log:
            log(f"[정보] HWP 텍스트 추출 시작: {path.name}")
        rows = extract_table_rows_from_hwp(path)
    else:
        rows = extract_table_rows_from_file(path)
    if stop_when_found and rows:
        return rows
    return rows


def extract_table_from_attachments(
    session: requests.Session,
    attachments: List[Dict[str, str]],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, str]]:
    if not attachments:
        return []
    rows: List[Dict[str, str]] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for idx, attachment in enumerate(attachments, start=1):
            url = attachment.get("url")
            if not url:
                continue
            cached = _attachment_cache.get(url)
            if cached is not None:
                if cached:
                    rows.extend(cached)
                    return rows
                continue

            filename = attachment.get("name") or f"attachment_{idx}"
            safe_name = re.sub(r"[^\w가-힣._-]", "_", filename)
            dest = temp_path / safe_name
            try:
                if log:
                    log(f"[정보] 첨부 다운로드 시작: {filename}")
                download_file(session, url, dest)
                if log:
                    log(f"[정보] 첨부 다운로드 완료: {filename} ({dest.stat().st_size} bytes)")
            except ScraperError as exc:
                print(f"[경고] 첨부 다운로드 실패: {exc}")
                _attachment_cache[url] = []
                continue

            extracted_rows = extract_table_rows_from_path(
                dest,
                stop_when_found=True,
                log=log,
            )
            _attachment_cache[url] = extracted_rows
            if extracted_rows:
                rows.extend(extracted_rows)
                break
    return rows


def parse_detail(
    session: requests.Session,
    detail_url: str,
    *,
    skip_table_extraction: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    try:
        soup = fetch_soup(session, detail_url)
        if log:
            log(f"[정보] 상세 페이지 응답 수신: {detail_url}")
    except ScraperError as exc:
        print(f"[경고] 상세 페이지 요청 실패: {exc}")
        return {}, []

    view = soup.select_one("div.bd-view")
    if not view:
        print(f"[경고] 상세 영역을 찾을 수 없습니다: {detail_url}")
        return {}, []

    detail_data: Dict[str, str] = {}

    content_div = view.select_one("div.dbdata")
    if content_div:
        content_text = content_div.get_text("\n", strip=True)
        detail_data["상세내용"] = content_text or "-"
    else:
        detail_data["상세내용"] = "-"

    attachments, sizes = extract_attachment_info(view)
    if log:
        log(f"[정보] 첨부파일 {len(attachments)}건 발견: {detail_url}")
    if sizes:
        detail_data["상세첨부파일크기"] = " | ".join(sizes)

    if skip_table_extraction:
        detail_data["항 목"] = "-"
        detail_data["점 검 사 항"] = "-"
        detail_data["점 검 방 식"] = "-"
    else:
        table_rows = extract_table_from_attachments(
            session,
            attachments,
            log=log,
        )
        if table_rows:
            detail_data["항 목"] = " || ".join(row.get("항 목", "") for row in table_rows if row.get("항 목")) or "-"
            detail_data["점 검 사 항"] = " || ".join(row.get("점 검 사 항", "") for row in table_rows if row.get("점 검 사 항")) or "-"
            detail_data["점 검 방 식"] = " || ".join(row.get("점 검 방 식", "") for row in table_rows if row.get("점 검 방 식")) or "-"
        else:
            detail_data["항 목"] = "-"
            detail_data["점 검 사 항"] = "-"
            detail_data["점 검 방 식"] = "-"

    for dl in view.find_all("dl", recursive=False):
        if "file-list" in (dl.get("class") or []):
            continue
        dts = [dt.get_text(strip=True) for dt in dl.find_all("dt")]
        dds = [dd.get_text(" ", strip=True) for dd in dl.find_all("dd")]
        for dt_text, dd_text in zip(dts, dds):
            normalized_key = dt_text.replace(" ", "")
            mapped_key = DETAIL_KEY_MAP.get(normalized_key) or DETAIL_KEY_MAP.get(dt_text) or dt_text
            detail_data[mapped_key] = dd_text

    return detail_data, attachments


def scrape_all(
    session: requests.Session,
    limit: Optional[int] = None,
    *,
    skip_table_extraction: bool = False,
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    page = 1

    def log(message: str) -> None:
        print(message, flush=True)

    while True:
        params = {"menuNo": "200177", "pageIndex": str(page)}
        try:
            soup = fetch_soup(session, urljoin(BASE_URL, LIST_PATH), params=params)
        except ScraperError as exc:
            log(f"[경고] 목록 페이지 요청 실패: {exc}")
            break

        table = soup.find("table")
        if not table:
            log(f"[정보] 목록 테이블이 없습니다 (page={page}).")
            break

        body = table.find("tbody")
        if not body:
            log(f"[정보] tbody가 없습니다 (page={page}).")
            break

        rows = [parse_list_row(tr) for tr in body.find_all("tr")]
        rows = [row for row in rows if row]
        if not rows:
            log(f"[정보] 더 이상 데이터가 없습니다 (page={page}).")
            break

        new_records = 0
        for row in rows:
            ntt_id = row.get("nttId")
            if ntt_id and ntt_id in seen_ids:
                continue

            log(f"[정보] 상세 수집 시작: nttId={ntt_id} | 제목={row.get('제목', '-')}")
            detail_data, attachments = parse_detail(
                session,
                row["상세페이지URL"],
                skip_table_extraction=skip_table_extraction,
                log=log,
            )
            seen_ids.add(ntt_id)

            attach_names = [att["name"] for att in attachments if att.get("name")]
            attach_urls = [att["url"] for att in attachments if att.get("url")]
            attach_sizes = detail_data.get("상세첨부파일크기", "")

            record = {
                "번호": row["번호"] or "-",
                "구분": row["구분"] or "-",
                "제목": row["제목"] or "-",
                "담당부서": row["담당부서"] or "-",
                "등록일": row["등록일"] or "-",
                "첨부파일": "Y" if attachments else "-",
                "첨부파일 이름": " | ".join(attach_names) if attach_names else "-",
                "첨부파일URL": " | ".join(attach_urls) if attach_urls else "-",
                "조회수": row["조회수"] or "-",
                "상세페이지URL": row["상세페이지URL"],
                "상세등록일": detail_data.get("상세등록일", "-"),
                "상세첨부파일크기": attach_sizes if attach_sizes else "-",
                "상세내용": detail_data.get("상세내용", "-"),
                "상세담당부서": detail_data.get("상세담당부서", "-"),
                "상세담당팀": detail_data.get("상세담당팀", "-"),
                "상세담당자": detail_data.get("상세담당자", "-"),
                "상세문의": detail_data.get("상세문의", "-"),
                "상세문의이메일": detail_data.get("상세문의이메일", "-"),
                "항 목": detail_data.get("항 목", "-"),
                "점 검 사 항": detail_data.get("점 검 사 항", "-"),
                "점 검 방 식": detail_data.get("점 검 방 식", "-"),
            }
            if "상세조회수" in detail_data:
                record["상세조회수"] = detail_data["상세조회수"]

            results.append(record)
            new_records += 1
            log(f"[정보] 상세 수집 완료: nttId={ntt_id}")

            if limit is not None and len(results) >= limit:
                break

        log(f"[정보] {page}페이지 처리 완료 - {new_records}건")
        if limit is not None and len(results) >= limit:
            log(f"[정보] 수집 제한 {limit}건에 도달하여 중단합니다.")
            break
        page += 1
        time.sleep(SLEEP_SECONDS)

    return results


def save_results(results: List[Dict[str, str]], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "inspection_results.json"
    csv_path = output_dir / "inspection_results.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "번호",
        "구분",
        "제목",
        "담당부서",
        "등록일",
        "첨부파일",
        "첨부파일 이름",
        "첨부파일URL",
        "조회수",
        "상세페이지URL",
        "상세등록일",
        "상세첨부파일크기",
        "상세내용",
        "상세담당부서",
        "상세담당팀",
        "상세담당자",
        "상세문의",
        "상세문의이메일",
        "항목",
        "점검사항",
        "점검방식",
    ]
    if results and "상세조회수" in results[0]:
        fieldnames.insert(fieldnames.index("상세페이지URL"), "상세조회수")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow(row)

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
    parser.add_argument(
        "--skip-attachments",
        action="store_true",
        help="첨부파일 다운로드 및 점검표 추출을 건너뜁니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    session = requests.Session()
    results = scrape_all(
        session,
        limit=args.limit,
        skip_table_extraction=args.skip_attachments,
    )
    print(f"[정보] 총 {len(results)}건 수집 완료")

    json_path, csv_path = save_results(results, output_dir)
    print(f"[정보] JSON 저장: {json_path}")
    print(f"[정보] CSV 저장: {csv_path}")


if __name__ == "__main__":
    main()
