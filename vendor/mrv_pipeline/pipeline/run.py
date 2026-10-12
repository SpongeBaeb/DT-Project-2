"""MRV 전처리 자동화 파이프라인 — 실행 진입점 (프로젝트 루트에서 실행)

    python -m pipeline.run --status          원본 파일 상태만 확인 (아무것도 바꾸지 않음)
    python -m pipeline.run --mode version    수시 버전 업데이트: 바뀐 연도만 다시 읽고 전체 규칙 재적용
    python -m pipeline.run --mode annual     6월 새 보고연도: 양식 점검 후 전체 재처리
    python -m pipeline.run --rollback        직전 실행 결과로 되돌리기
    (--no-fetch를 붙이면 MRV 사이트를 확인하지 않고 data/raw의 파일만 사용)
    (--crawl을 붙이면 제원 없는 선박을 VesselFinder에서 크롤링한 뒤 결합, --crawl-max N으로 척수 지정)

종료 코드: 0 성공(또는 변경 없음) / 1 오류 / 2 사람 확인이 필요해 멈춤 (양식 변경, 모드 불일치 등)
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import pickle
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import config, crawl, download, enrich, report, rules_mrv, snapshot, sources

log = logging.getLogger("pipeline")
EXIT_OK, EXIT_ERROR, EXIT_STOP = 0, 1, 2
MODE_LABEL = {"version": "버전 모드 (수시 업데이트)", "annual": "연간 모드 (새 보고연도)"}


class Stop(Exception):
    """사람 확인이 필요해 멈춤 (종료 코드 2)"""


def _has_parquet() -> bool:
    for mod in ("pyarrow", "fastparquet"):
        try:
            __import__(mod)
            return True
        except ImportError:
            pass
    return False


def _setup_logging(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    try:                                   # Windows 콘솔(cp949)에서 특수문자 때문에 멈추지 않도록
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    added = []
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(run_dir / "run.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
        added.append(h)
    return added


def _close_logging(handlers):
    """main()이 붙인 로그 핸들러를 떼고 닫음 (Windows에서 run.log가 잠긴 채 남거나, 같은 프로세스에서 다시 부를 때 로그가 중복되지 않도록)"""
    root = logging.getLogger()
    for h in handlers:
        root.removeHandler(h)
        h.close()


# ── 결과 쓰기 / 백업 / 되돌리기 ───────────────────────────────────────
def _backup_current(P):
    out, prev = P["out"], P["previous"]
    if prev.exists():
        shutil.rmtree(prev)
    if not (out / "_manifest.json").exists():   # 처음 실행 등 완성된 이전 결과가 없으면 백업하지 않음 (rollback이 빈 결과로 되돌리지 않게)
        return
    prev.mkdir(parents=True)
    for f in out.iterdir():
        if f.name in (prev.name, P["snapshots"].name):       # 스냅샷은 바뀌지 않는 기록이라 백업 대상 아님
            continue
        (shutil.copytree if f.is_dir() else shutil.copy2)(f, prev / f.name)


def rollback(P):
    out, prev = P["out"], P["previous"]
    if not (prev / "_manifest.json").exists():          # 매니페스트는 실행 마지막에 쓰므로, 없으면 완성된 백업이 아님
        log.error("되돌릴 직전 결과가 없거나 불완전함 (%s) — 현재 결과를 그대로 둠. "
                  "예전 데이터가 필요하면 data/processed/snapshots/의 스냅샷을 쓸 것", prev)
        return EXIT_ERROR
    for f in list(out.iterdir()):
        if f.name not in (prev.name, P["snapshots"].name):   # 스냅샷은 되돌리지 않고 그대로 둠
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    for f in prev.iterdir():
        (shutil.copytree if f.is_dir() else shutil.copy2)(f, out / f.name)
    log.info("직전 결과로 되돌림. 원본 폴더는 그대로이므로, 다음 실행 때 같은 새 버전을 다시 처리한다. "
             "구버전으로 계속 쓰려면 data/raw/archive/의 구버전 파일을 data/raw/로 옮기고 새 버전을 빼둘 것")
    return EXIT_OK


def _write(df, path, kind):
    tmp = path.with_name(path.name + ".tmp")
    if kind == "csv":
        df.to_csv(tmp, index=False, encoding=config.CSV_ENCODING)
    elif kind == "parquet":
        df.to_parquet(tmp, index=False)
    elif kind == "pkl":
        with open(tmp, "wb") as f:
            pickle.dump(df, f)
    tmp.replace(path)


def _file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _enrich_fingerprint(P) -> str:
    """제원 입력 파일과 결합 코드가 바뀌었는지 판단하기 위한 지문"""
    h = hashlib.sha256(_file_hash(Path(enrich.__file__)).encode())
    for d in (P["vf_dir"],):
        for f in sorted(x for x in d.glob("*.csv") if not x.name.startswith("_")) if d.exists() else []:
            h.update(f.name.encode() + sources.sha256(f).encode())
    return h.hexdigest()


def _add_file_cols(frame, info):
    """파이프라인이 붙이는 출처 버전 2열을 맨 끝에 추가 (노트북 열 순서는 그대로)"""
    f = frame.copy()
    f["mrv_file_version"] = f["source_file"].map(lambda n: f"v{info[n].version}" if n in info else None).astype("string")
    f["mrv_file_date"] = f["source_file"].map(lambda n: info[n].date if n in info else None).astype("string")
    return f


def _load_state(P, name):
    p = P["out"] / "_state" / f"{name}.pkl"
    if p.exists():
        with open(p, "rb") as f:
            return pickle.load(f)
    return None


# ── 메인 ─────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="MRV 전처리 자동화 파이프라인")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mode", choices=["version", "annual"])
    g.add_argument("--status", action="store_true", help="원본 파일 상태만 확인")
    g.add_argument("--rollback", action="store_true", help="직전 결과로 되돌리기")
    ap.add_argument("--accept-schema", action="store_true", help="양식 점검 경고를 확인했고 그대로 진행")
    ap.add_argument("--no-fetch", action="store_true", help="MRV 사이트를 확인하지 않고 data/raw의 파일만 사용")
    ap.add_argument("--crawl", action="store_true", help="제원이 없는 선박을 VesselFinder에서 크롤링한 뒤 결합")
    ap.add_argument("--crawl-max", type=int, default=None, help=f"이번에 크롤링할 최대 척수 (기본 {config.CRAWL_MAX_PER_RUN})")
    ap.add_argument("--root", help="프로젝트 루트 (기본: pipeline 폴더의 상위)")
    args = ap.parse_args(argv)

    if args.root:
        config.set_root(args.root)
    P = config.paths()
    started = datetime.now()
    mode = args.mode or ("rollback" if args.rollback else "status")
    run_dir = P["reports"] / f"{started:%Y%m%d_%H%M%S}_{mode}"
    handlers = _setup_logging(run_dir)
    try:
        ctx = {"mode_label": MODE_LABEL.get(mode, mode), "started": f"{started:%Y-%m-%d %H:%M:%S}", "warnings": []}

        if args.rollback:
            return rollback(P)

        t0 = time.time()
        try:
            code = _run(args, mode, P, ctx, run_dir)
            ctx["status"] = {EXIT_OK: "성공", EXIT_STOP: "확인 필요로 멈춤"}.get(code, "오류")
        except (Stop, rules_mrv.RuleCheckFailed) as e:
            if isinstance(e, rules_mrv.RuleCheckFailed):
                e = Stop(f"전처리 규칙 점검 실패(노트북이었다면 assert에서 멈췄을 상황): {e}")
            log.warning("멈춤: %s", e)
            ctx["warnings"].insert(0, str(e))
            ctx["status"], code = "확인 필요로 멈춤 — 출력 파일은 바뀌지 않음", EXIT_STOP
        except Exception as e:
            log.exception("파이프라인 오류")
            ctx["warnings"].insert(0, f"오류: {e!r}")
            ctx["status"], code = "오류 — 출력 파일은 바뀌지 않음", EXIT_ERROR
        if mode != "status":
            ctx["elapsed"] = time.time() - t0
            report.write_summary(run_dir / "summary.md", ctx)
            shutil.copy2(run_dir / "summary.md", P["reports"] / "latest_summary.md")
            log.info("리포트: %s", run_dir / "summary.md")
        return code
    finally:
        _close_logging(handlers)        # rollback으로 일찍 끝날 때도 run.log를 닫음


def _run(args, mode, P, ctx, run_dir):
    # 0) MRV 사이트에서 새 버전 확인·다운로드 (status는 확인만)
    if not args.no_fetch:
        local, _, _ = sources.discover(P["raw"]) if P["raw"].exists() else ({}, [], [])
        try:
            got, notes = download.fetch_updates(P["raw"], local, dry_run=(mode == "status"))
            for n in notes:
                log.info("사이트: %s", n)
            ctx["fetch"] = notes + ([f"내려받음: {', '.join(got)}"] if got else [])
            if mode == "status" and any("→" in n or "새 보고연도" in n for n in notes):
                log.info("→ 버전 모드(또는 새 연도면 연간 모드)로 실행하면 내려받아 처리한다")
        except Exception as e:
            log.warning("MRV 사이트 확인 실패: %s → data/raw의 파일 기준으로 진행", e)
            ctx["warnings"].append(f"MRV 사이트 확인 실패 — 최신 버전 여부를 모른 채 로컬 파일로 처리함 ({e})")

    # 1) 원본 파일 상태
    chosen, superseded, unknown = sources.discover(P["raw"])
    if not chosen:
        raise Stop(f"{P['raw']}에 '연도-v버전-날짜-....xlsx' 형식의 MRV 파일이 없음")
    for p in unknown:
        ctx["warnings"].append(f"이름 규칙에 맞지 않아 무시한 파일: {p.name}")
    hashes = {y: sources.sha256(rf.path) for y, rf in chosen.items()}
    manifest = sources.load_manifest(P["manifest"])
    det = sources.detect_changes(chosen, manifest, hashes)
    ctx["detect"] = det
    known = {int(y): v for y, v in manifest.get("years", {}).items()}
    ctx["file_changes"] = {y: (known[y]["file"], chosen[y].name) for y in det["changed"]}
    first_run = not known

    log.info("연도별 사용 파일: %s", {y: f"v{rf.version}" for y, rf in chosen.items()})
    log.info("새 연도 %s / 새 버전 %s / 그대로 %s%s", det["new"], det["changed"], det["unchanged"],
             f" / 구버전 {len(superseded)}개는 성공 후 archive로 이동" if superseded else "")
    if mode == "status":
        return EXIT_OK

    # 2) 모드 점검
    if det["removed"]:
        raise Stop(f"기록에는 있는데 파일이 없는 연도 {det['removed']} — data/raw를 확인할 것")
    if det["downgraded"]:
        raise Stop(f"기록된 버전보다 낮은 버전 파일이 있음 {det['downgraded']} — 실수로 넣은 구버전인지 확인")
    rules_hash = _file_hash(Path(rules_mrv.__file__))
    rules_changed = not first_run and manifest.get("rules_hash") != rules_hash
    mrv_changed = first_run or rules_changed or bool(det["new"] or det["changed"])
    if rules_changed:
        log.info("전처리 규칙(rules_mrv.py)이 바뀜 → 원본이 그대로여도 전체 규칙을 다시 적용")
        ctx["warnings"].append("rules_mrv.py가 지난 실행 이후 바뀌어 전체 재처리함 — 노트북과 비교 확인 권장")
    if first_run:
        log.info("처음 실행: 전체 연도를 처리해 기준 결과를 만든다")
    elif mode == "version" and det["new"]:
        raise Stop(f"새 보고연도 {det['new']} 파일이 있음 → 연간 모드(--mode annual)로 실행할 것")
    elif mode == "annual" and not det["new"]:
        raise Stop("새 보고연도 파일이 없음 → 버전 업데이트는 --mode version으로 실행할 것")

    # 3) 연간 모드: 새 연도 양식 점검
    if mode == "annual" and det["new"] and not first_run:
        lines, issues, blocking = [], [], []
        for y in det["new"]:
            same_fmt = [k for k in chosen if k < y and (k >= rules_mrv.NEW_FORMAT_FROM) == (y >= rules_mrv.NEW_FORMAT_FROM)]
            res = sources.schema_check(chosen[y], chosen[max(same_fmt)] if same_fmt else None)
            lines.append(f"{y}년 ({res['file']}) vs 비교 기준 {res['ref_file']}: 열 {res.get('n_columns')}개, "
                         f"추가 {res.get('added_vs_ref', [])}, 삭제 {res.get('removed_vs_ref', [])}")
            lines += [f"  ⛔ {i}" for i in res["blocking"]] + [f"  ⚠ {i}" for i in res["issues"]]
            issues += res["issues"]
            blocking += res["blocking"]
            if y > max(rules_mrv.Z):
                ctx["warnings"].append(f"10단계 CII 감축률 Z에 {y}년 값이 없어 {y}년분의 그해 기준 등급(cii_rating)이 비어 있음 "
                                       "— IMO가 정한 감축률을 rules_mrv.Z에 추가할 것 (2026년 기준 등급은 계산됨)")
            if y > rules_mrv.SCOPE_EXPANSION_YEAR:
                ctx["warnings"].append(
                    f"규칙 ⑥(신규 일반화물선 제외)은 {rules_mrv.SCOPE_EXPANSION_YEAR}년분에만 적용됨 → {y}년분 신규 "
                    "소형 일반화물선(400~5,000GT)이 걸러지지 않음. 팀에서 규칙을 정해 rules_mrv.limit_scope에 반영할 것")
        ctx["schema"] = lines
        if blocking:
            raise Stop("새 연도 파일에 매핑된 열·시트가 없음 — rules_mrv.COLUMN_MAP(노트북 2-1)을 새 양식에 맞게 고친 뒤 "
                       "다시 실행 (--accept-schema로는 넘어갈 수 없음)")
        if issues and not args.accept_schema:
            raise Stop("새 연도 양식이 직전 연도와 다름 — 리포트의 양식 점검을 확인하고, 매핑을 고치거나 "
                       "분석에 영향이 없으면 --accept-schema로 다시 실행")

    # 4) MRV 정제 1~8단계 (바뀐 연도만 엑셀을 다시 읽고, 규칙은 전체 연도에 다시 적용)
    prev_clean = _load_state(P, "mrv_clean")
    prev_merged = _load_state(P, "mrv_merged")
    info = {rf.name: rf for rf in chosen.values()}
    if mrv_changed:
        frames, partial, raw_diff_lines = {}, {}, []
        for y, rf in chosen.items():
            old_cache = sources.load_cached(P["cache"], y, known[y]["sha256"]) if y in det["changed"] else None
            frames[y], partial[y], hit = sources.read_year_cached(rf, hashes[y], P["cache"])
            if y in det["changed"] and old_cache is None:
                raw_diff_lines.append(f"{y}년 원본: 이전 버전 캐시가 없어 원본 단위 비교는 건너뜀 (결과 단위 비교는 아래)")
            if old_cache is not None:
                a, r, vc, per_col = report.compare_frames(old_cache["df"].drop(columns="source_file"),
                                                         frames[y].drop(columns="source_file"))
                raw_diff_lines.append(f"{y}년 원본: 추가 {len(a)}행, 삭제 {len(r)}행, 값이 바뀐 행 "
                                      f"{vc[['imo']].drop_duplicates().shape[0]}개 (열별: {dict(list(per_col.items())[:6])})")
        ctx["raw_diff"] = raw_diff_lines

        raw_all, clean, clog, by_year, rstats = rules_mrv.run_rules(frames, partial)
        empty = rstats["combine"]["unexpected_empty_columns"]
        if empty and not args.accept_schema:
            raise Stop(f"연도별로 통째로 비어 있는 매핑 열이 있음 {empty} — 헤더 매핑 오류 가능성 (노트북 2-3 점검)")
        k = rstats["keys"]
        if k["imo_not_7digits"] or k["imo_checksum_failed"] or rstats["combine"]["dup_imo_year"]:
            ctx["warnings"].append(f"키 점검(노트북 2-3·3-1): {k}, IMO+연도 중복 {rstats['combine']['dup_imo_year']}")
        clean61 = clean
        clean = _add_file_cols(clean61, info)
        col_dict = rules_mrv.column_dictionary(clean)
        ctx["cleaning_log"] = clog
        rr, cf = rstats["row_rules"], rstats["co2_fix"]
        ctx["rule_notes"] = [
            f"3-4 2배 오류: 후보 {cf['co2_fix_candidates']}행 중 보정 {cf['co2_fixed']}행, 보정 못 해 ⑤-4에서 제외 {cf['co2_not_recovered']}행",
            f"3-4 계수 반올림(3.21) 보정: {cf['co2_rounded_321_fixed'] or '없음'}",
            f"⑤-5 제외: {rr['rule55_removed'] or '없음'}",
            f"⑤-6 검토 대상(경유 계수 + 반올림 오차 초과, 남김): {rr['rule56_over_round_kept'] or '없음'} "
            "— 새 행이 생기면 예외 목록에 넣을지 팀에서 판단",
        ]
        log.info("정제 결과: %s행 × %s열, %s척", f"{len(clean):,}", clean.shape[1], f"{clean['imo'].nunique():,}")
    else:
        clean = prev_clean
        if clean is None:
            raise Stop("이전 정제 결과(_state)가 없음 — 처음이면 아무 모드로나 한 번 전체 실행할 것")
        clean61 = clean.drop(columns=[c for c in rules_mrv.PIPELINE_ADDED_COLS if c in clean.columns])
        col_dict = rules_mrv.column_dictionary(clean)

    # 4a) 제원 파일 준비: 없으면 파이프라인에 들어 있는 파일을 제자리(data/raw/vesselfinder/)에 복사
    seeded = enrich.ensure_spec_file(P)
    if seeded:
        log.info(seeded)
        ctx["warnings"].append(seeded)

    # 4b) VesselFinder 크롤링 (--crawl): 제원 없는 선박만, 결과는 data/raw/vesselfinder에 바로 저장
    if args.crawl:
        try:
            cs = crawl.run_crawl(clean, P, args.crawl_max or config.CRAWL_MAX_PER_RUN)
            ctx["crawl"] = [
                f"제원 없는 선박 중 지금 시도 가능 {cs['eligible']:,}척 → 이번에 {cs['planned']:,}척 시도: "
                f"성공 {cs['ok']}, 페이지에 제원 없음 {cs['no_data']}, 없는 선박(404) {cs['not_found']}, 오류 {cs['error']}",
                f"남은 대상 {cs['remaining']:,}척 (다음 --crawl 실행에서 이어서) / 재시도 대기 {cs['waiting_retry']}척 "
                f"/ {config.CRAWL_MAX_ATTEMPTS}번 실패해 포기 {cs['gave_up']}척",
            ]
            if cs["blocked"]:
                ctx["warnings"].append(f"VesselFinder가 요청을 막아({cs['blocked']}) 크롤링을 중간에 멈춤 — "
                                       "며칠 뒤 다시 실행하거나 --crawl-max를 줄일 것")
        except Exception as e:
            log.warning("크롤링 실패: %s → 기존 제원으로 계속", e)
            ctx["warnings"].append(f"크롤링 실패 — 기존 제원으로 처리함 ({e!r})")

    if not mrv_changed:
        if manifest.get("enrich_inputs") == _enrich_fingerprint(P):
            log.info("변경 없음 (MRV 원본·규칙·제원 파일 모두 그대로) → 결과를 바꾸지 않음")
            ctx["warnings"].append("변경 없음 — 출력 파일과 백업은 그대로")
            latest = P["out"] / "mrv_merged.parquet"
            if _has_parquet() and latest.exists():          # 스냅샷이 아직 없으면 지금 내용으로 하나 남김
                try:
                    msg = snapshot.save(latest, P["snapshots"], run_dir.name)
                    ctx["enrich"] = [msg]
                    log.info(msg)
                except Exception as e:
                    ctx["warnings"].append(f"스냅샷 저장 실패 ({e!r})")
            return EXIT_OK
        log.info("MRV 원본 변경 없음 → 제원 결합만 다시 만든다")

    # 5) 제원 통합·CII 등급 (노트북 9~10단계) → 통합 파일 (노트북 11-1)
    sp = enrich.spec_path(P)
    if not sp.exists():
        raise Stop(f"제원 파일이 없음: {sp} — 노트북 9단계의 입력. pipeline/seed/의 번들 파일도 없어 복사하지 못함 "
                   "(ship_data_detailed.csv를 이 위치에 둘 것)")
    merged61, mstats = rules_mrv.build_merged(clean61, sp)
    merged = _add_file_cols(merged61, info)
    merged_dict = rules_mrv.merged_column_dictionary(merged, col_dict)
    vfs, missing = enrich.spec_status(clean, P)
    s9, s10 = mstats["specs"], mstats["cii"]
    ctx["enrich"] = [
        f"제원: 정제 결과 {vfs['ships']:,}척 중 {s9['matched_ships']:,}척 매칭 (행 기준 {s9['row_match_rate']:.2%}), "
        f"제원 없음 {s9['mrv_only_ships']:,}척 {s9['no_spec_rows']:,}행 / 폭 오기재로 결측 처리 {len(s9['beam_set_missing'])}척 "
        f"/ 총톤수 5,000 미만 {s9['gt_below_5000_ships']}척 / 건조연도 > 보고연도 {s9['built_after_report_rows']}행",
        f"CII 등급: 그해 기준 {s10['rated_rows']:,}행, 2026년 기준 {s10['rated_2026basis_rows']:,}행 / 고속선 근사 {s10['hsc_ships']}척 "
        f"/ 선종 변경 표시 {s10['cii_type_changed_rows']}행 / 최근 연도 등급 분포 {s10['rating_latest_year']}",
        f"크롤링: 제원 파일에 없고 아직 시도 안 한 선박 {vfs['never_crawled']:,}척, 시도했지만 실패 {vfs['crawled_but_failed']:,}척",
        f"통합 파일: {merged.shape[0]:,}행 × {merged.shape[1]}열 (노트북 {merged.shape[1] - len(rules_mrv.PIPELINE_ADDED_COLS)}열 + 파이프라인 추가 {len(rules_mrv.PIPELINE_ADDED_COLS)}열: {', '.join(rules_mrv.PIPELINE_ADDED_COLS)})",
    ]
    if s9["no_spec_rows"] and not args.crawl:
        ctx["warnings"].append(f"제원이 없는 선박 {s9['mrv_only_ships']}척 {s9['no_spec_rows']}행은 CII 등급이 비어 있음 — "
                               "run_version_crawl.bat(--crawl)으로 실행하면 크롤링해서 채움")
    if vfs.get("crawled_but_failed") and not args.crawl:
        ctx["warnings"].append(f"크롤링을 시도했지만 제원이 없는 선박 {vfs['crawled_but_failed']}척 — --crawl로 실행하면 "
                               f"{config.CRAWL_RETRY_AFTER_DAYS}일 간격으로 최대 {config.CRAWL_MAX_ATTEMPTS}번까지 다시 시도함")

    # 6) 변경 비교 (통합 파일 기준 → 정제 값, 제원, CII 등급 변화까지)
    prev = prev_merged if prev_merged is not None else prev_clean
    if prev is not None:
        a, r, vc, per_col = report.compare_frames(prev, merged, ignore=("source_file", *rules_mrv.PIPELINE_ADDED_COLS))
        ctx["result_diff"] = {"added": len(a), "removed": len(r), "cells": len(vc),
                              "top_cols": dict(list(per_col.items())[:8])}
        rows = pd.concat([a.assign(change="추가"), r.assign(change="삭제")], ignore_index=True)
        rows.to_csv(run_dir / "row_changes.csv", index=False, encoding=config.CSV_ENCODING)
        vc.to_csv(run_dir / "value_changes.csv", index=False, encoding=config.CSV_ENCODING)
    if mrv_changed:
        ctx["year_table"] = report.year_summary(prev_clean, clean)
        flagged = ctx["year_table"].get("확인 필요")
        if flagged is not None and flagged.any():
            ctx["warnings"].append(f"행 수나 총 CO2가 {config.ALERT_ROWS_PCT}% 넘게 바뀐 연도: "
                                   f"{list(ctx['year_table'].index[flagged.fillna(False)])}")

    # 7) 쓰기: 직전 결과 백업 → 덮어쓰기
    out = P["out"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "_state").mkdir(exist_ok=True)
    _backup_current(P)
    parquet = _has_parquet()
    if not parquet:
        ctx["warnings"].append("pyarrow가 없어 parquet은 건너뛰고 csv만 저장함 (pip install pyarrow)")
    if mrv_changed:
        _write(clean, out / "_state" / "mrv_clean.pkl", "pkl")
        _write(clean, out / "mrv_clean.csv", "csv")
        _write(clog, out / "cleaning_log.csv", "csv")
        by_year.to_csv(out / "cleaning_by_year.csv", encoding=config.CSV_ENCODING)
        col_dict.to_csv(out / "column_dictionary.csv", encoding=config.CSV_ENCODING, index_label="열")
        if parquet:
            _write(clean, out / "mrv_clean.parquet", "parquet")
            _write(raw_all, out / "mrv_raw.parquet", "parquet")
    _write(merged, out / "_state" / "mrv_merged.pkl", "pkl")
    _write(merged, out / "mrv_merged.csv", "csv")
    merged_dict.to_csv(out / "column_dictionary_merged.csv", encoding=config.CSV_ENCODING, index_label="열")
    if parquet:
        _write(merged, out / "mrv_merged.parquet", "parquet")
        try:
            msg = snapshot.save(out / "mrv_merged.parquet", P["snapshots"], run_dir.name)
            ctx["enrich"].append(msg)
            log.info(msg)
        except Exception as e:                                # 스냅샷 실패가 결과 저장을 막지 않게
            ctx["warnings"].append(f"스냅샷 저장 실패 ({e!r}) — 최종 파일은 정상 저장됨")
    for old in ("ship_year_panel.csv", "ship_year_panel.parquet"):        # 이전 버전의 결과 파일 이름 (백업에는 남아 있음)
        if (out / old).exists():
            (out / old).unlink()
    written = enrich.write_missing_list(missing, P)
    ctx["enrich"].append(f"크롤링할 IMO 목록 {len(missing):,}개 → {', '.join(written)}")

    # 8) 기록 갱신: 매니페스트, 구버전 보관, data_sources.yaml
    if mrv_changed:
        manifest["years"] = {str(y): {"file": rf.name, "version": rf.version, "date": rf.date, "sha256": hashes[y],
                                      "rows_raw": int(frames[y].shape[0]), "rows_clean": int((clean["year"] == y).sum()),
                                      "processed_at": ctx["started"]} for y, rf in chosen.items()}
        sources.prune_cache(P["cache"], hashes)
        moved = sources.archive_superseded(superseded, P["raw_archive"])
        if moved:
            ctx["warnings"].append(f"구버전 파일을 data/raw/archive로 옮김: {moved}")
        for m in sources.sync_sources_yaml(P["sources_yaml"], chosen):
            if "직접" in m or "없음" in m:
                ctx["warnings"].append(f"data_sources.yaml: {m}")
            else:
                log.info("data_sources.yaml 갱신 %s", m)
    manifest["rules_hash"] = rules_hash
    manifest["enrich_inputs"] = _enrich_fingerprint(P)
    manifest.setdefault("runs", []).append({"at": ctx["started"], "mode": mode, "mrv_changed": mrv_changed,
                                            "rows": int(len(clean)), "report": run_dir.name})
    manifest["runs"] = manifest["runs"][-50:]
    sources.save_manifest(P["manifest"], manifest)
    log.info("완료: %s", out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
