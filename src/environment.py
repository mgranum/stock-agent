import os


def get_environment():
    return os.getenv(
        "STOCK_AGENT_ENV",
        "test",
    )


def is_prod():
    return get_environment() == "prod"


def environment_label():
    if is_prod():
        return "PROD – faktisk portefølje"

    return "TEST – utviklingsmiljø"