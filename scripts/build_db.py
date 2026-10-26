"""把 Olist 的 8 张 CSV 表导入 SQLite（data/olist.db），并建好常用索引。

运行：python scripts/build_db.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "olist.db"

TABLES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

INDEXES = [
    "CREATE INDEX idx_orders_order ON orders(order_id)",
    "CREATE INDEX idx_orders_customer ON orders(customer_id)",
    "CREATE INDEX idx_items_order ON order_items(order_id)",
    "CREATE INDEX idx_items_seller ON order_items(seller_id)",
    "CREATE INDEX idx_items_product ON order_items(product_id)",
    "CREATE INDEX idx_pay_order ON order_payments(order_id)",
    "CREATE INDEX idx_reviews_order ON order_reviews(order_id)",
    "CREATE INDEX idx_customers_id ON customers(customer_id)",
    "CREATE INDEX idx_customers_unique ON customers(customer_unique_id)",
    "CREATE INDEX idx_products_id ON products(product_id)",
]


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    for table, fname in TABLES.items():
        # 邮编前缀要按字符串读，否则开头的 0 会丢
        df = pd.read_csv(RAW / fname, dtype={"customer_zip_code_prefix": str, "seller_zip_code_prefix": str}, encoding="utf-8-sig")
        df.to_sql(table, con, index=False)
        print(f"{table:<22}{len(df):>10,} 行")
    for sql in INDEXES:
        con.execute(sql)
    con.commit()
    con.close()
    print(f"已生成 {DB}")


if __name__ == "__main__":
    main()
