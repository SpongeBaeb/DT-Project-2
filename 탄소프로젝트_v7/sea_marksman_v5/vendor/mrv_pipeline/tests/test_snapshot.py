"""스냅샷 테스트 — 내용이 바뀔 때만 날짜+해시 이름으로 보관되고, 노트북에서 고정해 읽을 수 있는지.

    python tests/test_snapshot.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mrv_reader as R  # noqa: E402
from pipeline import config, run  # noqa: E402


def _use_pickle_as_parquet():
    """parquet 엔진(pyarrow)이 없는 환경에서도 시험할 수 있게 parquet 읽기·쓰기를 pickle로 대신"""
    try:
        import pyarrow  # noqa: F401
        return
    except ImportError:
        pd.DataFrame.to_parquet = lambda self, path, index=False, **k: self.to_pickle(path)
        pd.read_parquet = lambda path, **k: pd.read_pickle(path)
        run._has_parquet = lambda: True


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


def main():
    ok = True
    _use_pickle_as_parquet()
    with tempfile.TemporaryDirectory() as t:
        config.SEED_DIR = Path(t) / "no_seed"        # 합성 데이터에 실제 번들 제원이 섞이지 않게
        proj = Path(t) / "proj"
        gen = [sys.executable, str(ROOT / "tests" / "make_synthetic_raw.py"), str(proj)]
        subprocess.run(gen, check=True, capture_output=True)
        latest = proj / "data/processed/mrv_merged.parquet"
        snaps = proj / "data/processed/snapshots"
        pipe = lambda *a: run.main(["--mode", "version", "--root", str(proj), "--no-fetch", *a])  # noqa: E731

        # 1) 첫 실행 → 스냅샷 1개, 최신 파일과 같은 내용
        pipe()
        df1, m1 = R.load_merged(latest, quiet=True)
        files = sorted(snaps.glob("mrv_merged_*.parquet"))
        ok &= check("첫 실행: 스냅샷 1개 (이름 = 날짜 + 내용 해시 앞 8자리)",
                    len(files) == 1 and files[0].name.endswith(f"_{m1['data_hash'][:8]}.parquet"))
        ok &= check("최신 파일을 읽으면 같은 내용의 스냅샷을 알려 줌", m1["snapshot"] and Path(m1["snapshot"]).name == files[0].name)

        # 2) 내용이 같으면 새로 만들지 않음 (규칙 지문을 지워 강제로 다시 처리)
        import json
        mf = proj / "data/processed/_manifest.json"
        man = json.loads(mf.read_text(encoding="utf-8")); man.pop("rules_hash"); mf.write_text(json.dumps(man), encoding="utf-8")
        pipe()
        ok &= check("다시 처리했지만 내용이 같으면 스냅샷을 새로 만들지 않음", len(list(snaps.glob("mrv_merged_*.parquet"))) == 1)

        # 3) MRV 새 버전 → 내용이 바뀌어 스냅샷 2개
        subprocess.run(gen + ["--add-version", "2025"], check=True, capture_output=True)
        pipe()
        ok &= check("새 버전 반영: 스냅샷 2개 + 목록(index.csv)", len(list(snaps.glob("mrv_merged_*.parquet"))) == 2
                    and len(R.list_snapshots(snaps, quiet=True)) == 2)

        # 4) 예전 데이터를 스냅샷으로 그대로 다시 읽기
        key = m1["data_hash"][:8]
        old, m_old = R.load_merged(latest, snapshot=key, quiet=True)
        ok &= check("load_merged(snapshot=해시 앞자리)로 예전 데이터를 그대로 읽음", old.equals(df1) and m_old["data_hash"] == m1["data_hash"])
        try:
            R.check_same(m1)
            ok &= check("최신 파일 기준 기록은 바뀌었다고 멈춤", False)
        except R.DataChanged as e:
            ok &= check("최신 파일 기준 기록은 멈추고, 스냅샷으로 이어 갈 방법을 안내", "load_merged(snapshot=" in str(e))
        ok &= check("스냅샷으로 고정한 기록은 파이프라인이 다시 돌아도 통과", R.check_same(m_old) is True)

        # 5) 보관 개수 제한
        config.SNAPSHOT_KEEP = 2
        spec = proj / "data/raw/vesselfinder/ship_data_detailed.csv"
        s = pd.read_csv(spec, dtype={"IMO": str}); s.loc[0, "Gross Tonnage"] += 1; s.to_csv(spec, index=False)   # 제원만 바뀜
        pipe()
        names = sorted(p.name for p in snaps.glob("mrv_merged_*.parquet"))
        ok &= check("보관 개수를 넘으면 가장 오래된 스냅샷 삭제", len(names) == 2 and not any(key in n for n in names))

        # 6) 되돌리기는 스냅샷을 건드리지 않음
        before = sorted(p.name for p in snaps.iterdir())
        cur_hash = R.load_merged(latest, quiet=True)[1]["data_hash"]
        code = run.main(["--rollback", "--root", str(proj)])
        ok &= check("--rollback 후에도 스냅샷은 그대로", sorted(p.name for p in snaps.iterdir()) == before)
        ok &= check("--rollback은 직전 실행 결과로 되돌림", code == 0 and latest.exists()
                    and R.load_merged(latest, quiet=True)[1]["data_hash"] != cur_hash)

        # 7) 완성된 백업이 없으면 되돌리지 않음 (처음 실행 직후 등)
        with tempfile.TemporaryDirectory() as t2:
            p2 = Path(t2) / "proj"
            subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_raw.py"), str(p2)], check=True, capture_output=True)
            run.main(["--mode", "version", "--root", str(p2), "--no-fetch"])
            out2 = p2 / "data/processed"
            code = run.main(["--rollback", "--root", str(p2)])
            ok &= check("처음 실행 직후 --rollback은 멈추고 현재 결과를 그대로 둠 (종료 코드 1)",
                        code == 1 and (out2 / "mrv_merged.parquet").exists() and (out2 / "_manifest.json").exists())

    print("스냅샷:", "✅ 모두 통과" if ok else "❌ 실패 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    sys.exit(main())
