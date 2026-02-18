# Health_Checker/
#  ├─ check_module/
#  │   ├─ bok_legnotice_check.py
#  │   ├─ law_legnotice_check.py
#  │   ├─ kfb_committee_scraper.py
#  │   └─ __init__.py
#  └─ collect_health_check.py

HEALTH_CHECKERS = []

# 내부 Health Check
from . import bok_legnotice_check
from . import law_legnotice_check

# 외부 프로젝트 Health Check
from KFB_Committee_Scraper.kfb_committee_scraper import kfb_committee_health_check

HEALTH_CHECKERS.append(kfb_committee_health_check)

