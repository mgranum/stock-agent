from src.storage import save_portfolio
from src.write_ownership import assert_writer


def add_or_update_position(
    portfolio,
    ticker,
    shares,
    buy_price,
):
    assert_writer("legacy")
    ticker = ticker.upper()

    updated = []

    found = False

    for position in portfolio:
        if position["ticker"] == ticker:
            updated.append({
                "ticker": ticker,
                "shares": shares,
                "buy_price": buy_price,
            })
            found = True
        else:
            updated.append(position)

    if not found:
        updated.append({
            "ticker": ticker,
            "shares": shares,
            "buy_price": buy_price,
        })

    save_portfolio(updated)

    return updated


def remove_position(
    portfolio,
    ticker,
):
    assert_writer("legacy")
    ticker = ticker.upper()

    updated = [
        position
        for position in portfolio
        if position["ticker"] != ticker
    ]

    save_portfolio(updated)

    return updated
