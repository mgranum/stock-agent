# Lokal drift av React + FastAPI

## Forutsetninger

* Python-avhengigheter installert med `uv sync`
* Node.js og npm tilgjengelig
* frontend-avhengigheter installert med `npm install` i `frontend/`

## TEST – utvikling og brukerakseptanse

Start begge prosessene fra prosjektroten:

```bash
./scripts/dev_web.sh
```

Skriptet bruker TEST som standard. Åpne `http://127.0.0.1:5173`.

Kjør en fersk TEST-refresh eksplisitt:

```bash
STOCK_AGENT_ENV=test uv run python -m src.daily_refresh --force
```

Ikke bruk `scripts/run_daily_refresh.sh` til TEST. Wrapperen er bevisst
hardkodet til PROD for launchd-jobben.

Kjør migrasjonsportene:

```bash
STOCK_AGENT_ENV=test uv run python scripts/verify_migration_parity.py
STOCK_AGENT_ENV=test uv run python scripts/verify_migration_operations.py
uv run pytest -q
cd frontend
npm run build
npm test -- --run
```

## Samme-origin produksjonsbygg

Bygg klienten og la FastAPI servere den:

```bash
cd frontend
npm run build
cd ..
STOCK_AGENT_ENV=test uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Åpne `http://127.0.0.1:8000`. Direkte ticker-ruter som
`/stocks/AAPL?period=3m` skal fungere etter omstart.

## Kontrollert PROD-verifikasjon

Den read-only paritetskontrollen krever en eksplisitt sikkerhetsbryter:

```bash
STOCK_AGENT_ENV=prod uv run python scripts/verify_migration_parity.py \
  --allow-prod-read-only
```

Kommandoen leser eksisterende PROD-snapshot, portefølje og watchlists. Den
starter ikke refresh, laster ikke kursdata og skriver ikke brukerdata.

## Backup og rollback

Administrer er skrivbar i TEST. PROD er skrivebeskyttet som standard og krever
at serverprosessen startes med den eksplisitte bryteren
`STOCK_AGENT_ENABLE_PROD_WRITES=1`. Før hver lagring opprettes én tidsstemplet
backup som inneholder `portfolio.json`, `watchlists.json` og status for
`writer_owner.json` i miljøets `backups`-mappe. API-svaret inneholder
`backup_id`.

Rollback i TEST:

```text
POST /api/admin/rollback/{backup_id}
```

Backup-id og miljø valideres før brukerdata og writer-eierskap gjenopprettes.
Dersom andre skriving i en mutasjon feiler, gjenoppretter tjenesten all
opprinnelig tilstand automatisk.

Kontrollert PROD-verifikasjon krever tre samtidige vern:

```bash
STOCK_AGENT_ENV=prod STOCK_AGENT_ENABLE_PROD_WRITES=1 \
  uv run python scripts/verify_prod_admin_rollback.py \
  --ticker SUBC.OL --confirm-prod-write-rollback
```

Verifikasjonen gjenbruker tickerens eksisterende eid-status, GAV og
watchlist-medlemskap, ruller umiddelbart tilbake og sammenligner alle tre
datatilstandene med originalen. Bryteren skal ikke settes permanent før den nye
løsningen faktisk gjøres til standard.

## Cutover og tilbakeføring

React kan gjøres til standard først når:

1. fersk TEST- og read-only PROD-paritet består
2. full regresjon og kritiske brukerflyter består
3. PROD-skriving og rollback er eksplisitt godkjent og verifisert
4. brukeren har godkjent grensesnittet i PROD

Ved avvik skal React-serveren stoppes og Streamlit brukes som fallback. Ikke
fjern `app.py` eller Streamlit-avhengigheter før fallbackperioden er avsluttet.
