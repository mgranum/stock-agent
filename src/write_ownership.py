from src.storage import load_json, update_json


def claim_writer(owner: str):
    normalized = str(owner).strip().lower()
    if normalized not in {"legacy", "react"}:
        raise ValueError("Ugyldig writer-owner.")

    def claim(current):
        existing = str((current or {}).get("owner") or "").lower()
        if existing and existing != normalized:
            raise RuntimeError(
                f"Brukerdata eies av '{existing}' og kan ikke skrives av '{normalized}'."
            )
        return {"owner": normalized}

    return update_json("writer_owner.json", claim, {})


def assert_writer(owner: str):
    current = load_json("writer_owner.json", {})
    existing = str((current or {}).get("owner") or "").lower()
    if existing and existing != str(owner).strip().lower():
        raise RuntimeError(
            f"Brukerdata eies av '{existing}' og kan ikke skrives av '{owner}'."
        )
