"""统计函数单元测试（不依赖数据库）。运行：pytest -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from olist.stats import attributable_count, mantel_haenszel_rd, two_proportion_test  # noqa: E402


def _make(rows):
    """rows: [(stratum, exposure, outcome, count)] → 展开成个体级 DataFrame"""
    recs = []
    for s, e, o, n in rows:
        recs += [{"s": s, "e": e, "o": o}] * n
    return pd.DataFrame(recs)


def test_mh_equals_crude_when_no_confounding():
    # 两层的暴露比例一样、效应一样 → MH 合并结果 = 不分层结果 = 0.2
    df = _make([
        ("A", 1, 1, 30), ("A", 1, 0, 70), ("A", 0, 1, 10), ("A", 0, 0, 90),
        ("B", 1, 1, 30), ("B", 1, 0, 70), ("B", 0, 1, 10), ("B", 0, 0, 90),
    ])
    r = mantel_haenszel_rd(df, "e", "o", "s")
    assert r["rd"] == pytest.approx(0.2)
    assert r["strata_used"] == 2


def test_mh_removes_confounding_simpson():
    # 构造辛普森悖论：层内都没有效应（差值 0），但暴露集中在高基线的层
    df = _make([
        ("高风险州", 1, 1, 450), ("高风险州", 1, 0, 450), ("高风险州", 0, 1, 50), ("高风险州", 0, 0, 50),
        ("低风险州", 1, 1, 10), ("低风险州", 1, 0, 90), ("低风险州", 0, 1, 90), ("低风险州", 0, 0, 810),
    ])
    crude = df[df.e == 1].o.mean() - df[df.e == 0].o.mean()
    r = mantel_haenszel_rd(df, "e", "o", "s")
    assert crude > 0.3  # 不分层会得出「暴露导致结局」的错误结论
    assert r["rd"] == pytest.approx(0.0, abs=1e-9)


def test_mh_skips_strata_without_both_groups():
    df = _make([("A", 1, 1, 5), ("A", 0, 0, 5), ("B", 1, 1, 3)])
    assert mantel_haenszel_rd(df, "e", "o", "s")["strata_used"] == 1


def test_attributable_count():
    # 1000 单延迟订单，差评率 60%，准时订单 10% → 多出 500 条差评
    assert attributable_count(1000, 0.6, 0.1) == pytest.approx(500)


def test_two_proportion_basic():
    r = two_proportion_test(100, 1000, 80, 1000)
    assert r["abs_diff"] == pytest.approx(-0.02)
    assert r["ci_low"] < r["abs_diff"] < r["ci_high"]
    assert 0 < r["p_value"] < 1


def test_two_proportion_identical_groups():
    r = two_proportion_test(50, 500, 50, 500)
    assert r["abs_diff"] == 0
    assert r["p_value"] == pytest.approx(1.0)
