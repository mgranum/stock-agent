from dataclasses import asdict, dataclass

from src.model_version import MODEL_VERSION


PASS = "PASS"
WARNING = "WARNING"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ValidationCheck:
    check_id: str
    title: str
    status: str
    finding: str
    required_action: str


BACKTEST_VALIDATION_CHECKS = (
    ValidationCheck(
        check_id="technical_look_ahead",
        title="Tekniske signaler",
        status=PASS,
        finding=(
            "Indikatorer og relativ styrke beregnes bare fra rader til og med "
            "signaldatoen."
        ),
        required_action="Behold tidsavgrensningen ved senere endringer.",
    ),
    ValidationCheck(
        check_id="fundamental_look_ahead",
        title="Historiske fundamentaler",
        status=BLOCKED,
        finding=(
            "Dagens fundamental- og historikkanalyse lastes én gang og brukes "
            "på alle historiske signaldatoer."
        ),
        required_action=(
            "Bruk point-in-time fundamentaler med publiseringsdato, eller "
            "valider en eksplisitt teknisk-only baseline."
        ),
    ),
    ValidationCheck(
        check_id="signal_execution_timing",
        title="Signal- og handelstidspunkt",
        status=BLOCKED,
        finding=(
            "Signalet bruker dagens close og handelen bokføres til den samme "
            "close-prisen."
        ),
        required_action=(
            "Utfør tidligst på neste tilgjengelige open og dokumenter "
            "håndtering av gap og manglende open."
        ),
    ),
    ValidationCheck(
        check_id="transaction_costs",
        title="Handelskostnader",
        status=BLOCKED,
        finding="Kurtasje, spread og valutaeffekt er ikke trukket fra.",
        required_action=(
            "Legg kostnadsantakelser i backtest-konfigurasjonen og bruk dem "
            "likt for modell og referanser."
        ),
    ),
    ValidationCheck(
        check_id="corporate_actions",
        title="Splits og utbytte",
        status=BLOCKED,
        finding=(
            "Backtesten handler på ujustert close og har ingen eksplisitt "
            "kontantstrøm for utbytte eller justering av antall aksjer."
        ),
        required_action=(
            "Velg og dokumenter total-return-metode; test splits og utbytte "
            "med kjente hendelser."
        ),
    ),
    ValidationCheck(
        check_id="survivorship_bias",
        title="Screening-univers og avnoteringer",
        status=BLOCKED,
        finding=(
            "Dagens watchlist brukes som historisk univers; tidligere "
            "indeksmedlemmer og avnoterte selskaper er ikke bevart."
        ),
        required_action=(
            "Lagre daterte univers-snapshots og definer behandling av "
            "avnotering, oppkjøp og manglende sluttdato."
        ),
    ),
    ValidationCheck(
        check_id="dataset_separation",
        title="In-sample og out-of-sample",
        status=BLOCKED,
        finding=(
            "Periodene uttrykkes som relative yfinance-vinduer uten faste, "
            "ikke-overlappende datoer."
        ),
        required_action=(
            "Bruk eksplisitte dato-intervaller for in-sample, kalibrering og "
            "urørt out-of-sample."
        ),
    ),
    ValidationCheck(
        check_id="rolling_walk_forward",
        title="Rolling walk-forward",
        status=BLOCKED,
        finding=(
            "Konfigurasjonen velges på ett relativt vindu og testes på et "
            "annet vindu som kan overlappe train-data."
        ),
        required_action=(
            "Implementer kronologiske rullerende folds der hvert testvindu "
            "ligger strengt etter sitt trainvindu."
        ),
    ),
)


def build_backtest_validation_report(checks=None):
    selected_checks = (
        BACKTEST_VALIDATION_CHECKS
        if checks is None
        else tuple(checks)
    )

    invalid_statuses = sorted(
        {
            check.status
            for check in selected_checks
            if check.status not in {PASS, WARNING, BLOCKED}
        }
    )
    if invalid_statuses:
        raise ValueError(
            "Ugyldig valideringsstatus: "
            + ", ".join(invalid_statuses)
        )

    blocked_count = sum(
        check.status == BLOCKED
        for check in selected_checks
    )
    warning_count = sum(
        check.status == WARNING
        for check in selected_checks
    )

    return {
        "model_version": MODEL_VERSION,
        "validation_version": "backtest-validation-v1",
        "approved": bool(selected_checks) and blocked_count == 0,
        "status": PASS if selected_checks and blocked_count == 0 else BLOCKED,
        "blocked_count": blocked_count,
        "warning_count": warning_count,
        "checks": [asdict(check) for check in selected_checks],
    }


def summarize_backtest_validation(report):
    if not report or not report.get("checks"):
        return "Backtest-validering: ingen kontroller tilgjengelig."

    if report.get("approved"):
        return (
            "Backtest-validering: GODKJENT "
            f"({len(report['checks'])} kontroller)."
        )

    blocked = [
        check["title"]
        for check in report["checks"]
        if check.get("status") == BLOCKED
    ]
    return (
        "Backtest-validering: IKKE GODKJENT. "
        f"{len(blocked)} blokkerende funn: {', '.join(blocked)}."
    )
