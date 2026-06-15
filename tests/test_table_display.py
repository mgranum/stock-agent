import unittest

import pandas as pd

from src.table_display import display_table_cell, ensure_string_columns


class TableDisplayTests(unittest.TestCase):
    def test_display_table_cell_formats_missing_values(self):
        self.assertEqual(display_table_cell(None), "—")
        self.assertEqual(display_table_cell(float("nan")), "—")
        self.assertEqual(display_table_cell(42), "42")

    def test_ensure_string_columns_casts_mixed_values(self):
        df = pd.DataFrame(
            {
                "Analytikere": [42, None],
                "Kursmål": [298.93, "—"],
            }
        )

        result = ensure_string_columns(df, ["Analytikere", "Kursmål"])

        self.assertEqual(result.iloc[0]["Analytikere"], "42")
        self.assertEqual(result.iloc[1]["Analytikere"], "—")
        self.assertEqual(result.iloc[0]["Kursmål"], "298.93")
        self.assertEqual(result.iloc[1]["Kursmål"], "—")
