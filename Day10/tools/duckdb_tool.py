from typing import Any, Dict
import pandas as pd

from Day10.app.sql_utils import run_sql, is_safe_sql


def query(sql: str) -> pd.DataFrame:
    if not is_safe_sql(sql):
        raise ValueError("Unsafe SQL: only read-only queries are allowed")
    return run_sql(sql)


