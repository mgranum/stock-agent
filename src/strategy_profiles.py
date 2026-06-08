import pandas as pd

from src.config import load_json_config
from src.strategy_classification import STRATEGY_TYPES, add_strategy_types

DEFAULT_STRATEGY_PROFILES = {
    "MOMENTUM": {
        "preferred_hold_days": 30,
        "preferred_stop_loss_pct": 0.08,
        "preferred_trailing_sma": "sma50",
        "style": "Aggressive trend following",
    },
    "QUALITY_COMPOUNDER": {
        "preferred_hold_days": 180,
        "preferred_stop_loss_pct": 0.15,
        "preferred_trailing_sma": "sma100",
        "style": "Long-term quality accumulation",
    },
    "COMPOUNDER": {
        "preferred_hold_days": 120,
        "preferred_stop_loss_pct": 0.12,
        "preferred_trailing_sma": "sma100",
        "style": "Quality with trend confirmation",
    },
    "CYCLICAL": {
        "preferred_hold_days": 45,
        "preferred_stop_loss_pct": 0.10,
        "preferred_trailing_sma": "sma50",
        "style": "Cyclical swing trading",
    },
    "WEAK/AVOID": {
        "preferred_hold_days": 0,
        "preferred_stop_loss_pct": 0.06,
        "preferred_trailing_sma": "sma20",
        "style": "Avoid or exit exposure",
    },
    "UNKNOWN": {
        "preferred_hold_days": 60,
        "preferred_stop_loss_pct": 0.12,
        "preferred_trailing_sma": "sma100",
        "style": "Default balanced handling",
    },
}


def load_strategy_profiles():
    return load_json_config(
        "strategy_profiles.json",
        DEFAULT_STRATEGY_PROFILES,
    )


def get_strategy_profile(strategy_type):
    profiles = load_strategy_profiles()
    return profiles.get(
        strategy_type,
        profiles.get("UNKNOWN", DEFAULT_STRATEGY_PROFILES["UNKNOWN"]),
    )


def _format_stop_pct(value):
    if value is None:
        return ""

    return f"{float(value) * 100:.0f}%"


def _format_stop_style(profile):
    trailing_sma = profile.get("preferred_trailing_sma", "")
    stop_pct = _format_stop_pct(profile.get("preferred_stop_loss_pct"))

    if trailing_sma and stop_pct:
        return f"{trailing_sma.upper()} trailing / {stop_pct} hard stop"

    return trailing_sma or stop_pct


def add_strategy_profile_columns(df):
    if df is None or df.empty:
        return df

    result = df.copy()

    if "strategy_type" not in result.columns:
        result = add_strategy_types(result)

    def profile_field(strategy_type, field):
        return get_strategy_profile(strategy_type).get(field)

    result["style"] = result["strategy_type"].map(
        lambda strategy_type: profile_field(strategy_type, "style")
    )
    result["preferred_hold_days"] = result["strategy_type"].map(
        lambda strategy_type: profile_field(strategy_type, "preferred_hold_days")
    )
    result["preferred_stop_loss_pct"] = result["strategy_type"].map(
        lambda strategy_type: _format_stop_pct(
            profile_field(strategy_type, "preferred_stop_loss_pct")
        )
    )

    return result


def strategy_profiles_overview():
    profiles = load_strategy_profiles()
    rows = []

    for strategy_type in STRATEGY_TYPES:
        profile = profiles.get(
            strategy_type,
            profiles.get("UNKNOWN", {}),
        )
        rows.append({
            "strategy_type": strategy_type,
            "style": profile.get("style", ""),
            "typical_hold_days": profile.get("preferred_hold_days"),
            "preferred_stop_style": _format_stop_style(profile),
        })

    return pd.DataFrame(rows)
