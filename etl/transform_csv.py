#!/usr/bin/env python3
"""
transform_csv.py

Clean and normalizes CSV files exported from Google Sheets
before load them to PostgreSQL (via COPY):

  1. Deletes currency simbols and commas in numeric values  ($1,234.56 → 1234.56)
  2. Converts integer floats in real floats            (3.0 → 3)
  3. Localizes datetime columns in user timezone and converts in UTC

Use:
    python3 transform_csv.py --data-folder ./data --config ./timezone_config.yml

Designed to be reused as module in dedicated ETL service.
"""

import sys
import re
import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleans and normalize CSVs for PostgreSQL.")
    parser.add_argument("--data-folder", required=True, help="Folder that contains CSVs")
    parser.add_argument("--config",      required=True, help="Path to timezone_config.yml")
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """Loads the timezones configuration from YAML."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    return yaml.safe_load(path.read_text())


def resolve_tz(config: dict, table: str, col: str) -> ZoneInfo:
    """Return origin timezone for a given table/column."""
    tz_name = (
        config
        .get("overrides", {})
        .get(table, {})
        .get(col, config["default_timezone"])
    )
    return ZoneInfo(tz_name)


def clean_currency(series: pd.Series) -> pd.Series:
    """
    Delete currency simbols and thousands separators.
    '$1,234.56' → 1234.56 | '1,234' → 1234.0
    Only acts in string columns wich contains $ or numeric commas.
    """
    if not pd.api.types.is_string_dtype(series):
        return series

    sample = series.dropna().head(20).str.cat(sep=" ")
    if not re.search(r'\$|(?<=\d),(?=\d)', sample):
        return series

    cleaned = (
        series
        .str.replace(r'^\s*\$', '', regex=True)
        .str.replace(r',(?=\d{3})', '', regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce").combine_first(series)


def fix_integer_floats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts float columns that only contains numeric values to Int64.
    Avoid pandas serializes '3' as '3.0' when the CSV is written.
    """
    for col in df.columns:
        if not pd.api.types.is_float_dtype(df[col]):
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        if (non_null % 1 == 0).all():
            df[col] = df[col].astype("Int64")
    return df


def localize_timestamps(df: pd.DataFrame, config: dict, table: str) -> tuple[pd.DataFrame, int]:
    """
    Detects datetime columns, localize them in user timezones and converts to UTC.
    Returns modified DataFrame and the count of transformed columns.
    """
    transformed = 0

    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]):
            continue

        parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True, format="mixed")

        if parsed.dt.tz is not None:
            df[col] = parsed.dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S+00")
            transformed += 1
            print(f"    [TZ] {table}.{col} → UTC (already tz-aware)")
            continue

        non_null_mask  = df[col].notna()
        valid_ratio = parsed[non_null_mask].notna().sum() / max(non_null_mask.sum(), 1)
        if valid_ratio < 0.5:
            continue

        tz = resolve_tz(config, table, col)
        try:
            df[col] = (
                parsed
                .dt.tz_localize(tz)
                .dt.tz_convert("UTC")
                .dt.strftime("%Y-%m-%d %H:%M:%S+00")
            )
            transformed += 1
            print(f"    [TZ] {table}.{col} → UTC (from {tz})")
        except Exception as e:
            raise RuntimeError(f"Error localizing {table}.{col}: {e}") from e

    return df, transformed


def transform_csv(csv_path: Path, config: dict) -> int:
    """
    Applies all transformations to a CSV in-place.
    Returns the count of transformed columns.
    """
    table = csv_path.stem
    df = pd.read_csv(csv_path, keep_default_na=True, dtype_backend="numpy_nullable")

    # 1. Clean currency
    df = df.apply(clean_currency)

    # 2. Convert empty/blank strings to NULL
    df = df.apply(lambda col: col.str.strip().replace("", pd.NA) 
                if pd.api.types.is_string_dtype(col) else col)

    # 3. Fix integer floats
    df = fix_integer_floats(df)

    # 4. Localize timestamps to UTC
    df, transformed = localize_timestamps(df, config, table)

    df.to_csv(csv_path, index=False)
    return transformed


def transform(data_folder: str, config_path: str) -> None:
    """Principal entry point. Process all CSVs into folder."""
    config = load_config(config_path)
    csv_files = list(Path(data_folder).glob("*.csv"))

    if not csv_files:
        print("[WARN] CSVs not found", file=sys.stderr)
        return

    total_cols = 0
    for csv_path in csv_files:
        print(f"[INFO] Processing: {csv_path.name}")
        cols = transform_csv(csv_path, config)
        total_cols += cols
        print(f"       → {cols} timestamp column(s) transformed")

    print(f"[INFO] Ready. Total of processed timestamp column(s): {total_cols}")


if __name__ == "__main__":
    args = parse_args()
    try:
        transform(args.data_folder, args.config)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)