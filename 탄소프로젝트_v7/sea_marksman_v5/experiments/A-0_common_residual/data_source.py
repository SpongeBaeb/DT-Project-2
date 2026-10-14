"""데이터를 읽는 단 하나의 입구. 모든 데이터 생성 코드와 실험은 여기서 MRV 데이터를 받는다.

원본: MRV 전처리 파이프라인의 최종 파일 (mrv_pipeline/data/processed/mrv_merged.parquet)
  - 파이프라인 위치는 환경변수 MRV_PIPELINE 으로 바꿀 수 있다. 없으면 아래 DEFAULT_PIPELINE.
  - 파이프라인의 mrv_reader.load_merged 로 읽어, 원본 버전과 내용 해시(meta)를 함께 돌려준다.
    결과 파일(json)의 meta 에 source() 를 넣어 두면 어떤 데이터로 만들었는지 나중에 대조할 수 있다.
  - 실험 입력을 고정하려면 snapshot="3183d290" 처럼 스냅샷 해시를 준다.

사용:
    from data_source import load, source
    df, meta = load()            # imo 는 int 로 바꿔서 준다
    out["meta"]["data"] = source(meta)
"""
import os
import sys
from pathlib import Path

DEFAULT_PIPELINE = Path(r"C:\Users\samsung\Desktop\ship image\mrv_pipeline_2026-10-07_2\mrv_pipeline")
PIPELINE = Path(os.environ.get("MRV_PIPELINE", DEFAULT_PIPELINE))
MERGED = PIPELINE / "data" / "processed" / "mrv_merged.parquet"


def load(snapshot=None, quiet=True):
    """(DataFrame, meta). imo 를 int 로 바꾼다 (파이프라인 parquet 은 문자열)."""
    if not (PIPELINE / "mrv_reader.py").exists():
        raise FileNotFoundError(f"MRV 파이프라인을 찾을 수 없습니다: {PIPELINE}  (환경변수 MRV_PIPELINE 으로 위치 지정)")
    sys.path.insert(0, str(PIPELINE))
    from mrv_reader import load_merged  # noqa: E402
    df, meta = load_merged(MERGED, snapshot=snapshot, quiet=quiet)
    df = df.copy()
    df["imo"] = df["imo"].astype(int)
    return df, meta


def source(meta: dict) -> dict:
    """결과 파일에 남길 출처 요약: 파일, 원본 연도별 버전, 내용 해시 앞 8자리."""
    return {
        "file": "mrv_pipeline/data/processed/mrv_merged.parquet",
        "versions": meta.get("versions"),
        "data_hash": str(meta.get("data_hash", ""))[:8],
        "rows": meta.get("rows"),
        "ships": meta.get("ships"),
    }
