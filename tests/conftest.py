"""테스트 공통 준비: 임시 폴더에 합성 표본 → 파이프라인 → 모델 학습. artifacts/ 상태와 무관하게 돈다."""
from __future__ import annotations

import copy

import pytest

from models.bundle import ModelBundle
from pipeline.run import load_snapshot, run
from shared.config import load_config


@pytest.fixture(scope="session")
def cfg(tmp_path_factory):
    c = copy.deepcopy(load_config())
    tmp = tmp_path_factory.mktemp("sm")
    c["data"].update(source="sample", raw_dir=str(tmp / "raw"), snapshot_dir=str(tmp / "snap"), cache_dir=str(tmp / "cache"))
    return c


@pytest.fixture(scope="session")
def snapshot(cfg):
    run(cfg)
    return load_snapshot(cfg)


@pytest.fixture(scope="session")
def bundle(snapshot, cfg):
    return ModelBundle.train(snapshot, cfg)


@pytest.fixture(scope="session")
def results(bundle, snapshot):
    return bundle.run(snapshot)
