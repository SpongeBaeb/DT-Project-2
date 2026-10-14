"""자동화 설정 — 경로, 알림 기준 등. 전처리 규칙은 rules_mrv.py에 있다.

프로젝트 루트(ship-carbon-ml/)에 pipeline/ 폴더를 두는 구조를 가정한다.
다른 위치의 프로젝트를 돌리려면 환경변수 SHIP_PIPELINE_ROOT 또는 --root 옵션을 쓴다.
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("SHIP_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))


def set_root(root):
    global ROOT
    ROOT = Path(root).resolve()


def paths():
    """ROOT 기준 경로 묶음 (set_root 이후에도 맞게 함수로 계산)"""
    r = ROOT
    return {
        "raw": r / "data" / "raw",                          # 연도별 MRV xlsx (노트북과 같은 위치)
        "raw_archive": r / "data" / "raw" / "archive",      # 새 버전이 들어오면 구버전을 여기로 옮김
        "sources_yaml": r / "config" / "data_sources.yaml",  # 노트북 1-1이 대조하는 버전 기록
        "cache": r / "data" / "cache",                      # 연도별 읽기 결과 캐시 (엑셀 다시 읽지 않도록)
        "out": r / "data" / "processed",                    # 파이프라인 결과 (노트북의 data/interim과 분리)
        "previous": r / "data" / "processed" / "_previous",  # 직전 결과 1개 백업
        "snapshots": r / "data" / "processed" / "snapshots",  # 최종 파일 스냅샷 (날짜 + 내용 해시, 최근 N개)
        "manifest": r / "data" / "processed" / "_manifest.json",
        "reports": r / "reports" / "pipeline",
        # VesselFinder: 크롤러 결과 파일과, 크롤러가 읽을 '제원 없는 IMO 목록' 위치
        "vf_dir": r / "data" / "raw" / "vesselfinder",       # ship_data_detailed.csv 를 여기에 둠
        "missing_spec_list": r / "data" / "processed" / "missing_spec_imo_list.txt",
    }


# ── VesselFinder 크롤링 (--crawl 옵션) ──
VF_OUTPUT_NAME = "ship_data_detailed.csv"   # data/raw/vesselfinder/ 안의 크롤링 결과 파일 (기존 크롤러와 같은 이름·형식)
CRAWL_MAX_PER_RUN = 200        # 한 번 실행에 크롤링할 최대 척수 (200척 ≈ 4~5분). --crawl-max로 바꿀 수 있음
CRAWL_DELAY_SEC = 1.0          # 요청 간격 (기존 크롤러와 같음)
CRAWL_RETRY_AFTER_DAYS = 7     # 실패한 IMO를 다시 시도할 때까지 기다리는 날수
CRAWL_MAX_ATTEMPTS = 3         # 이만큼 실패하면 더 시도하지 않음 (VesselFinder에 없는 선박)

# 크롤러(vessel_scraper_new.py)의 INPUT_TXT 경로. 지정하면 목록을 그 위치에도 복사한다.
CRAWLER_INPUT_TXT = os.environ.get("CRAWLER_INPUT_TXT", r"c:\DT Project\missing_spec_imo_list.txt")

# 파이프라인에 함께 들어 있는 제원 파일 (2026-10-06 수집분 22,899척 + 2026-10-06 추가 크롤링 6척 = 22,905척).
# data/raw/vesselfinder/ship_data_detailed.csv가 없으면 그 위치로 복사하고, 있으면 제원 값이 없는 IMO의 행만 덧붙인다
# (제원 값이 있는 기존 행은 절대 덮어쓰지 않음, enrich.ensure_spec_file)
SEED_DIR = Path(__file__).resolve().parent / "seed"

FIRST_YEAR = 2018
FILE_PATTERN = r"^(?P<year>\d{4})-v(?P<version>\d+)-(?P<date>\d{8})-.*\.xlsx$"   # 2024-v246-01102026-...xlsx

# 변경 리포트에서 '확인 필요'로 표시할 기준 (값만 표시, 실행은 계속)
ALERT_ROWS_PCT = 5.0        # 한 연도의 정제 후 행 수가 이 % 넘게 바뀌면
ALERT_CO2_PCT = 5.0         # 한 연도의 총 CO2가 이 % 넘게 바뀌면

# 값 변경 비교에서 숫자를 같은 값으로 볼 상대 오차
VALUE_RTOL = 1e-9

CSV_ENCODING = "utf-8-sig"

# 최종 파일 스냅샷: 내용이 바뀔 때만 data/processed/snapshots/에 날짜+해시 이름으로 보관, 최근 이만큼만 유지 (개당 약 21MB)
SNAPSHOT_KEEP = 10
