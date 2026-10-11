"""표 약속을 코드로 적고 검사하는 작은 도구.

표마다 열 이름·종류·단위·빈칸 허용·값 범위를 한 번 적어 두면
- validate(): 넘겨받은 표가 약속을 지키는지 검사 (어기면 무엇이 틀렸는지 전부 모아 알려 줌)
- to_markdown(): 사람이 읽는 형식 약속서(docs/contracts.md) 생성
에 함께 쓰인다. 외부 라이브러리 없이 pandas만 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

KINDS = ("int", "float", "str", "bool")


class ContractError(ValueError):
    """표가 약속을 어겼을 때. problems 에 위반 목록이 들어 있다."""

    def __init__(self, table: str, problems: list[str]):
        self.problems = problems
        super().__init__(f"[{table}] 약속 위반 {len(problems)}건:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    unit: str = ""
    desc: str = ""
    nullable: bool = True
    min: float | None = None
    max: float | None = None

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind는 {KINDS} 중 하나")


def _kind_ok(s: pd.Series, kind: str) -> bool:
    if kind == "int":
        return ptypes.is_integer_dtype(s) or (ptypes.is_float_dtype(s) and bool(np.all(s.dropna() % 1 == 0)))
    if kind == "float":
        return ptypes.is_numeric_dtype(s) and not ptypes.is_bool_dtype(s)
    if kind == "bool":
        return ptypes.is_bool_dtype(s)
    return ptypes.is_string_dtype(s) or ptypes.is_object_dtype(s) or s.isna().all()


@dataclass(frozen=True)
class TableSchema:
    name: str
    version: str
    key: tuple[str, ...]
    columns: tuple[Column, ...]
    desc: str = ""

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)

    def validate(self, df: pd.DataFrame, *, extra: str = "allow") -> pd.DataFrame:
        """약속 검사. 통과하면 약속 순서대로 열을 정렬한 표를 돌려준다.

        extra: "allow"(약속에 없는 열은 뒤에 둠) | "drop"(버림) | "forbid"(오류)
        """
        problems: list[str] = []
        missing = [c for c in self.names if c not in df.columns]
        if missing:
            problems.append(f"빠진 열: {missing}")
        extras = [c for c in df.columns if c not in self.names]
        if extras and extra == "forbid":
            problems.append(f"약속에 없는 열: {extras}")

        for col in self.columns:
            if col.name not in df.columns:
                continue
            s = df[col.name]
            if not _kind_ok(s, col.kind):
                problems.append(f"{col.name}: 종류가 {col.kind} 이 아님 (실제 {s.dtype})")
                continue
            n_null = int(s.isna().sum())
            if not col.nullable and n_null:
                problems.append(f"{col.name}: 빈칸 금지인데 {n_null}개 빈칸")
            if col.kind in ("int", "float") and len(s.dropna()):
                v = s.dropna().astype(float)
                if not np.isfinite(v).all():
                    problems.append(f"{col.name}: inf 값 {int((~np.isfinite(v)).sum())}개")
                if col.min is not None and (v < col.min).any():
                    problems.append(f"{col.name}: {col.min} 미만 {int((v < col.min).sum())}개 (최소 {v.min():.4g})")
                if col.max is not None and (v > col.max).any():
                    problems.append(f"{col.name}: {col.max} 초과 {int((v > col.max).sum())}개 (최대 {v.max():.4g})")

        if all(k in df.columns for k in self.key):
            dup = int(df.duplicated(list(self.key)).sum())
            if dup:
                problems.append(f"키 {self.key} 중복 {dup}행")

        if problems:
            raise ContractError(f"{self.name} v{self.version}", problems)

        ordered = self.names + ([c for c in extras] if extra == "allow" else [])
        return df[ordered].reset_index(drop=True)

    def empty(self) -> pd.DataFrame:
        return pd.DataFrame({c.name: pd.Series(dtype=_EMPTY_DTYPE[c.kind]) for c in self.columns})

    def to_markdown(self) -> str:
        lines = [
            f"## {self.name} (형식 {self.version})",
            "",
            self.desc,
            "",
            f"키: `{', '.join(self.key)}`",
            "",
            "| 열 | 종류 | 단위 | 빈칸 | 범위 | 뜻 |",
            "|---|---|---|---|---|---|",
        ]
        for c in self.columns:
            rng = "" if c.min is None and c.max is None else f"{'' if c.min is None else c.min} ~ {'' if c.max is None else c.max}"
            lines.append(f"| `{c.name}` | {c.kind} | {c.unit} | {'허용' if c.nullable else '금지'} | {rng} | {c.desc} |")
        return "\n".join(lines) + "\n"


_EMPTY_DTYPE = {"int": "Int64", "float": "float64", "str": "object", "bool": "bool"}
