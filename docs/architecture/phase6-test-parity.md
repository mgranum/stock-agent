# Fase 6.1 – TEST-paritet

Dato: 2026-08-09

Miljø: TEST

Resultat: Fersk TEST-paritet godkjent, cutover ikke godkjent

## Automatisert presentasjonsparitet

Kommando:

```bash
STOCK_AGENT_ENV=test uv run python scripts/verify_migration_parity.py
```

Resultat: 73 av 73 kontroller bestått.

Kontrollene sammenligner det nye presentasjonslaget direkte med de samme
kildene som Streamlit bruker:

* modellversjon
* eide tickere og watchlist-medlemskap
* anbefaling og score for alle 21 viste aksjer
* GAV, stop-nivå og gevinst for alle seks eide aksjer
* watchlist-rangeringen i Utforsk
* representativ selskapsanbefaling og selskapsscore

Verifikatoren er read-only og avbryter dersom `STOCK_AGENT_ENV` ikke er `test`.

## Driftskontroller

Kommando:

```bash
STOCK_AGENT_ENV=test uv run python scripts/verify_migration_operations.py
```

Resultat: 9 av 9 kontroller bestått.

* API health, I dag, Utforsk, Modell og data og selskapsdetaljer svarer med 200
* direkte React-rute `/stocks/AAPL?period=3m` svarer med 200
* AAPL-grafen leser 64 datapunkter fra lokal kurscache
* en ny query-instans gjenoppretter de samme 21 beslutningsradene fra disk
* refresh-status kan leses og beholder TEST-miljøet

Manuell nettleserkontroll bekreftet Utforsk → selskapsdetaljer → tilbake til
Utforsk, periodeendring med `replaceState`, kontekstuell chat og minigrafer.

## Fersk Daily Refresh

Daily Refresh ble kjørt eksplisitt i TEST før siste portkontroll:

* `last_status`: `success`
* `last_error_count`: `0`
* fullført: `2026-08-09T13:59:15+00:00`
* 21 symboler og seks porteføljeposisjoner analysert
* screening, context-snapshot og discovery-journal oppdatert

Begge verifikatorene ble kjørt på nytt mot det ferske snapshotet med samme
resultat: 73/73 og 9/9 bestått.

Full regresjon etter refresh:

* backend: 607 tester uten registrerte feil
* frontend: 9 tester bestått
* TypeScript- og Vite-produksjonsbygg: bestått

## Åpent før cutover

Før React kan gjøres til standard må følgende gjennomføres:

1. Gjennomfør kontrollert, read-only PROD-paritet.
2. Dokumenter lokal drift, backup, rollback og cutover før React blir standard.

Streamlit beholdes som fallback. Ingen modell-, score-, anbefalings- eller
stop-loss-logikk er endret i fase 6.1.

## Read-only PROD-paritet

Kommando:

```bash
STOCK_AGENT_ENV=prod uv run python scripts/verify_migration_parity.py \
  --allow-prod-read-only
```

Første kjøring avdekket at Administrer viste en duplisert AAPL-rad fra PROD-
porteføljefilen, mens I dag allerede dedupliserte samme kilde. Presentasjonslaget
er rettet til én rad per ticker uten å endre PROD-datafilen. Fire øvrige avvik
var feil i kontrollens forventning for eide aksjer som bare fantes i
porteføljerapporten; kontrollen bruker nå samme sammenslåtte kilde som Streamlit.

Ny kjøring: 83 av 83 kontroller bestått. Ingen PROD-refresh, kursnedlasting,
mutasjon eller annen skriving ble utført.
