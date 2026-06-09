import pandas as pd


def add_indicators(df):
    df = df.copy()

    # -----------------------------
    # Glidende snitt
    # -----------------------------
    df["sma20"] = (
        df["close"]
        .rolling(window=20)
        .mean()
    )

    df["sma50"] = (
        df["close"]
        .rolling(window=50)
        .mean()
    )

    df["sma100"] = (
        df["close"]
        .rolling(window=100)
        .mean()
    )

    df["sma200"] = (
        df["close"]
        .rolling(window=200)
        .mean()
    )

    # -----------------------------
    # RSI (14)
    # -----------------------------
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = (
        gain
        .rolling(window=14)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(window=14)
        .mean()
    )

    rs = avg_gain / avg_loss

    df["rsi"] = (
        100 - (100 / (1 + rs))
    )

    # -----------------------------
    # MACD
    # -----------------------------
    ema12 = (
        df["close"]
        .ewm(span=12, adjust=False)
        .mean()
    )

    ema26 = (
        df["close"]
        .ewm(span=26, adjust=False)
        .mean()
    )

    df["macd"] = ema12 - ema26

    df["macd_signal"] = (
        df["macd"]
        .ewm(span=9, adjust=False)
        .mean()
    )

    # -----------------------------
    # Volum
    # -----------------------------
    df["volume_avg20"] = (
        df["volume"]
        .rolling(window=20)
        .mean()
    )

    # -----------------------------
    # ATR (14)
    # -----------------------------
    high_low = (
        df["high"] - df["low"]
    )

    high_close = (
        df["high"]
        - df["close"].shift()
    ).abs()

    low_close = (
        df["low"]
        - df["close"].shift()
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close,
        ],
        axis=1
    ).max(axis=1)

    df["atr14"] = (
        true_range
        .rolling(window=14)
        .mean()
    )

    return df