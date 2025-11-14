"""
금융감독원 보도자료 목록에서 첨부파일(HWP, PDF 등)을 모두 추출하고,
보도일을 HWP에서만 추출하는 스크립트 (CSV/Excel/JSON 저장)
"""
import requests
from bs4 import BeautifulSoup
import re
import io
import time
import olefile
from urllib.parse import urljoin
import pandas as pd
import json
from openpyxl.utils import get_column_letter


# -----------------------------------------------------------
# HWP 파일에서 텍스트 추출
# -----------------------------------------------------------
def extract_text_from_hwp_bytes(hwp_bytes):
    """HWP 파일 바이트 데이터를 메모리에서 읽어 텍스트 추출"""
    try:
        with olefile.OleFileIO(io.BytesIO(hwp_bytes)) as ole:
            text_content = ""
            possible_paths = ['PrvText', 'BodyText/Section0', 'Section0', 'DocInfo', 'BodyText']
            for path in possible_paths:
                if ole.exists(path):
                    data = ole.openstream(path).read()
                    try:
                        text = data.decode('utf-16-le', errors='ignore')
                        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
                        text = re.sub(r'\s+', ' ', text)

                        if len(text.strip()) > 10:
                            text_content = text
                            break
                    except Exception:
                        pass
            return text_content

    except Exception as e:
        print(f"    ⚠️ HWP 파일 파싱 오류: {e}")
        return ""


# -----------------------------------------------------------
# 텍스트에서 날짜 추출
# -----------------------------------------------------------
def extract_first_date(text):
    """텍스트에서 가장 처음 나타나는 날짜 추출 (보도일)"""
    if not text:
        return None

    date_patterns = [
        r'(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)',
        r'(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s*\(?[가-힣]*\)?)',
        r'(\d{4}-\d{1,2}-\d{1,2})',
        r'(\d{4}/\d{1,2}/\d{1,2})',
        r'(\d{8})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return None


# -----------------------------------------------------------
# 보도자료 목록 스크래핑
# -----------------------------------------------------------
def scrape_press_releases(base_url):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    results = []
    print("📢 보도자료 목록 처리 중...\n")

    try:
        response = session.get(base_url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', class_='board_list') or soup.find('table')

        if not table:
            print("❌ 테이블을 찾을 수 없습니다.")
            return results

        rows = table.find_all('tr')[1:]
        if not rows:
            print("❌ 데이터가 없습니다.")
            return results

        # 각 보도자료 행 반복 처리
        for idx, row in enumerate(rows, start=1):
            title_link = row.find('a', href=re.compile(r'view\.do'))
            if not title_link:
                continue

            # 제목, 상세 URL
            title = title_link.get_text(strip=True)
            detail_url = urljoin(base_url, title_link['href'])

            # 담당부서
            tds = row.find_all('td')
            department = tds[2].get_text(strip=True) if len(tds) >= 3 else None

            # 첨부파일 (.hwp, .pdf, 등)
            file_links = []
            attach_links = row.find_all('a', href=re.compile(r'fileDown\.do'))

            for link in attach_links:
                href = urljoin(base_url, link['href'])
                file_name = link.get_text(strip=True)

                file_links.append({
                    '첨부파일명': file_name,
                    '첨부파일 url': href
                })

            print(f"[{idx}] {title}")
            if not file_links:
                print("    ⚠️ 첨부파일 없음")

            # 상세 본문 가져오기
            try:
                detail_response = session.get(detail_url, timeout=30)
                detail_response.raise_for_status()
                detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                content_div = detail_soup.find('div', class_='dbdata')
                content = content_div.get_text(separator='\n', strip=True) if content_div else ''
                content = re.sub(r'\n+', '\n', content.strip())
            except Exception as e:
                print(f"    ⚠️ 상세페이지 크롤링 실패: {e}")
                content = ''

            # HWP 파일을 통한 보도일 추출
            date = None
            text_preview = None

            hwp_files = [f for f in file_links if f['첨부파일명'].lower().endswith('.hwp')]

            for f in hwp_files:
                try:
                    print(f"    📂 HWP 다운로드 중: {f['첨부파일명']}")
                    file_response = session.get(f['첨부파일 url'], timeout=30)
                    file_response.raise_for_status()

                    text = extract_text_from_hwp_bytes(file_response.content)
                    if text:
                        date = extract_first_date(text)
                        text_preview = text[:200]
                        print(f"    📅 보도일: {date or '추출 실패'}")
                        break

                except Exception as e:
                    print(f"    ⚠️ HWP 처리 실패 ({f['첨부파일명']}): {e}")

            # 결과 저장
            results.append({
                '번호': idx,
                '제목': title,
                '담당부서': department,
                '보도일': date,
                '첨부파일': file_links,
                '첨부파일내용 미리보기': text_preview,
                '상세페이지URL': detail_url,
                '내용': content
            })

            time.sleep(0.5)

    except Exception as e:
        print(f"❌ 처리 오류: {e}")

    return results


# -----------------------------------------------------------
# CSV / Excel / JSON 저장 함수
# -----------------------------------------------------------
def save_results(results, csv_file="results.csv", excel_file="results.xlsx", json_file="results.json"):
    if not results:
        print("❌ 저장할 결과가 없습니다.")
        return

    df = pd.DataFrame(results)

    # 첨부파일 리스트 → 문자열 변환
    df['첨부파일'] = df['첨부파일'].apply(
        lambda lst: ', '.join([f"{f['첨부파일명']} ({f['첨부파일 url']})" for f in lst]) if lst else ''
    )

    df.fillna('', inplace=True)

    # 컬럼 순서 정렬
    df = df[['번호', '제목', '보도일', '상세페이지URL', '첨부파일', '담당부서', '내용']]

    # CSV 저장
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"📄 CSV 저장 완료: {csv_file}")

    # Excel 저장
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='보도자료')
        ws = writer.sheets['보도자료']

        # 열 너비 자동 조정
        for i, col in enumerate(df.columns, start=1):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(max_len, 50)

    print(f"📘 Excel 저장 완료: {excel_file}")

    # JSON 저장
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"🧾 JSON 저장 완료: {json_file}")


# -----------------------------------------------------------
# 실행 메인
# -----------------------------------------------------------
def main():
    base_url = "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218&pageIndex=1"
    print("금융감독원 보도자료 스크래핑 시작")
    print("=" * 70)

    results = scrape_press_releases(base_url)

    print("=" * 70)
    print(f"총 {len(results)}개 보도자료 처리 완료")

    success = sum(1 for r in results if r['보도일'])
    if results:
        print(f"보도일 추출 성공률: {success}/{len(results)} ({success/len(results)*100:.1f}%)")

    save_results(results)


if __name__ == "__main__":
    main()
