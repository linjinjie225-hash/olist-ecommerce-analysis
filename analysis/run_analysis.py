"""Olist 电商分析主脚本：执行 sql/ 下的全部查询，做统计检验，输出图表和结果 JSON。

核心业务问题：
  Olist 的差评从哪里来？物流延迟贡献了多少？延迟的根因是卖家还是物流？
  延迟会不会伤害复购？平台该优先治理什么？

运行（先 python scripts/build_db.py）：
  python analysis/run_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from olist.db import connect, run_sql_file  # noqa: E402
from olist.plotting import BLUE, GREY, RED, plt, save  # noqa: E402
from olist.stats import attributable_count, mantel_haenszel_rd, two_proportion_test  # noqa: E402

FIG = ROOT / "reports" / "figures"
OUT = ROOT / "reports" / "results.json"


def order_level_frame(con) -> pd.DataFrame:
    """订单级数据：宽表 + 订单主品类（第一个商品的品类），用于分层分析。"""
    sql = """
    WITH first_item AS (
        SELECT order_id, product_id
        FROM (SELECT order_id, product_id,
                     ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_item_id) AS rn
              FROM order_items)
        WHERE rn = 1
    )
    SELECT d.order_id, d.customer_state, d.is_late, d.seller_late, d.delay_days, d.review_score,
           COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
    FROM dwd_delivered_orders d
    JOIN first_item fi ON fi.order_id = d.order_id
    LEFT JOIN products p ON p.product_id = fi.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
    WHERE d.review_score IS NOT NULL
    """
    df = pd.read_sql_query(sql, con)
    df["bad"] = (df["review_score"] <= 2).astype(int)
    return df


def main() -> dict:
    FIG.mkdir(parents=True, exist_ok=True)
    con = connect()
    res: dict = {}

    # ---------- 1. 经营概览 ----------
    monthly = run_sql_file(con, "01_monthly_overview.sql")
    res["overview"] = {
        "months": len(monthly),
        "total_orders": int(monthly["orders"].sum()),
        "total_gmv": float(monthly["gmv"].sum()),
        "aov": float(monthly["gmv"].sum() / monthly["orders"].sum()),
        "peak_month": monthly.loc[monthly["gmv"].idxmax(), "month"],
        "gmv_2017_08": float(monthly.set_index("month").loc["2017-08", "gmv"]),
        "gmv_2018_08": float(monthly.set_index("month").loc["2018-08", "gmv"]),
    }
    fig, ax = plt.subplots(figsize=(8, 3.3))
    ax.bar(monthly["month"], monthly["gmv"] / 1e6, color=BLUE)
    ax.set_ylabel("GMV（百万雷亚尔）")
    ax.set_title("月度 GMV：2017 年快速增长，2017-11 黑五达到峰值，2018 年进入平台期")
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    save(fig, FIG / "01_monthly_gmv.png")

    # ---------- 2. 延迟与评分 ----------
    bucket = run_sql_file(con, "02_delay_vs_review.sql")
    res["delay_buckets"] = bucket.to_dict(orient="records")
    fig, ax = plt.subplots(figsize=(8, 3.5))
    labels = [b[3:] for b in bucket["delay_bucket"]]
    colors = [GREY if "提前" in b else RED for b in bucket["delay_bucket"]]
    ax.bar(labels, bucket["bad_review_rate"] * 100, color=colors)
    for i, v in enumerate(bucket["bad_review_rate"]):
        ax.text(i, v * 100 + 1.5, f"{v:.0%}", ha="center", fontsize=9)
    ax.set_ylabel("差评率（1~2 星，%）")
    ax.set_title("一旦晚于承诺日期送达，差评率从约 10% 跳到 32%~80%")
    ax.tick_params(axis="x", rotation=20)
    save(fig, FIG / "02_delay_vs_bad_review.png")

    orders = order_level_frame(con)
    late, ontime = orders[orders.is_late == 1], orders[orders.is_late == 0]
    overall = two_proportion_test(int(ontime.bad.sum()), len(ontime), int(late.bad.sum()), len(late))
    res["late_vs_ontime_bad_review"] = {**overall, "n_late": len(late), "n_ontime": len(ontime)}

    # 混杂控制：在州内、品类内比较
    res["mh_by_state"] = mantel_haenszel_rd(orders, "is_late", "bad", "customer_state")
    res["mh_by_category"] = mantel_haenszel_rd(orders, "is_late", "bad", "category")

    # 差评归因：延迟订单「多出来」的差评
    excess = attributable_count(len(late), overall["rate_b"], overall["rate_a"])
    total_bad = int(orders.bad.sum())
    res["attribution"] = {
        "total_bad_reviews": total_bad,
        "late_share_of_orders": len(late) / len(orders),
        "late_share_of_bad_reviews": float(late.bad.sum() / total_bad),
        "excess_bad_reviews_from_late": float(excess),
        "excess_share_of_all_bad": float(excess / total_bad),
    }
    # 情景测算：延迟率减半，差评能少多少？（假设延迟订单差评率与准时订单一致后的改善按比例发生）
    half = excess / 2
    avg_now = orders.review_score.mean()
    score_gap = late.review_score.mean() - ontime.review_score.mean()
    res["scenario_half_late"] = {
        "bad_reviews_avoided": float(half),
        "bad_review_rate_now": float(orders.bad.mean()),
        "bad_review_rate_after": float((total_bad - half) / len(orders)),
        "avg_score_now": float(avg_now),
        "avg_score_after": float(avg_now - score_gap * (len(late) / 2) / len(orders)),
    }

    # ---------- 3. 延迟根因 ----------
    root = run_sql_file(con, "03_late_root_cause.sql")
    res["root_cause"] = root.to_dict(orient="records")
    d = pd.read_sql_query("SELECT is_late, handling_days, transit_days FROM dwd_delivered_orders", con)
    res["median_days"] = d.groupby("is_late")[["handling_days", "transit_days"]].median().round(2).to_dict(orient="index")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    axes[0].bar(root["seller_handover"], root["late_rate"] * 100, color=[GREY, RED])
    for i, v in enumerate(root["late_rate"]):
        axes[0].text(i, v * 100 + 0.5, f"{v:.1%}", ha="center")
    axes[0].set_title("卖家超时发货的订单，延迟率是 3.9 倍")
    axes[0].set_ylabel("订单延迟率（%）")
    axes[1].pie(
        root["late_orders"],
        labels=[f"{s}\n{v:.0%}" for s, v in zip(root["seller_handover"], root["share_of_all_late"])],
        colors=[GREY, RED],
        startangle=90,
        wedgeprops={"width": 0.45},
    )
    axes[1].set_title("但 72% 的延迟订单，卖家是按时发货的")
    save(fig, FIG / "03_late_root_cause.png")

    # ---------- 4. 地域 ----------
    state = run_sql_file(con, "04_state_late_rate.sql")
    res["state"] = state.to_dict(orient="records")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    s = state.sort_values("late_rate", ascending=False)
    ax.bar(s["customer_state"], s["late_rate"] * 100, color=[RED if v > 0.1 else GREY for v in s["late_rate"]])
    ax.axhline(orders.is_late.mean() * 100, color="black", ls="--", lw=1)
    ax.text(len(s) - 1, orders.is_late.mean() * 100 + 0.4, f"整体 {orders.is_late.mean():.1%}", ha="right", fontsize=9)
    ax.set_ylabel("延迟率（%）")
    ax.set_title("延迟集中在东北部各州（AL、MA、SE…）和人口大州 RJ（订单量 ≥ 300 的州）")
    save(fig, FIG / "04_state_late_rate.png")

    # ---------- 5. 复购 ----------
    rep = run_sql_file(con, "05_repurchase_after_first_order.sql").set_index("first_order")
    r_on, r_late = rep.loc["首单准时"], rep.loc["首单延迟"]
    res["repurchase"] = {
        **two_proportion_test(int(r_on.repurchasers), int(r_on.customers), int(r_late.repurchasers), int(r_late.customers)),
        "n_ontime": int(r_on.customers),
        "n_late": int(r_late.customers),
    }
    # 不显著时要问：样本量能检测多大的差异？（两组样本量不等，80% 功效，α=0.05）
    p0 = res["repurchase"]["rate_a"]
    se0 = np.sqrt(p0 * (1 - p0) * (1 / int(r_on.customers) + 1 / int(r_late.customers)))
    res["repurchase"]["mde_abs"] = float((1.96 + 0.8416) * se0)
    res["repurchase"]["mde_rel"] = float((1.96 + 0.8416) * se0 / p0)

    # ---------- 6. 用户分层 ----------
    rfm = run_sql_file(con, "06_rfm_segments.sql")
    res["rfm"] = rfm.to_dict(orient="records")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    x = np.arange(len(rfm))
    ax.bar(x - 0.2, rfm["customer_share"] * 100, 0.4, color=GREY, label="用户占比")
    ax.bar(x + 0.2, rfm["value_share"] * 100, 0.4, color=BLUE, label="金额占比")
    ax.set_xticks(x)
    ax.set_xticklabels([v[2:] for v in rfm["segment"]])
    ax.set_ylabel("%")
    ax.legend()
    ax.set_title("高价值用户（近期 + 沉睡）只占 18% 的人，却贡献 49% 的金额")
    save(fig, FIG / "06_rfm_segments.png")

    # ---------- 7. 卖家帕累托 ----------
    pareto = run_sql_file(con, "07_seller_late_pareto.sql")
    marks = {}
    for share in [0.01, 0.05, 0.10]:
        row = pareto[pareto["cum_seller_share"] <= share].iloc[-1]
        marks[f"top_{int(share*100)}pct"] = {
            "sellers": int(row["rank_by_late"]),
            "late_share": float(row["cum_late_share"]),
            "order_share": float(row["cum_order_share"]),
        }
    res["seller_pareto"] = {
        "n_sellers": len(pareto),
        "sellers_with_any_late": int((pareto["seller_late_orders"] > 0).sum()),
        **marks,
        "top10": pareto.head(10)[["seller_id", "orders", "seller_late_orders", "seller_late_rate"]].to_dict(orient="records"),
    }
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(pareto["cum_seller_share"] * 100, pareto["cum_late_share"] * 100, color=RED, label="超时发货订单累计占比")
    ax.plot(pareto["cum_seller_share"] * 100, pareto["cum_order_share"] * 100, color=GREY, label="订单量累计占比")
    m = marks["top_5pct"]
    ax.scatter([5], [m["late_share"] * 100], color=RED, zorder=3)
    ax.annotate(f"前 5% 卖家：{m['late_share']:.0%} 的超时发货\n但只有 {m['order_share']:.0%} 的订单", (5, m["late_share"] * 100), xytext=(18, 45), arrowprops={"arrowstyle": "->"})
    ax.set_xlabel("卖家累计占比（按超时发货单数降序，%）")
    ax.set_ylabel("累计占比（%）")
    ax.set_xlim(0, 60)
    ax.legend(loc="lower right")
    ax.set_title("超时发货高度集中在少数卖家")
    save(fig, FIG / "07_seller_pareto.png")

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    con.close()
    return res


def summarize(r: dict) -> None:
    o = r["overview"]
    print(f"订单 {o['total_orders']:,}，GMV {o['total_gmv']:,.0f}，客单价 {o['aov']:.1f}，峰值月 {o['peak_month']}")
    lv = r["late_vs_ontime_bad_review"]
    print(f"差评率：准时 {lv['rate_a']:.2%}（n={lv['n_ontime']:,}）vs 延迟 {lv['rate_b']:.2%}（n={lv['n_late']:,}），差 {lv['abs_diff']*100:+.1f}pp")
    for k in ["mh_by_state", "mh_by_category"]:
        m = r[k]
        print(f"  {k}: {m['rd']*100:+.1f}pp [{m['ci_low']*100:+.1f}, {m['ci_high']*100:+.1f}]，{m['strata_used']} 层")
    a = r["attribution"]
    print(
        f"延迟订单占 {a['late_share_of_orders']:.1%}，却占差评 {a['late_share_of_bad_reviews']:.1%}；"
        f"多出来的差评 {a['excess_bad_reviews_from_late']:.0f} 条 = 全部差评的 {a['excess_share_of_all_bad']:.1%}"
    )
    s = r["scenario_half_late"]
    print(f"延迟减半：少 {s['bad_reviews_avoided']:.0f} 条差评，差评率 {s['bad_review_rate_now']:.2%} → {s['bad_review_rate_after']:.2%}，均分 {s['avg_score_now']:.3f} → {s['avg_score_after']:.3f}")
    for row in r["root_cause"]:
        print(f"  {row['seller_handover']}：订单占 {row['order_share']:.1%}，延迟率 {row['late_rate']:.1%}，占全部延迟 {row['share_of_all_late']:.1%}")
    print(f"中位数天数（0=准时,1=延迟）：{r['median_days']}")
    rp = r["repurchase"]
    print(f"180天复购：准时 {rp['rate_a']:.2%}（n={rp['n_ontime']:,}）vs 延迟 {rp['rate_b']:.2%}（n={rp['n_late']:,}），差 {rp['abs_diff']*100:+.2f}pp [{rp['ci_low']*100:+.2f}, {rp['ci_high']*100:+.2f}]，p={rp['p_value']:.3f}，MDE≈{rp['mde_abs']*100:.2f}pp（相对 {rp['mde_rel']:.0%}）")
    for row in r["rfm"]:
        print(f"  {row['segment']}：用户 {row['customer_share']:.1%}，金额 {row['value_share']:.1%}，客均 {row['avg_value']:.0f}")
    sp = r["seller_pareto"]
    for k in ["top_1pct", "top_5pct", "top_10pct"]:
        print(f"  {k}: {sp[k]['sellers']} 个卖家 → 超时发货 {sp[k]['late_share']:.1%}，订单 {sp[k]['order_share']:.1%}")


if __name__ == "__main__":
    summarize(main())
