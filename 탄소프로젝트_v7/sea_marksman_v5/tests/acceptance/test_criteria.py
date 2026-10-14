"""5-2절 합격 기준 판정. 먼저 python tasks.py evaluate 를 실행한 뒤:  uv run pytest -m acceptance"""
import json

import pytest

from publish.artifacts import latest_dir

pytestmark = pytest.mark.acceptance


def _verdict():
    p = latest_dir() / "acceptance.json"
    if not p.exists():
        pytest.skip("acceptance.json 없음: python tasks.py evaluate 먼저")
    return json.loads(p.read_text(encoding="utf-8"))["verdict"]


@pytest.mark.parametrize("i", range(6))
def test_criterion(i):
    v = _verdict()[i]
    assert v["pass"], f"{v['criterion']}: {v['value']} (합격선 {v['threshold']})"
