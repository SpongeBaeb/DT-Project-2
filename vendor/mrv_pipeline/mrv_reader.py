"""파이프라인 결과(mrv_merged.parquet)를 읽는 도우미 — 피처·회귀 노트북에서 사용.

파이프라인은 실행할 때마다 결과를 같은 이름으로 덮어쓴다. 그래서 분석 노트북은
  1) 읽을 때 '어떤 데이터를 읽었는지'(원본 버전 + 내용 해시)를 기록하고
  2) 다음 단계에서 지금 파일이 그때와 같은지 대조해, 다르면 멈춘다.

    from mrv_reader import load_merged, check_same, save_meta

    # 1단계 노트북
    df, meta = load_merged()                      # 읽으면서 버전·해시 기록
    target_meta["mrv_source"] = meta              # 학습 쌍 파일의 메타에 함께 저장 (또는 save_meta)

    # 2단계 이후 노트북
    check_same("data/target_meta.json")           # 1단계 이후 데이터가 바뀌었으면 멈춤

    # 실험 입력을 특정 시점에 고정 (파이프라인이 다시 돌아도 바뀌지 않음)
    list_snapshots()                              # 보관 중인 스냅샷 목록
    df, meta = load_merged(snapshot="2026-10-06") # 날짜·해시 앞자리·파일명 일부로 지정

판정 기준은 내용 해시(data_hash)다. 원본 버전(mrv_file_version)은 사람이 읽는 용도 —
크롤링으로 제원이 채워지거나 전처리 규칙이 바뀌면 버전은 그대로여도 내용이 바뀌기 때문.
pandas와 pyarrow만 있으면 되고, 파이프라인 코드에 의존하지 않는다 (이 파일만 복사해 써도 됨).
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "processed" / "mrv_merged.parquet"
SNAPSHOT_DIR = DEFAULT_PATH.parent / "snapshots"


class DataChanged(Exception):
    """기록한 데이터와 지금 파일의 내용이 다름"""


def _read(path: Path):
    """파일을 한 번에 읽어 (바이트 해시, DataFrame) 반환 — 해시와 내용이 같은 순간의 파일에서 나오도록"""
    path = Path(path)
    if path.suffix == ".csv":
        raise ValueError("csv는 열 타입이 깨집니다 (company_imo 앞자리 0, True/False·정수 열). "
                         "같은 폴더의 mrv_merged.parquet을 읽으세요")
    raw = path.read_bytes()
    df = pd.read_pickle(io.BytesIO(raw)) if path.suffix == ".pkl" else pd.read_parquet(io.BytesIO(raw))
    return hashlib.sha256(raw).hexdigest(), df


def data_hash(df: pd.DataFrame) -> str:
    """내용 해시: 행 순서·열 이름·타입·값이 모두 같으면 같은 값 (파일 저장 방식과 무관)"""
    h = hashlib.sha256()
    h.update(json.dumps([[c, str(t)] for c, t in df.dtypes.items()]).encode())
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def _meta(path: Path, file_sha: str, df: pd.DataFrame) -> dict:
    ver = (df.groupby("year")[["mrv_file_version", "mrv_file_date"]].first()
           if {"mrv_file_version", "mrv_file_date"} <= set(df.columns) else pd.DataFrame())
    run = None
    manifest = path.parent / "_manifest.json"
    if manifest.exists():
        runs = json.loads(manifest.read_text(encoding="utf-8")).get("runs") or []
        run = runs[-1] if runs else None
    st = path.stat()
    dh = data_hash(df)
    snap = path if path.parent.name == "snapshots" else _find_snapshot(dh, path.parent / "snapshots")
    return {
        "source": str(path.resolve()),
        "data_hash": dh,
        "snapshot": str(snap) if snap else None,
        "file_sha256": file_sha,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "ships": int(df["imo"].nunique()) if "imo" in df else None,
        "versions": {str(int(y)): str(v) for y, v in ver.get("mrv_file_version", pd.Series(dtype=str)).items()},
        "version_dates": {str(int(y)): str(v) for y, v in ver.get("mrv_file_date", pd.Series(dtype=str)).items()},
        "file_modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "pipeline_run": run,
        "read_at": datetime.now().isoformat(timespec="seconds"),
    }


def _find_snapshot(h: str, snap_dir: Path):
    """내용 해시가 h인 스냅샷 파일 (없으면 None)"""
    if not snap_dir.exists():
        return None
    hits = sorted(snap_dir.glob(f"mrv_merged_*_{h[:8]}.parquet"))
    return hits[-1] if hits else None


def list_snapshots(snap_dir=None, quiet=False) -> pd.DataFrame:
    """보관 중인 스냅샷 목록 (오래된 순)"""
    snap_dir = Path(snap_dir or SNAPSHOT_DIR)
    idx = snap_dir / "index.csv"
    if idx.exists():
        t = pd.read_csv(idx, dtype=str, encoding="utf-8-sig")
    else:
        t = pd.DataFrame({"file": sorted(p.name for p in snap_dir.glob("mrv_merged_*.parquet"))})
    t = t[t["file"].map(lambda f: (snap_dir / f).exists())].reset_index(drop=True)
    if not quiet:
        cols = [c for c in ["file", "saved_at", "rows", "versions"] if c in t]
        print(t[cols].to_string(index=False) if len(t) else f"[mrv] 스냅샷 없음 ({snap_dir})")
    return t


def _resolve_snapshot(key: str, snap_dir: Path) -> Path:
    files = sorted(p for p in snap_dir.glob("mrv_merged_*.parquet") if key in p.name)
    if len(files) == 1:
        return files[0]
    names = [p.name for p in sorted(snap_dir.glob("mrv_merged_*.parquet"))]
    if not files:
        raise FileNotFoundError(f"'{key}'에 맞는 스냅샷이 없음 — 보관 중: {names}")
    raise ValueError(f"'{key}'에 맞는 스냅샷이 여러 개 — 해시 앞자리까지 지정하세요: {[p.name for p in files]}")


def load_merged(path=None, snapshot=None, quiet=False):
    """최종 파일을 읽고 (df, meta) 반환. meta는 JSON으로 저장할 수 있는 dict
    snapshot="2026-10-06" 또는 "3183d290"처럼 주면 그 스냅샷을 읽음 (실험 입력 고정)"""
    if snapshot:
        path = _resolve_snapshot(str(snapshot), Path(path).parent / "snapshots" if path else SNAPSHOT_DIR)
    path = Path(path or DEFAULT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음 — 파이프라인(run_version_crawl.bat)을 먼저 실행하세요")
    file_sha, df = _read(path)
    meta = _meta(path, file_sha, df)
    if not quiet:
        print(f"[mrv] {path.name}: {meta['rows']:,}행 × {meta['columns']}열, {meta['ships']:,}척 "
              f"(파일 수정 {meta['file_modified']})")
        print(f"[mrv] 원본 버전: {meta['versions']}")
        print(f"[mrv] 내용 해시: {meta['data_hash'][:16]}…")
        print(f"[mrv] 같은 내용의 스냅샷: {Path(meta['snapshot']).name}" if meta["snapshot"] else
              "[mrv] 같은 내용의 스냅샷 없음 (파이프라인을 다시 돌리면 생김)")
    return df, meta


def save_meta(meta: dict, path, extra: dict | None = None, key="mrv_source"):
    """meta를 JSON 파일에 저장. 파일이 이미 있으면 다른 내용은 두고 key 항목만 바꿈"""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc[key] = meta
    if extra:
        doc.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _recorded_meta(recorded, key):
    if isinstance(recorded, (str, Path)):
        recorded = json.loads(Path(recorded).read_text(encoding="utf-8"))
    if isinstance(recorded, dict) and key in recorded:
        recorded = recorded[key]
    if not isinstance(recorded, dict) or "data_hash" not in recorded:
        raise ValueError("기록에서 data_hash를 찾지 못함 — load_merged()가 돌려준 meta(또는 그것을 저장한 JSON)를 넘기세요")
    return recorded


def check_same(recorded, path=None, strict=True, key="mrv_source"):
    """기록한 데이터와 지금 파일이 같은지 대조.
    recorded: load_merged()의 meta, 그 meta를 담은 dict(예: target_meta), 또는 그 JSON 파일 경로.
    같으면 True. 다르면 strict=True일 때 DataChanged로 멈추고, False면 경고만 출력하고 False 반환."""
    rec = _recorded_meta(recorded, key)
    path = Path(path or rec.get("source") or DEFAULT_PATH)
    if not path.exists():
        hint = (" — 스냅샷 보관 개수(SNAPSHOT_KEEP)를 넘어 삭제됨. 1단계부터 다시 실행"
                if path.parent.name == "snapshots" else "")
        raise FileNotFoundError(f"{path} 없음{hint}")
    file_sha, df = _read(path)
    if file_sha == rec.get("file_sha256") or data_hash(df) == rec["data_hash"]:
        print(f"[mrv] ✅ 기록한 데이터와 같음 ({rec['rows']:,}행, 기록 시각 {rec.get('read_at')})")
        return True

    now = _meta(path, file_sha, df)
    lines = [f"[mrv] ❌ 기록한 데이터와 지금 파일이 다름 — 기록 {rec.get('read_at')} / 파일 수정 {now['file_modified']}",
             f"  행: {rec['rows']:,} → {now['rows']:,}, 선박: {rec.get('ships')} → {now['ships']}"]
    changed = {y: (rec["versions"].get(y), now["versions"].get(y))
               for y in sorted(set(rec.get("versions", {})) | set(now["versions"]))
               if rec["versions"].get(y) != now["versions"].get(y)}
    lines.append(f"  원본 버전 변화: {changed}" if changed else
                 "  원본 버전은 같음 → 크롤링으로 제원이 채워졌거나 전처리 규칙이 바뀐 경우 (파이프라인 리포트 확인)")
    if now.get("pipeline_run"):
        lines.append(f"  마지막 파이프라인 실행: {now['pipeline_run'].get('at')} (리포트 {now['pipeline_run'].get('report')})")
    snap = rec.get("snapshot")
    if snap and Path(snap).exists():
        lines.append(f"  기록한 데이터는 스냅샷으로 남아 있음 → load_merged(snapshot=\"{Path(snap).name[11:-8]}\")로 "
                     "읽으면 같은 데이터로 계속 진행 가능")
    lines.append("  → 1단계부터 다시 실행하거나, 의도한 변경이면 결과 폴더를 새 버전으로 만들어 진행")
    msg = "\n".join(lines)
    if strict:
        raise DataChanged(msg)
    print(msg)
    return False
