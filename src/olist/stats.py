"""分析中用到的统计方法（只依赖 numpy / scipy）。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats


def two_proportion_test(x_a: int, n_a: int, x_b: int, n_b: int, alpha: float = 0.05) -> dict:
    """两比例 z 检验（B 相对 A），差值区间用 Wald 法。"""
    p_a, p_b = x_a / n_a, x_b / n_b
    p_pool = (x_a + x_b) / (n_a + n_b)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    z = (p_b - p_a) / se_pool
    se = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    zc = stats.norm.ppf(1 - alpha / 2)
    return {
        "rate_a": p_a,
        "rate_b": p_b,
        "abs_diff": p_b - p_a,
        "rel_diff": (p_b - p_a) / p_a,
        "ci_low": p_b - p_a - zc * se,
        "ci_high": p_b - p_a + zc * se,
        "p_value": float(2 * (1 - stats.norm.cdf(abs(z)))),
    }


def mantel_haenszel_rd(df: pd.DataFrame, exposure: str, outcome: str, stratum: str) -> dict:
    """Mantel-Haenszel 合并风险差（分层控制混杂）。

    问题：延迟订单更多集中在偏远州、某些品类，而这些州/品类本身差评就可能更多。
    做法：在每个州（或品类）内部比较「延迟 vs 准时」的差评率，再按 MH 权重合并。
    如果合并后的差值和不分层的差值接近，说明这个关系不是由该混杂因素造成的。

    exposure / outcome 需为 0/1 列。
    """
    num, den = 0.0, 0.0
    var_num = 0.0
    used = 0
    for _, g in df.groupby(stratum):
        e = g[g[exposure] == 1][outcome]
        u = g[g[exposure] == 0][outcome]
        n1, n0 = len(e), len(u)
        if n1 == 0 or n0 == 0:
            continue  # 该层只有一种暴露状态，无法比较
        used += 1
        n = n1 + n0
        a, c = e.sum(), u.sum()
        w = n1 * n0 / n
        num += (a / n1 - c / n0) * w
        den += w
        # 方差近似：把 MH 权重视为固定值，合并各层风险差的方差
        var_num += w**2 * ((a / n1) * (1 - a / n1) / n1 + (c / n0) * (1 - c / n0) / n0)
    rd = num / den
    se = math.sqrt(var_num) / den
    return {
        "rd": rd,
        "ci_low": rd - 1.96 * se,
        "ci_high": rd + 1.96 * se,
        "strata_used": used,
    }


def attributable_count(n_exposed: int, rate_exposed: float, rate_unexposed: float) -> float:
    """暴露组中「多出来」的结局数：如果暴露组的结局率降到非暴露组水平，能少多少个。"""
    return n_exposed * (rate_exposed - rate_unexposed)
