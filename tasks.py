"""Sea Marksman 실행 명령 (Windows·Mac 공통). 모든 명령은 프로젝트 루트에서.

  uv run python tasks.py all         # 처음부터 끝까지: pipeline → build → schema → test
  uv run python tasks.py pipeline    # ① 데이터 → data/snapshots/ship_year.parquet
  uv run python tasks.py build       # ② 학습 → artifacts/<버전>/ (모델 파일·결과 표·웹 JSON)
  uv run python tasks.py evaluate    # ③ 5-2절 합격 기준 판정표 → artifacts/<버전>/acceptance.md
  uv run python tasks.py schema      # 약속 문서(docs/contracts.md)·OpenAPI·웹 타입 다시 만들기
  uv run python tasks.py dev         # API + 웹 함께 켜기  →  http://localhost:5173  (끄기: Ctrl+C)
  uv run python tasks.py serve       # 진단 API만  http://localhost:8000/docs
  uv run python tasks.py test        # 테스트 (합격 기준 제외)

옵션: --config config/다른설정.yaml
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time

from shared.config import ROOT, load_config, load_yaml


def cmd_pipeline(cfg, args):
    from pipeline.run import run
    print(f"[pipeline] 완료 → {run(cfg)}")


def cmd_build(cfg, args):
    from publish.artifacts import build
    out = build(cfg)
    print(f"[build] 완료 → {out.relative_to(ROOT)}  (web/public/data 에도 복사)")


def cmd_evaluate(cfg, args):
    from evaluation.report import evaluate
    from pipeline.run import load_snapshot
    from publish.artifacts import latest_dir
    rep = evaluate(load_snapshot(cfg), cfg, load_yaml("config/acceptance.yaml"), latest_dir())
    print((latest_dir() / "acceptance.md").read_text(encoding="utf-8"))
    print(f"통과 {sum(r['pass'] for r in rep['verdict'])}/{len(rep['verdict'])}")


def cmd_schema(cfg, args):
    from pydantic.json_schema import models_json_schema

    from api.main import app
    from contracts.api import IndexEntry, ShipFile
    from contracts.tables import ALL_TABLES, CAUSE_FACTORS
    gen = ROOT / "contracts" / "generated"
    gen.mkdir(exist_ok=True)
    spec = app.openapi()
    # 정적 JSON 파일 모양도 웹 타입으로 내보낸다 (API 경로에는 안 나오므로 직접 추가)
    _, extra = models_json_schema([(m, "validation") for m in (ShipFile, IndexEntry)], ref_template="#/components/schemas/{model}")
    spec["components"]["schemas"].update(extra["$defs"])
    (gen / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    doc = ["# 형식 약속서 (자동 생성: python tasks.py schema — 직접 고치지 말 것)", "",
           "원본: `contracts/tables.py`, `contracts/api.py`. 바꾸면 버전을 올리고 받는 사람에게 알린다.", ""]
    doc += [t.to_markdown() for t in ALL_TABLES]
    doc += ["## 원인 막대 요인", "", "| 코드 | 화면 이름 |", "|---|---|"] + [f"| `{k}` | {v} |" for k, v in CAUSE_FACTORS.items()]
    doc += ["", "## API", "", "`contracts/generated/openapi.json` 또는 서버 실행 후 http://localhost:8000/docs", ""]
    (ROOT / "docs" / "contracts.md").write_text("\n".join(doc), encoding="utf-8")
    print("[schema] docs/contracts.md, contracts/generated/openapi.json")
    npm = shutil.which("npm")
    if npm and (ROOT / "web" / "node_modules").exists():
        subprocess.run([npm, "run", "gen:types"], cwd=ROOT / "web", check=True)
        print("[schema] web/src/api/schema.d.ts")
    else:
        print("[schema] web/node_modules 없음 → 웹 타입 생성 건너뜀 (cd web && npm install 후 다시)")


def cmd_serve(cfg, args):
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=args.port, reload=False)


def cmd_dev(cfg, args):
    """API(8000)와 웹(5173)을 함께 켠다. Ctrl+C 한 번으로 둘 다 끈다."""
    from publish.artifacts import latest_dir
    try:
        latest_dir()
    except FileNotFoundError:
        print("[dev] 산출물이 없어 먼저 만듭니다 (pipeline → build)")
        cmd_pipeline(cfg, args)
        cmd_build(cfg, args)
    npm = shutil.which("npm")
    if not npm:
        sys.exit("[dev] npm 이 없습니다. Node.js 를 설치하세요")
    if not (ROOT / "web" / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=ROOT / "web", check=True)
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT),
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "web"),
    ]
    print(f"\n[dev] 웹  http://localhost:5173   ·   API 문서  http://localhost:{args.port}/docs   (끄기: Ctrl+C)\n")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        print("[dev] 서버 하나가 멈췄습니다. 위쪽 오류를 확인하세요.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


def cmd_test(cfg, args):
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", *args.rest], cwd=ROOT))


def cmd_all(cfg, args):
    for name in ("pipeline", "build", "schema"):
        t = time.perf_counter()
        COMMANDS[name](cfg, args)
        print(f"  ({time.perf_counter() - t:.1f}s)")
    cmd_test(cfg, args)


COMMANDS = {
    "pipeline": cmd_pipeline, "build": cmd_build, "evaluate": cmd_evaluate, "schema": cmd_schema,
    "serve": cmd_serve, "dev": cmd_dev, "test": cmd_test, "all": cmd_all,
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=COMMANDS)
    p.add_argument("--config", default=None)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("rest", nargs="*", help="test 명령에 넘길 pytest 인자")
    args = p.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="  %(name)s | %(message)s")
    COMMANDS[args.command](load_config(args.config), args)


if __name__ == "__main__":
    main()
