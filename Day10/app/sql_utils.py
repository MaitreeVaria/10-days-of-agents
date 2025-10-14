# Day10/app/sql_utils.py
from pathlib import Path
import duckdb
import pandas as pd
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "analytics.duckdb"

@contextmanager
def connect_ro():
    con = duckdb.connect(str(DB_PATH))
    try:
        # read-only-ish: disable dangerous pragmas & restrict memory if desired
        con.execute("PRAGMA threads=4;")
        con.execute("SET schema='day10';")
        yield con
    finally:
        con.close()

def list_tables():
    with connect_ro() as con:
        return con.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = 'day10'
            ORDER BY table_name
        """).fetchdf()

def list_columns(table: str):
    with connect_ro() as con:
        return con.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'day10' AND table_name = ?
            ORDER BY ordinal_position
        """, [table]).fetchdf()

SAFE_PREFIXES = ("select", "with", "explain", "show", "describe", "pragma")  # allow read-only

def is_safe_sql(sql: str) -> bool:
    if not sql:
        return False
    head = sql.strip().split(None, 1)[0].lower()
    return any(head.startswith(p) for p in SAFE_PREFIXES)

def run_sql(sql: str) -> pd.DataFrame:
    with connect_ro() as con:
        return con.execute(sql).fetchdf()

def quick_examples():
    return {
        "Sample 10 rides": "SELECT * FROM v_rides_analytics LIMIT 10;",
        "Avg price by cab_type":
            "SELECT cab_type, ROUND(AVG(price_usd),2) AS avg_price, COUNT(*) AS n "
            "FROM v_rides_analytics GROUP BY cab_type ORDER BY n DESC;",
        "Hourly volume (last 90 days if available)":
            "WITH recent AS (SELECT * FROM v_rides_analytics "
            "WHERE ts IS NOT NULL AND ts >= DATE_TRUNC('day', CURRENT_TIMESTAMP) - INTERVAL 90 DAY) "
            "SELECT hour, COUNT(*) AS trips FROM recent GROUP BY hour ORDER BY hour;",
        "Top routes by trips":
            "SELECT source, destination, COUNT(*) AS trips "
            "FROM v_rides_analytics GROUP BY source, destination ORDER BY trips DESC LIMIT 20;"
    }
