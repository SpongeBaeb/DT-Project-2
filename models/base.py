"""모델 부품(Stage) 규칙. 모든 모델 담당자는 이 규칙만 지키면 서로의 코드를 몰라도 맞물린다.

    class 내모델(Stage):
        requires = ("sea_eff_kg_nm", "size_bin")     # 이 열이 있어야 돌 수 있음 (앞 부품이 만든 열 포함)
        produces = ("sea_eff_expected", ...)         # 정확히 이 열들을 돌려줌

        def fit(self, train, ctx):   # train = 학습 기간 행만. 배운 값은 self 에 저장 (joblib 로 통째로 저장됨)
            ...
            return self

        def transform(self, df):     # df = 진단할 행들 (같은 배의 여러 해 포함). index 를 그대로 유지
            return pd.DataFrame({...}, index=df.index)

지켜야 할 것
1. transform 은 행 순서·index 를 바꾸지 않는다. 행을 버리지 않는다.
2. 한 배의 값은 **그 배의 행만으로** 계산된다 (다른 배 행이 섞여 있어도, 빠져 있어도 결과가 같아야 함).
   → API(한 척)와 결과 표(전체)가 같은 값을 내는 조건. tests/parity 가 확인한다.
3. 같은 배의 이전 연도 값은 써도 되지만 **미래 연도 값은 쓰지 않는다**.
4. 연도 효과는 year 대신 year_eff 를 쓴다 (학습에 없는 연도는 마지막 학습 연도로 맞춰져 있음).
5. 숫자 기준은 ctx.thresholds / self.params 에서 받는다 (코드에 박지 않기).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd


@dataclass
class FitContext:
    cutoff_year: int | None
    seed: int
    thresholds: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)


class Stage(ABC):
    requires: ClassVar[tuple[str, ...]] = ()
    produces: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **params: Any):
        self.params = params
        self.thresholds: dict[str, Any] = {}

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "Stage":
        self.thresholds = ctx.thresholds
        return self

    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame: ...

    @property
    def name(self) -> str:
        return f"{type(self).__module__}:{type(self).__name__}"

    def describe(self) -> dict[str, Any]:
        return {"use": self.name, "params": self.params}
