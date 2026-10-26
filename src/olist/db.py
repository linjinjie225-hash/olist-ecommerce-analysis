"""数据库连接与 SQL 执行工具。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "olist.db"
SQL_DIR = ROOT / "sql"


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"找不到 {db_path}，请先运行 python scripts/build_db.py")
    con = sqlite3.connect(db_path)
    create_views(con)
    return con


def create_views(con: sqlite3.Connection) -> None:
    con.executescript((SQL_DIR / "00_views.sql").read_text(encoding="utf-8"))


def run_sql_file(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    return pd.read_sql_query(sql, con)
