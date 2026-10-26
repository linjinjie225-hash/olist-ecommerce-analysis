"""下载 Olist 公开数据集到 data/raw/（共 8 个 CSV，约 63MB）。

运行：python scripts/download_data.py
如果访问 GitHub 慢，也可以去 Kaggle 搜索 "Brazilian E-Commerce Public Dataset by Olist" 手动下载，
把下面列出的 CSV 放进 data/raw/ 即可（不需要 geolocation 表）。
"""
from pathlib import Path
from urllib.request import urlretrieve

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
BASE = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"
FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_products_dataset.csv",
    "product_category_name_translation.csv",
]


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = RAW / name
        if dest.exists():
            print(f"已存在，跳过：{name}")
            continue
        print(f"下载 {name} ...")
        urlretrieve(BASE + name, dest)
    print("完成")


if __name__ == "__main__":
    main()
