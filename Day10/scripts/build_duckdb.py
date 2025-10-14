import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "db" / "analytics.duckdb"
DEFAULT_FILE = DATA_DIR / "uber_lyft_boston.csv"  # fallback if present

def find_csvs():
    paths = []
    if DEFAULT_FILE.exists():
        paths.append(str(DEFAULT_FILE))
    # include any other CSVs
    for p in DATA_DIR.glob("*.csv"):
        sp = str(p)
        if sp not in paths:
            paths.append(sp)
    return paths

def main():
    csvs = find_csvs()
    if not csvs:
        raise SystemExit(f"No CSVs found in {DATA_DIR}. Put your Kaggle file there.")

    print(f"Using CSV files: {csvs}")

    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")
    con.execute("CREATE SCHEMA IF NOT EXISTS day10;")
    con.execute("SET schema='day10';")

    # Load raw
    con.execute("DROP TABLE IF EXISTS raw_rides;")
    print("Loading CSV(s) into raw_rides ...")
    con.execute(
        """
        CREATE TABLE raw_rides AS
        SELECT * FROM read_csv_auto(?, HEADER=TRUE);
        """,
        [csvs if len(csvs) > 1 else csvs[0]],
    )

    # Column names
    info = con.execute("PRAGMA table_info('raw_rides');").fetchall()
    colnames = [row[1] for row in info]
    print("Detected columns:", colnames)

    def first_existing(cands):
        return next((c for c in cands if c in colnames), None)

    # Possible columns in this dataset
    ts_text_col = first_existing(["datetime", "date_time"])
    ts_col = first_existing(["timestamp", "_timestamp"])  # often unix seconds
    lat_col = first_existing(["latitude", "lat", "pickup_latitude"])
    lon_col = first_existing(["longitude", "lon", "lng", "pickup_longitude"])

    # Helper to sanitize "NA"/"N/A"/"NaN"/"null"/""
    def num_expr(col):
        if not col:
            return "NULL::DOUBLE"
        return f"""
        CASE
          WHEN {col} IS NULL THEN NULL
          WHEN lower(trim(CAST({col} AS VARCHAR))) IN ('', 'na', 'n/a', 'nan', 'null') THEN NULL
          ELSE TRY_CAST({col} AS DOUBLE)
        END
        """

    # Timestamp derivation:
    # 1) Prefer explicit datetime text -> TIMESTAMP
    # 2) Else, from unix seconds in `timestamp` (numeric or string)
    if ts_text_col:
        ts_expr = f"TRY_CAST({ts_text_col} AS TIMESTAMP)"
    elif ts_col:
        # If numeric: epoch seconds; if string: try cast to DOUBLE first, else parse as timestamp text
        ts_expr = f"""
        CASE
          WHEN {ts_col} IS NULL THEN NULL
          -- try numeric epoch: cast to DOUBLE succeeds
          WHEN TRY_CAST({ts_col} AS DOUBLE) IS NOT NULL THEN
               (TIMESTAMP '1970-01-01' + TRY_CAST({ts_col} AS DOUBLE) * INTERVAL 1 SECOND)
          -- else try timestamp text parse
          ELSE TRY_CAST({ts_col} AS TIMESTAMP)
        END
        """
    else:
        ts_expr = "NULL::TIMESTAMP"

    price_expr = num_expr(first_existing(["price", "fare", "amount"]))
    dist_expr  = num_expr(first_existing(["distance", "miles"]))
    surge_expr = num_expr(first_existing(["surge_multiplier", "surge", "multiplier"]))
    lat_expr   = num_expr(lat_col)
    lon_expr   = num_expr(lon_col)

    con.execute("DROP TABLE IF EXISTS rides;")
    print("Creating normalized table rides ...")
    con.execute(
        f"""
        CREATE TABLE rides AS
        SELECT
          COALESCE(LOWER(cab_type), '')::TEXT              AS cab_type,
          COALESCE(LOWER(name), '')::TEXT                  AS ride_name,
          COALESCE(LOWER(source), '')::TEXT                AS source,
          COALESCE(LOWER(destination), '')::TEXT           AS destination,
          COALESCE(product_id, '')::TEXT                   AS product_id,

          {price_expr}                                     AS price_usd,
          {dist_expr}                                      AS distance_miles,
          {surge_expr}                                     AS surge_multiplier,

          {lat_expr}                                       AS latitude,
          {lon_expr}                                       AS longitude,

          {ts_expr}                                        AS ts
        FROM raw_rides;
        """
    )

    # Derived date parts
    print("Adding date parts ...")
    con.execute("ALTER TABLE rides ADD COLUMN IF NOT EXISTS date DATE;")
    con.execute("UPDATE rides SET date = CAST(ts AS DATE) WHERE ts IS NOT NULL;")

    con.execute("ALTER TABLE rides ADD COLUMN IF NOT EXISTS hour INTEGER;")
    con.execute("UPDATE rides SET hour = EXTRACT(HOUR FROM ts) WHERE ts IS NOT NULL;")

    con.execute("ALTER TABLE rides ADD COLUMN IF NOT EXISTS dow INTEGER;")
    con.execute("UPDATE rides SET dow = EXTRACT(DOW FROM ts) WHERE ts IS NOT NULL;")

    # Simple analytics view
    con.execute("DROP VIEW IF EXISTS v_rides_analytics;")
    con.execute(
        """
        CREATE VIEW v_rides_analytics AS
        SELECT
          cab_type, ride_name, source, destination,
          price_usd, distance_miles, surge_multiplier,
          ts, date, hour, dow
        FROM rides;
        """
    )

    # Summary
    n = con.execute("SELECT COUNT(*) FROM rides;").fetchone()[0]
    print(f"Loaded rows into rides: {n}")

    stats = con.execute(
        """
        SELECT
          COUNT(*) AS rows,
          COUNT(price_usd) AS priced_rows,
          ROUND(AVG(price_usd),2) AS avg_price,
          ROUND(AVG(distance_miles),2) AS avg_distance,
          MIN(ts) AS min_ts,
          MAX(ts) AS max_ts
        FROM rides;
        """
    ).fetchdf()
    print(stats)

    con.close()
    print(f"✅ DuckDB ready at: {DB_PATH}")

if __name__ == "__main__":
    main()
