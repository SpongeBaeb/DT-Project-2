"""원본 MRV 파일 관리.

- 연도별로 가장 높은 버전 파일 선택, 같은 연도의 구버전은 성공 후 data/raw/archive/ 로 이동
  (노트북 1-1은 연도별 파일이 하나여야 하므로)
- 매니페스트(data/processed/_manifest.json)와 비교해 새 연도 / 바뀐 연도 판단
- 연도별 읽기 결과를 캐시 → 바뀐 연도만 엑셀을 다시 읽음 (한 파일에 수십 초)
- config/data_sources.yaml 의 파일명을 새 버전으로 바꿔 노트북 1-1 대조와 맞춤
- 연간 모드의 양식 점검 (노트북 1-4와 같은 방식)
"""
from __future__ import annotations

import hashlib
import json
import logging
import pickle
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import config, rules_mrv

log = logging.getLogger("pipeline.sources")


@dataclass
class RawFile:
    year: int
    version: int
    date: str          # 파일명의 생성일 (YYYY-MM-DD)
    path: Path

    @property
    def name(self):
        return self.path.name


def parse_name(path: Path):
    m = re.match(config.FILE_PATTERN, path.name)
    if not m:
        return None
    d = m.group("date")                                  # ddmmyyyy
    return RawFile(int(m.group("year")), int(m.group("version")), f"{d[4:]}-{d[2:4]}-{d[:2]}", path)


def discover(raw_dir: Path):
    """반환: ({연도: 최신 RawFile}, [같은 연도의 구버전 RawFile], [이름 규칙에 안 맞는 xlsx])"""
    by_year, unknown = {}, []
    for p in sorted(raw_dir.glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        rf = parse_name(p)
        if rf is None or rf.year < config.FIRST_YEAR:
            unknown.append(p)
            continue
        by_year.setdefault(rf.year, []).append(rf)
    chosen, superseded = {}, []
    for y, files in by_year.items():
        files.sort(key=lambda f: (f.version, f.date))
        chosen[y] = files[-1]
        superseded += files[:-1]
    return dict(sorted(chosen.items())), superseded, unknown


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 매니페스트 ───────────────────────────────────────────────────────
def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"years": {}, "runs": []}


def save_manifest(path: Path, manifest: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def detect_changes(chosen: dict, manifest: dict, hashes: dict):
    known = {int(y): v for y, v in manifest.get("years", {}).items()}
    new = [y for y in chosen if y not in known]
    changed, downgraded = [], []
    for y, rf in chosen.items():
        if y in known and (rf.name != known[y]["file"] or hashes[y] != known[y]["sha256"]):
            (downgraded if rf.version < known[y]["version"] else changed).append(y)
    removed = [y for y in known if y not in chosen]
    return {"new": new, "changed": changed, "downgraded": downgraded, "removed": removed,
            "unchanged": [y for y in chosen if y not in new + changed + downgraded]}


# ── 연도별 읽기 + 캐시 ───────────────────────────────────────────────
def _cache_path(cache_dir: Path, year: int, file_hash: str) -> Path:
    return cache_dir / f"mrv_std_{year}_{file_hash[:16]}.pkl"


def load_cached(cache_dir: Path, year: int, file_hash: str):
    p = _cache_path(cache_dir, year, file_hash)
    if p.exists():
        with open(p, "rb") as f:
            cached = pickle.load(f)
        if cached.get("rules_version") == RULES_FINGERPRINT:
            return cached
    return None


def read_year_cached(rf: RawFile, file_hash: str, cache_dir: Path):
    """같은 파일(해시)의 캐시가 있으면 사용, 없으면 엑셀을 읽고 캐시 저장. 반환 (df, partial_imos, 캐시 사용 여부)"""
    cached = load_cached(cache_dir, rf.year, file_hash)
    if cached:
        return cached["df"], cached["partial"], True
    log.info("엑셀 읽기: %s (수십 초 걸릴 수 있음)", rf.name)
    df = rules_mrv.read_year(rf.year, rf.path)
    partial = rules_mrv.read_partial_imos(rf.year, rf.path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = _cache_path(cache_dir, rf.year, file_hash)
    tmp = dest.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump({"file": rf.name, "sha256": file_hash, "rules_version": RULES_FINGERPRINT,
                     "df": df, "partial": partial}, f)
    tmp.replace(dest)
    return df, partial, False


def prune_cache(cache_dir: Path, hashes: dict):
    """성공 후, 지금 쓰는 파일이 아닌 캐시 삭제"""
    keep = {_cache_path(cache_dir, y, h).name for y, h in hashes.items()}
    for p in cache_dir.glob("mrv_std_*.pkl"):
        if p.name not in keep:
            p.unlink()


def _rules_fingerprint() -> str:
    """read_year에 영향을 주는 매핑이 바뀌면 캐시를 무효화하기 위한 지문"""
    src = json.dumps([rules_mrv.COLUMN_MAP, rules_mrv.OLD_HEADER_ALIASES, rules_mrv.NEW_FORMAT_FROM,
                      rules_mrv.TEXT_COLS], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(src.encode()).hexdigest()[:12]


RULES_FINGERPRINT = _rules_fingerprint()


# ── 연간 모드: 양식 점검 (노트북 1-2, 1-4) ───────────────────────────
def read_headers(rf: RawFile):
    with pd.ExcelFile(rf.path) as xls:
        sheets = xls.sheet_names
        sheet = rules_mrv.sheet_for(rf.year)
        if isinstance(sheet, str) and sheet not in sheets:
            return sheets, None
        cols = list(xls.parse(sheet, header=2, nrows=0).columns)
    return sheets, [rules_mrv.OLD_HEADER_ALIASES.get(c, c) for c in cols]


def schema_check(new_rf: RawFile, ref_rf: RawFile | None) -> dict:
    """새 연도 파일을 같은 양식의 직전 연도 파일과 비교. issues가 비어 있으면 통과."""
    res = {"year": new_rf.year, "file": new_rf.name, "ref_file": ref_rf.name if ref_rf else None,
           "blocking": [], "issues": []}   # blocking = 매핑을 고쳐야 함 / issues = 확인 후 --accept-schema 가능
    sheets, cols = read_headers(new_rf)
    res["sheets"] = sheets
    if new_rf.year >= rules_mrv.NEW_FORMAT_FROM:
        for s in (f"{new_rf.year} Full ERs", f"{new_rf.year} Partial ERs"):
            if s not in sheets:
                res["blocking"].append(f"시트 '{s}' 없음 (시트 목록: {sheets})")
    if cols is None:
        return res
    res["n_columns"] = len(cols)

    new = new_rf.year >= rules_mrv.NEW_FORMAT_FROM
    for std, (old_h, new_h) in rules_mrv.COLUMN_MAP.items():
        h = new_h if new else old_h
        if h is not None and h not in cols:
            res["blocking"].append(f"매핑 열 없음: '{h}' (표준명 {std}) → rules_mrv.COLUMN_MAP 수정 필요")

    if ref_rf is not None:
        _, ref_cols = read_headers(ref_rf)
        res["added_vs_ref"] = [c for c in cols if c not in ref_cols]
        res["removed_vs_ref"] = [c for c in ref_cols if c not in cols]
        res["renamed_same_position"] = [(a, b) for a, b in zip(ref_cols, cols) if a != b]
        if res["added_vs_ref"] or res["removed_vs_ref"]:
            res["issues"].append(f"직전 연도 대비 열 추가 {len(res['added_vs_ref'])}개 / 삭제 {len(res['removed_vs_ref'])}개 "
                                 "(분석에 안 쓰는 열이면 --accept-schema 로 진행)")
    return res


# ── 성공 후 정리 ─────────────────────────────────────────────────────
def archive_superseded(superseded: list, archive_dir: Path):
    moved = []
    for rf in superseded:
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / rf.name
        if dest.exists():
            dest = archive_dir / f"{rf.path.stem}_{datetime.now():%Y%m%d%H%M%S}{rf.path.suffix}"
        shutil.move(str(rf.path), str(dest))
        moved.append(rf.name)
    return moved


def sync_sources_yaml(yaml_path: Path, chosen: dict) -> list[str]:
    """data_sources.yaml 안의 파일명만 문자열로 바꿔 주석·서식을 보존. 새 연도는 추가할 내용을 안내만 한다."""
    msgs = []
    if not yaml_path.exists():
        return [f"{yaml_path} 없음 → 동기화 건너뜀"]
    import yaml

    text = yaml_path.read_text(encoding="utf-8")
    recorded = (yaml.safe_load(text) or {}).get("files", {}) or {}
    recorded = {int(k): v for k, v in recorded.items()}
    new_text = text
    for y, rf in chosen.items():
        old = (recorded.get(y) or {}).get("file")
        if old is None:
            msgs.append(f"{y}년 항목이 data_sources.yaml에 없음 → 직접 추가 필요 (file: \"{rf.name}\")")
        elif old != rf.name:
            if old in new_text:
                new_text = new_text.replace(old, rf.name)
                msgs.append(f"{y}년: {old} → {rf.name}")
            else:
                msgs.append(f"{y}년: 기록된 파일명 '{old}'를 문서에서 찾지 못해 직접 수정 필요")
    if new_text != text:
        shutil.copy2(yaml_path, yaml_path.with_suffix(".yaml.bak"))
        yaml_path.write_text(new_text, encoding="utf-8")
    return msgs
