# Plan for avvikling av Streamlit

Dato: 2026-08-10

Status: Gjennomført

## Konklusjon

`app.py` er et 2160-linjers presentasjonslag for de 13 gamle Streamlit-tabbene.
FastAPI, Daily Refresh og React importerer ikke filen. Den kan derfor fjernes
uten å omskrive investeringsmodellen, men bare etter at start- og driftsdokumentasjon
er oppdatert samtidig.

## Første slettetrinn

Følgende kan fjernes samlet:

* `app.py`
* `streamlit` fra `pyproject.toml` og låsefilen
* Streamlit-fallbackkommandoer i README og driftsdokumentasjonen
* Streamlit-spesifikke miljøtekster som ikke har andre kallere

Akseptanse etter sletting:

* standardstarteren bygger og starter React/FastAPI
* direkte ruter og API-kontrakter fungerer etter omstart
* full Python- og frontendregresjon består
* read-only PROD-paritet består
* Daily Refresh importerer og kjører uten Streamlit installert

## Skal beholdes

Følgende er domenelogikk eller brukes fortsatt av den nye løsningen og skal
ikke slettes sammen med `app.py`:

* analyse, scoring, trend, stop-loss og anbefalingslogikk
* `src/context.py`, `src/daily_refresh.py` og `src/agent.py`
* screening, discovery journal, snapshots og validering
* backtest- og walk-forward-beregninger som inngår i valideringsgrunnlaget
* lagring, TEST/PROD-separasjon og writer-eierskap

## Egen etterfølgende fase: ordre

Ordre er besluttet avviklet, men kan ikke fjernes som en ren UI-opprydding.
Pending ordre og ordrehistorikk er fortsatt koblet til `context`, `dashboard`,
`alerts`, `daily_flow`, `recommendation_engine`, `agent` og Daily Refresh.

Ordre fjernes derfor etter Streamlit i en separat endring med egne
regresjonstester. Eksisterende datafiler arkiveres eller migreres
gjenopprettelig; de slettes ikke som del av kodeoppryddingen.

## Moduler som blir uten produksjonskallere

Disse modulene er i dag bare kalt av `app.py`, men slettes ikke automatisk:

* `src/order_editor.py`
* `src/portfolio_allocation.py`
* `src/backtest_report.py`
* `src/walk_forward_report.py`

`order_editor.py` vurderes i ordrefasen. De øvrige beholdes til det er avklart
om de skal eksponeres gjennom React/API eller avvikles som gamle rapporthjelpere.

## Verifikasjon

Etter fjerningen ble miljøet synkronisert fra låsefilen uten Streamlit og
PyArrow. Foreldede Arrow-tabellhjelpere for den gamle UI-en ble også fjernet.

* Python: 601 tester og 3 undertester bestått
* frontend: 9 tester bestått
* produksjonsbygg: bestått
* driftskontroll i TEST: 9/9 bestått
* read-only PROD-paritet: 75/75 bestått
