from __future__ import annotations

import pandas as pd

MISSING_DISPLAY = "—"


def display_table_cell(value) -> str:
    if value is None:
        return MISSING_DISPLAY
    if isinstance(value, float):
        if pd.isna(value):
            return MISSING_DISPLAY
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value)


def ensure_string_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    for column in columns:
        if column in df.columns:
            df[column] = df[column].map(display_table_cell)
    return df
