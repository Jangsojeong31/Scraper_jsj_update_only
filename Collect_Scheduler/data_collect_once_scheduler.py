import os
import sys
import traceback
from datetime import datetime

# ======================================================
# 프로젝트 루트 설정 (/Scraper)
# ======================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

# ======================================================
# 스크래퍼 import
# ======================================================

# 한국은행
from BOK_LegNotice_Scraper.bok_legnotice_scraper_v2 import run as bok_legnotice_run
from BOK_Scraper.bok_scraper_v2 import run as bok_scraper_run

# 여신금융협회
from CREFIA_LegNotice_Scraper.crefia_legnotice_scraper_v2 import run as crefia_legnotice_scraper_run
from CREFIA_Scraper.crefia_scraper_v2 import run as crefia_scraper_run

# 저축은행중앙회
from FSB_Scraper.fsb_scraper_v2 import run as fsb_scraper_run

# 금융위원회
from FSC_GUIDELINE_Scraper.fsc_guideline_scraper_v2 import run as fsc_guideline_scraper_run
from FSC_LegNotice_Scraper.fsc_legnotice_scraper_v2 import run as fsc_legnotice_scraper_run

# 금융감독원
from FSS_AdministrativeGuidance_Scraper.fss_adminguide_scraper_v2 import run as fss_adminguide_scraper_run
from FSS_AdminScraper.fss_admin_scraper_v2 import run as fss_admin_scraper_run
from FSS_GUIDELINE_Scraper.fss_guideline_scraper_v2 import run as fss_guideline_scraper_run
from FSS_LegNotice_Scraper.fss_legnotice_scraper_v2 import run as fss_legnotice_scraper_run
from FSS_ManagementNotices_Scraper.fss_mngtnotice_scraper_v2 import run as fss_mngtnotice_scraper_run
from FSS_Sanctions_Scraper.fss_sanctions_scraper_v2 import run as fss_sanctions_scraper_run
from InspectionManual_Scraper.fss_work_guide_scraper_v2 import run as fss_work_guide_scraper_run

# 은행연합회
from KFB_Committee_Scraper.kfb_committee_scraper_v2 import run as kfb_committee_scraper_run
from KFB_Finlaw_Scraper.kfb_finlaw_scraper_v2 import run as kfb_finlaw_scraper_run
from KFB_LegNotice_Scraper.kfb_legnotice_scraper_v2 import run as kfb_legnotice_scraper_run
from KFB_Scraper.kfb_scraper_v2 import run as kfb_scraper_run

# 금융투자협회
from KOFIA_LegNotice_Scraper.kofia_legnotice_scraper_v2 import run as kofia_legnotice_scraper_run
from KOFIA_Scraper.kofia_scraper_v2 import run as kofia_scraper_run

# 금융정보분석원
from KoFIU_Scraper.kofiu_scraper_v2 import run as kofiu_scraper_run

# 한국거래소
from KRX_LegNotice_Scraper.krx_legnotice_scraper_v2 import run as krx_legnotice_scraper_run
from KRX_Scraper.krx_scraper_v2 import run as krx_scraper_run

# 법제처
from Law_LegNotice_Scraper.law_legnotice_scraper_v2 import run as law_legnotice_scraper_run
from Law_Scraper.law_scraper_v2 import run as law_scraper_run
from Moleg_Scraper.moleg_scraper_v2 import run as moleg_scraper_run

# 보도자료
from PressReleases_Scraper.scrape_fss_press_releases_v2 import run as scrape_fss_press_releases_run


# ======================================================
# 공통 실행 래퍼
# ======================================================
def run_scraper(name: str, func):
    print(f"[{datetime.now()}] ▶ START {name}", flush=True)
    try:
        func()
        print(f"[{datetime.now()}] ✔ SUCCESS {name}", flush=True)
    except Exception:
        print(f"[{datetime.now()}] ✖ FAIL {name}", flush=True)
        traceback.print_exc()


# ======================================================
# 전체 스크래퍼 실행 (1회)
# ======================================================
def run_daily_scrapers_once():
    print("=" * 100)
    print(f"[{datetime.now()}] DAILY SCRAPER (ONCE) START")
    print("=" * 100)

    scrapers = [
        ("한국은행-운영 및 법규→ 법규정보→ 규정 예고", bok_legnotice_run),
        ("한국은행-한국은행>운영 및 법규>법규정보>법령 검색 >[탭] 규정", bok_scraper_run),

        ("여신금융협회-정보센터→ 자율규제 제·개정 공고", crefia_legnotice_scraper_run),
        ("여신금융협회-정보센터>규제개선>자율규제 현황", crefia_scraper_run),

        ("저축은행중앙회-소비자포탈>모범규준", fsb_scraper_run),

        ("금융위원회(금융규제·법령해석포털)	행정지도·행정감독>금융위 행정지도>시행", fsc_guideline_scraper_run),
        ("금융위원회-입법예고", fsc_legnotice_scraper_run),

        ("금융감독원-업무자료>금융감독법규>금융행정지도>행정지도 내역", fss_adminguide_scraper_run),
        ("금융감독원-업무자료>금융감독법규>감독행정작용>감독행정작용 내역", fss_admin_scraper_run),
        ("금융감독원-행정지도 및 행정작용", fss_guideline_scraper_run),
        ("금융감독원-업무자료→ 금융감독법규정보→ 금융감독법규정→ 세칙 제∙개정 예고", fss_legnotice_scraper_run),
        ("금융감독원-업무>검사.제제>금융회사 경영유의사항 등 공시", fss_mngtnotice_scraper_run),
        ("금융감독원-제재조치 현황", fss_sanctions_scraper_run),
        ("금융감독원-업무자료>검사·제재>검사업무안내서", fss_work_guide_scraper_run),

        ("은행연합회-규제심의위원회 결과", kfb_committee_scraper_run),
        ("은행연합회-금융관련법규 > 법규·규제 > 법규·규제", kfb_finlaw_scraper_run),
        ("은행연합회-공시·자료실→ 법규·규제→규제운영→ 자율규제 제정∙개정예고", kfb_legnotice_scraper_run),
        ("은행연합회-공시·자료실>법규·규제>[탭]자율규제", kfb_scraper_run),

        ("금융투자협회-법규정보시스템→ 규정 제∙개정 예고", kofia_legnotice_scraper_run),
        ("금융투자협회-법규정보시스템**", kofia_scraper_run),

        ("금융정보분석원-알림마당>제재공시", kofiu_scraper_run),

        ("한국거래소-법무포탈→ 규정 제∙개정 예고", krx_legnotice_scraper_run),
        ("한국거래소-KRX법무포탈", krx_scraper_run),

        ("법제처-국가법령정보센터→ 최신법령 옆 (+)→ 시행예정법령", law_legnotice_scraper_run),
        ("법제처-국가법령정보센터", law_scraper_run),
        ("법제처-법제처-뉴스.소식 → 입법예고", moleg_scraper_run),
        ("보도자료-금융감독원-보도, 알림 > 보도자료", scrape_fss_press_releases_run),
    ]

    for name, func in scrapers:
        run_scraper(name, func)

    print("=" * 100)
    print(f"[{datetime.now()}] DAILY SCRAPER (ONCE) END")
    print("=" * 100)


# ======================================================
# Main
# ======================================================
if __name__ == "__main__":
    try:
        run_daily_scrapers_once()
        print("✅ SCRAPER FINISHED - EXIT")
        sys.exit(0)
    except Exception:
        print("❌ SCRAPER FAILED")
        traceback.print_exc()
        sys.exit(1)
