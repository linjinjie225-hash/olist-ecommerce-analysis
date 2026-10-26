"""口径一致性测试：用 pandas 从原始 CSV 独立重算关键指标，和 SQL 结果对比。

两套代码写法完全不同，如果结果一致，说明 SQL 口径没有写错。
需要先运行 python scripts/build_db.py；没有数据库时自动跳过。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from olist.db import DB_PATH, connect, run_sql_file  # noqa: E402

RAW = ROOT / "data" / "raw"

_cache = {}


def _con():
    if not DB_PATH.exists():
        pytest.skip("未找到 data/olist.db，先运行 scripts/build_db.py")
    if "con" not in _cache:
        _cache["con"] = connect()
    return _cache["con"]


def _pandas_delivered() -> pd.DataFrame:
    """用 pandas 重新实现宽表口径。"""
    if "delivered" in _cache:
        return _cache["delivered"]
    ts = ["order_purchase_timestamp", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]
    o = pd.read_csv(RAW / "olist_orders_dataset.csv", parse_dates=ts)
    c = pd.read_csv(RAW / "olist_customers_dataset.csv")
    it = pd.read_csv(RAW / "olist_order_items_dataset.csv")
    d = o[(o.order_status == "delivered") & o.order_delivered_customer_date.notna() & o.order_delivered_carrier_date.notna()]
    d = d[d.order_id.isin(it.order_id)].merge(c, on="customer_id")
    d = d.assign(is_late=(d.order_delivered_customer_date.dt.normalize() > d.order_estimated_delivery_date.dt.normalize()).astype(int))
    _cache["delivered"] = d
    return d


def test_wide_table_row_count_matches_pandas():
    sql_n = pd.read_sql_query("SELECT COUNT(*) AS n FROM dwd_delivered_orders", _con()).n[0]
    assert sql_n == len(_pandas_delivered())


def test_wide_table_one_row_per_order():
    dup = pd.read_sql_query(
        "SELECT COUNT(*) - COUNT(DISTINCT order_id) AS dup FROM dwd_delivered_orders", _con()
    ).dup[0]
    assert dup == 0


def test_late_rate_matches_pandas():
    sql_rate = pd.read_sql_query("SELECT AVG(is_late) AS r FROM dwd_delivered_orders", _con()).r[0]
    assert sql_rate == pytest.approx(_pandas_delivered().is_late.mean(), abs=1e-12)


def test_root_cause_shares_sum_to_one():
    df = run_sql_file(_con(), "03_late_root_cause.sql")
    assert df.order_share.sum() == pytest.approx(1.0, abs=1e-3)
    assert df.share_of_all_late.sum() == pytest.approx(1.0, abs=1e-3)


def test_delay_buckets_cover_all_reviewed_orders():
    buckets = run_sql_file(_con(), "02_delay_vs_review.sql")
    n = pd.read_sql_query("SELECT COUNT(*) AS n FROM dwd_delivered_orders WHERE review_score IS NOT NULL", _con()).n[0]
    assert buckets.orders.sum() == n


def test_repurchase_matches_pandas():
    sql = run_sql_file(_con(), "05_repurchase_after_first_order.sql").set_index("first_order")

    o = pd.read_csv(RAW / "olist_orders_dataset.csv", parse_dates=["order_purchase_timestamp"])
    c = pd.read_csv(RAW / "olist_customers_dataset.csv")
    oc = o.merge(c, on="customer_id").sort_values(["customer_unique_id", "order_purchase_timestamp", "order_id"])
    oc["rn"] = oc.groupby("customer_unique_id").cumcount() + 1
    # 下一次「不同时刻」的下单：先对 (用户, 时刻) 去重，再 shift
    moments = oc.drop_duplicates(["customer_unique_id", "order_purchase_timestamp"]).copy()
    moments["next_ts"] = moments.groupby("customer_unique_id").order_purchase_timestamp.shift(-1)
    first = oc[(oc.rn == 1) & (oc.order_purchase_timestamp < "2018-03-04")]
    first = first.merge(moments[["customer_unique_id", "order_purchase_timestamp", "next_ts"]], on=["customer_unique_id", "order_purchase_timestamp"])
    first = first.merge(_pandas_delivered()[["order_id", "is_late"]], on="order_id")
    first["rep"] = ((first.next_ts - first.order_purchase_timestamp).dt.total_seconds() / 86400 <= 180) & first.next_ts.notna()

    for flag, label in [(0, "首单准时"), (1, "首单延迟")]:
        g = first[first.is_late == flag]
        assert len(g) == sql.loc[label, "customers"]
        assert int(g.rep.sum()) == sql.loc[label, "repurchasers"]


def test_rfm_segments_cover_all_customers():
    rfm = run_sql_file(_con(), "06_rfm_segments.sql")
    n = pd.read_sql_query(
        """SELECT COUNT(DISTINCT d.customer_unique_id) AS n
           FROM dwd_delivered_orders d
           WHERE d.order_id IN (SELECT order_id FROM order_payments)""",
        _con(),
    ).n[0]
    assert rfm.customers.sum() == n
    assert rfm.customer_share.sum() == pytest.approx(1.0, abs=1e-3)
    assert rfm.value_share.sum() == pytest.approx(1.0, abs=1e-3)


def test_monthly_gmv_matches_pandas():
    sql = run_sql_file(_con(), "01_monthly_overview.sql")
    o = pd.read_csv(RAW / "olist_orders_dataset.csv", parse_dates=["order_purchase_timestamp"])
    it = pd.read_csv(RAW / "olist_order_items_dataset.csv")
    o = o[~o.order_status.isin(["canceled", "unavailable"])]
    o = o[(o.order_purchase_timestamp >= "2017-01-01") & (o.order_purchase_timestamp < "2018-09-01")]
    gmv = it[it.order_id.isin(o.order_id)].price.sum()
    assert sql.gmv.sum() == pytest.approx(gmv, rel=1e-6)
