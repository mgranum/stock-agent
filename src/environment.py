import os


def get_environment():
    return os.getenv(
        "STOCK_AGENT_ENV",
        "prod",
    ).lower()


def is_prod():
    return get_environment() == "prod"


def is_test():
    return get_environment() == "test"


def environment_label():
    if is_prod():
        return "PROD – faktisk portefølje"

    return "TEST – utviklingsmiljø"


def environment_caption():
    if is_prod():
        return "Miljø: PROD"

    return "Miljø: TEST"


def should_show_test_banner():
    return is_test()


def context_snapshot_filename():
    return f"context_snapshot_{get_environment()}.json"


def daily_refresh_state_filename():
    return f"daily_refresh_state_{get_environment()}.json"


def daily_refresh_lock_filename():
    return f"daily_refresh_lock_{get_environment()}"
