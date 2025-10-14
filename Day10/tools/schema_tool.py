from typing import List

from Day10.app.sql_utils import list_tables, list_columns


def list_tables_tool() -> List[str]:
    df = list_tables()
    return df["table_name"].tolist()


def describe_table_tool(table: str) -> str:
    cols = list_columns(table)
    parts = [f"{r['column_name']} {r['data_type']}" for _, r in cols.iterrows()]
    return f"{table} (" + ", ".join(parts) + ")"


def schema_summary_tool() -> str:
    names = list_tables_tool()
    lines = [describe_table_tool(t) for t in names]
    return "\n".join(lines)


