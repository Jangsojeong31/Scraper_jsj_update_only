"""
data_collection_check.py

1) 프로젝트 전체 상대 import 위반 자동 점검
2) 금융/법규 자료 수집 Health Check 전체 실행
3) 각 Health Check 결과를 개별 로그로 저장
4) 최종 통합 결과 저장

권장 실행:
    python Health_Checker/data_collection_check.py
"""

# ==================================================
# 프로젝트 루트 등록
# ==================================================
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ==================================================
# 공통 import
# ==================================================
import json
import ast
import traceback
from datetime import datetime

from error_classifier import classify_health_error

# ==================================================
# 날짜 / 로그 경로
# ==================================================
RUN_DATE = datetime.now().strftime("%Y-%m-%d")
LOG_ROOT = PROJECT_ROOT / "Collect_Health_Checker" / "logs"
LOG_ROOT.mkdir(parents=True, exist_ok=True)
JSON_ROOT = PROJECT_ROOT / "Collect_Health_Checker" / "output" / "json"
JSON_ROOT.mkdir(parents=True, exist_ok=True)

# ==================================================
# 상대 import 자동 점검 설정
# ==================================================
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "site-packages",
    "node_modules",
}

# ==================================================
# 상대 import 점검 로직
# ==================================================
def find_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def get_local_modules(py_file: Path):
    return {
        p.stem
        for p in py_file.parent.glob("*.py")
        if p.name != "__init__.py"
    }


def check_relative_imports(py_file: Path):
    issues = []
    local_modules = get_local_modules(py_file)

    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except Exception:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                base = node.module.split(".")[0]
                if base in local_modules:
                    issues.append((node.lineno, f"from {node.module} import ..."))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in local_modules:
                    issues.append((node.lineno, f"import {alias.name}"))

    return issues


def run_relative_import_check():
    print("\n" + "=" * 80)
    print("🔍 상대 import 자동 점검 시작")
    print("=" * 80)

    total = 0

    for py_file in find_python_files(PROJECT_ROOT):
        issues = check_relative_imports(py_file)
        if issues:
            print(f"\n📄 {py_file.relative_to(PROJECT_ROOT)}")
            for lineno, code in issues:
                print(f"  ❌ Line {lineno}: {code}")
            total += len(issues)

    if total == 0:
        print("\n✅ 상대 import 위반 없음")
    else:
        print(f"\n🚨 상대 import 위반 총 {total}건")

    return total

# ==================================================
# JSON 저장 유틸
# ==================================================
def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================================================
# Health Check 함수 import
# ==================================================

# 한국은행
from BOK_LegNotice_Scraper.bok_legnotice_scraper_v2 import bok_legnotice_health_check
from BOK_Scraper.bok_scraper_v2 import bok_law_regulations_health_check

# 여신금융협회
from CREFIA_LegNotice_Scraper.crefia_legnotice_scraper_v2 import crefia_legnotice_health_check
from CREFIA_Scraper.crefia_scraper_v2 import crefia_health_check

# 저축은행중앙회
from FSB_Scraper.fsb_scraper_v2 import fsb_health_check

# 금융위원회
from FSC_GUIDELINE_Scraper.fsc_guideline_scraper_v2 import fsc_guideline_health_check
from FSC_LegNotice_Scraper.fsc_legnotice_scraper_v2 import fsc_legnotice_health_check

# 금융감독원
from FSS_AdministrativeGuidance_Scraper.fss_adminguide_scraper_v2 import fss_admin_guidance_health_check
from FSS_AdminScraper.fss_admin_scraper_v2 import fss_admin_health_check
from FSS_GUIDELINE_Scraper.fss_guideline_scraper_v2 import fss_guideline_check
from FSS_LegNotice_Scraper.fss_legnotice_scraper_v2 import fss_legnotice_health_check
from FSS_ManagementNotices_Scraper.fss_mngtnotice_scraper_v2 import fss_mngtnotice_check
from FSS_Sanctions_Scraper.fss_sanctions_scraper_v2 import fss_sanctions_check
from InspectionManual_Scraper.fss_work_guide_scraper_v2 import fss_menual_health_check

# 은행연합회
from KFB_Committee_Scraper.kfb_committee_scraper_v2 import kfb_committee_health_check
from KFB_Finlaw_Scraper.kfb_finlaw_scraper_v2 import kfb_finlaw_health_check
from KFB_LegNotice_Scraper.kfb_legnotice_scraper_v2 import kfb_legnotice_health_check
from KFB_Scraper.kfb_scraper_v2 import kfb_health_check

# 금융투자협회
from KOFIA_LegNotice_Scraper.kofia_legnotice_scraper_v2 import kofia_legnotice_health_check
from KOFIA_Scraper.kofia_scraper_v2 import kofia_health_check

# 금융정보분석원
from KoFIU_Scraper.kofiu_scraper_v2 import kofiu_health_check

# 한국거래소
from KRX_LegNotice_Scraper.krx_legnotice_scraper_v2 import krx_legnotice_health_check
from KRX_Scraper.krx_scraper_v2 import krx_health_check

# 법제처
from Law_LegNotice_Scraper.law_legnotice_scraper_v2 import law_legnotice_health_check
from Law_Scraper.law_scraper_v2 import law_health_check
from Moleg_Scraper.moleg_scraper_v2 import moleg_health_check

#보도자료
from PressReleases_Scraper.scrape_fss_press_releases_v2 import fss_press_releases_health_check

# ==================================================
# Health Check 목록
# ==================================================
HEALTH_CHECKS = [
    {
        "title": "한국은행-운영 및 법규→ 법규정보→ 규정 예고",
        "type": "BOK_LEGNOTICE",
        "func_check": bok_legnotice_health_check,
    },
    {
        "title": "한국은행 > 운영 및 법규 > 법규정보 > 법령 검색 > [탭] 규정",
        "type": "BOK",
        "func_check": bok_law_regulations_health_check,
    },

    {
        "title": "여신금융협회 > 정보센터 > 자율규제 제·개정 공고",
        "type": "CREFIA_LEGNOTICE",
        "func_check": crefia_legnotice_health_check,
    },
    {
        "title": "여신금융협회 > 정보센터 > 규제개선 > 자율규제 현황",
        "type": "CREFIA",
        "func_check": crefia_health_check,
    },

    {
        "title": "저축은행중앙회 > 소비자포탈 > 모범규준",
        "type": "FSB",
        "func_check": fsb_health_check,
    },

    {
        "title": "금융위원회 > 행정지도·행정감독 > 금융위 행정지도 > 시행",
        "type": "FSC_GUIDELINE",
        "func_check": fsc_guideline_health_check,
    },
    {
        "title": "금융위원회 > 입법예고",
        "type": "FSC_LEGNOTICE",
        "func_check": fsc_legnotice_health_check,
    },

    {
        "title": "금융감독원 > 금융행정지도 > 행정지도 내역",
        "type": "FSS_ADMIN_GUIDANCE",
        "func_check": fss_admin_guidance_health_check,
    },
    {
        "title": "금융감독원 > 감독행정작용 내역",
        "type": "FSS_ADMIN",
        "func_check": fss_admin_health_check,
    },
    {
        "title": "금융감독원 행정지도 및 행정작용",
        "type": "FSS_GUIDELINE",
        "func_check": fss_guideline_check,
    },
    {
        "title": "금융감독원 > 세칙 제·개정 예고",
        "type": "FSS_LEGNOTICE",
        "func_check": fss_legnotice_health_check,
    },
    {
        "title": "금융감독원 경영유의사항 공시",
        "type": "FSS_MANAGEMENTNOTICES",
        "func_check": fss_mngtnotice_check,
    },
    {
        "title": "금융감독원 제재조치 현황",
        "type": "FSS_SANCTIONS",
        "func_check": fss_sanctions_check,
    },

    {
        "title": "검사업무 안내서",
        "type": "InspectionManual",
        "func_check": fss_menual_health_check,
    },

    {
        "title": "은행연합회 규제심의위원회 결과",
        "type": "KFB_COMMITTEE",
        "func_check": kfb_committee_health_check,
    },
    {
        "title": "은행연합회 금융관련법규",
        "type": "KFB_FINLAW",
        "func_check": kfb_finlaw_health_check,
    },
    {
        "title": "은행연합회 자율규제 제정·개정예고",
        "type": "KFB_LegNotice",
        "func_check": kfb_legnotice_health_check,
    },
    {
        "title": "은행연합회 자율규제",
        "type": "KFB",
        "func_check": kfb_health_check,
    },

    {
        "title": "금융투자협회 규정 제·개정 예고",
        "type": "KOFIA_LegNotice",
        "func_check": kofia_legnotice_health_check,
    },
    {
        "title": "금융투자협회 법규정보시스템",
        "type": "KOFIA",
        "func_check": kofia_health_check,
    },

    {
        "title": "금융정보분석원(KoFIU) 제재공시",
        "type": "KoFIU",
        "func_check": kofiu_health_check,
    },

    {
        "title": "한국거래소 규정 제·개정 예고",
        "type": "KRX_LegNotice",
        "func_check": krx_legnotice_health_check,
    },
    {
        "title": "한국거래소 KRX 법무포탈",
        "type": "KRX",
        "func_check": krx_health_check,
    },

    {
        "title": "법제처 시행예정법령",
        "type": "Law_LegNotice",
        "func_check": law_legnotice_health_check,
    },
    {
        "title": "국가법령정보센터",
        "type": "Law",
        "func_check": law_health_check,
    },
    {
        "title": "법제처 입법예고",
        "type": "Moleg",
        "func_check": moleg_health_check,
    },

    {
        "title": "금융감독원 보도자료",
        "type": "PressReleases",
        "func_check": fss_press_releases_health_check,
    },
]


# ==================================================
# Health Check 실행
# ==================================================
def run_data_collection_health_check():
    print("\n" + "=" * 80)
    print("자료 수집 Health Check 시작")
    print("=" * 80)

    results = []
    start_time = datetime.now()

    for item in HEALTH_CHECKS:
        title = item["title"]
        check_type = item["type"]
        check_func = item["func_check"]

        func_name = check_func.__name__
        module_name = check_func.__module__.split(".")[0]

        print(f"\n[CHECK] {title}")
        print(f"        ({check_type} | {module_name}.{func_name})")

        log_path = (
            JSON_ROOT
            / check_type
            / f"{func_name}.{RUN_DATE}.json"
        )

        try:
            result = check_func()
        except Exception as e:
            result = {
                "org_name": check_type,
                "title": title,
                "status": "ERROR",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

        # ✅ 실패 유형 자동 분류
        if result.get("status") != "OK":
            error_type = classify_health_error(result)
            result["error_type"] = error_type.name
            result["error_type_desc"] = error_type.value

        write_json(log_path, result)
        results.append(result)

        print(f"  → 로그 저장: {log_path}")

    end_time = datetime.now()

    summary = {
        "run_date": RUN_DATE,
        "check_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "success": sum(1 for r in results if r.get("status") == "OK"),
        "fail": sum(1 for r in results if r.get("status") != "OK"),
        "elapsed_seconds": (end_time - start_time).total_seconds(),
        "results": results,
    }

    final_path = LOG_ROOT / f"final_result.{RUN_DATE}.json"
    write_json(final_path, summary)

    print("\n" + "=" * 80)
    print(
        f"✅ Health Check 완료 | 성공 {summary['success']} / 실패 {summary['fail']} | "
        f"소요 {summary['elapsed_seconds']}초"
    )
    print(f"📊 최종 결과 저장: {final_path}")
    print("=" * 80)

    return summary

# ==================================================
# Main
# ==================================================
if __name__ == "__main__":
    # violations = run_relative_import_check()

    # if violations > 0:
    #     print("\n⚠️ 상대 import 위반을 먼저 수정하는 것을 권장합니다.\n")

    run_data_collection_health_check()
