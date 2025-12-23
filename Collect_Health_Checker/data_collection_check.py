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

# ==================================================
# Health Check 목록
# ==================================================
HEALTH_CHECKS = [
    bok_legnotice_health_check,
    bok_law_regulations_health_check,
    crefia_legnotice_health_check,
    crefia_health_check,
    fsb_health_check,
    fsc_guideline_health_check,
    fsc_legnotice_health_check,
    fss_admin_guidance_health_check,
    fss_admin_health_check,
    fss_guideline_check,
    fss_legnotice_health_check,
    fss_mngtnotice_check,
    fss_sanctions_check,
    fss_menual_health_check,
    kfb_committee_health_check,
    kfb_finlaw_health_check,
    kfb_legnotice_health_check,
    kfb_health_check,
    kofia_legnotice_health_check,
    kofia_health_check,
    kofiu_health_check,
    krx_legnotice_health_check,
    krx_health_check,
    law_legnotice_health_check,
    law_health_check,
    moleg_health_check,
]

# ==================================================
# Health Check 실행
# ==================================================
def run_data_collection_health_check():
    print("\n" + "=" * 80)
    print("🚀 자료 수집 Health Check 시작")
    print("=" * 80)

    results = []
    start_time = datetime.now()

    for check_func in HEALTH_CHECKS:
        module_name = check_func.__module__.split(".")[0]
        func_name = check_func.__name__

        log_path = (
            JSON_ROOT
            / module_name
            / f"{func_name}.{RUN_DATE}.json"
        )

        print(f"[CHECK] {module_name}.{func_name}")

        try:
            result = check_func()
        except Exception as e:
            result = {
                "org_name": func_name,
                "status": "ERROR",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

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
