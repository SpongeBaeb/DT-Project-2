import numpy as np
import pandas as pd
import pytest

from contracts.schema import Column, ContractError, TableSchema
from contracts.tables import CONTRIB_COLS, RESULT_TABLE, SHIP_YEAR

T = TableSchema("t", "1.0", ("k",), (Column("k", "int", nullable=False), Column("v", "float", min=0)))


def test_validate_passes_and_orders():
    df = pd.DataFrame({"v": [1.0, 2.0], "k": [1, 2]})
    assert list(T.validate(df).columns) == ["k", "v"]


@pytest.mark.parametrize("df, msg", [
    (pd.DataFrame({"k": [1]}), "빠진 열"),
    (pd.DataFrame({"k": [1, 1], "v": [1.0, 2.0]}), "중복"),
    (pd.DataFrame({"k": [1], "v": [-1.0]}), "미만"),
    (pd.DataFrame({"k": [None, 2], "v": [1.0, 1.0]}), "빈칸"),
    (pd.DataFrame({"k": [1], "v": [np.inf]}), "inf"),
    (pd.DataFrame({"k": [1], "v": ["a"]}), "종류"),
])
def test_validate_catches(df, msg):
    with pytest.raises(ContractError, match=msg):
        T.validate(df)


def test_forbid_extra():
    with pytest.raises(ContractError, match="약속에 없는 열"):
        T.validate(pd.DataFrame({"k": [1], "v": [1.0], "x": [0]}), extra="forbid")


def test_contracts_are_well_formed():
    for t in (SHIP_YEAR, RESULT_TABLE):
        assert len(set(t.names)) == len(t.names), f"{t.name} 열 이름 중복"
        assert all(k in t.names for k in t.key)
    assert set(CONTRIB_COLS) <= set(RESULT_TABLE.names)


def test_snapshot_meets_contract(snapshot):
    SHIP_YEAR.validate(snapshot)
