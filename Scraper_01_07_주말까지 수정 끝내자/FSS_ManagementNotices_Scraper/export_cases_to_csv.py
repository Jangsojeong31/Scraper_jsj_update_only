import json
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

JSON_PATH = os.path.join(BASE_DIR, "output", "fss_mngnt_result.json")
CSV_PATH = os.path.join(BASE_DIR, "fss_mngnt_result.csv")
XLSX_PATH = os.path.join(BASE_DIR, "fss_mngnt_result.xlsx")


def main():
    # 1) JSON 로드
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []

    for item in data:
        사건목록 = item.get("사건목록", [])

        # 사건목록이 없는 경우도 한 줄로 남기고 싶다면 여기에서 처리
        if not 사건목록:
            rows.append({
                "번호": item.get("번호"),
                "제재대상기관": item.get("제재대상기관"),
                "제재조치요구일": item.get("제재조치요구일"),
                "관련부서": item.get("관련부서"),
                "조회수": item.get("조회수"),
                "문서유형": item.get("문서유형"),
                "상세페이지URL": item.get("상세페이지URL"),
                "제재조치내용": item.get("제재조치내용"),
                "제재대상": item.get("제재대상"),
                "제재내용": item.get("제재내용"),
                "사건_index": None,
                "사건제목": None,
                "사건내용": None,
            })
            continue

        for idx, 사건 in enumerate(사건목록, start=1):
            rows.append({
                "번호": item.get("번호"),
                "제재대상기관": item.get("제재대상기관"),
                "제재조치요구일": item.get("제재조치요구일"),
                "관련부서": item.get("관련부서"),
                "조회수": item.get("조회수"),
                "문서유형": item.get("문서유형"),
                "상세페이지URL": item.get("상세페이지URL"),
                "제재조치내용": item.get("제재조치내용"),
                "제재대상": item.get("제재대상"),
                "제재내용": item.get("제재내용"),
                "사건_index": idx,
                "사건제목": 사건.get("사건제목"),
                "사건내용": 사건.get("사건내용"),
            })

    df = pd.DataFrame(rows)

    # CSV 저장
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    # 엑셀 저장
    df.to_excel(XLSX_PATH, index=False)

    print(f"CSV 저장 완료: {CSV_PATH}")
    print(f"엑셀 저장 완료: {XLSX_PATH}")


if __name__ == "__main__":
    main()

