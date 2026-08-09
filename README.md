# Stock Agent

Lokal beslutningsstøtte for manuell aksjeinvestering. React og FastAPI er
standardgrensesnittet. Den eksisterende Streamlit-appen beholdes midlertidig
som fallback.

## Start Stock Agent

Installer Python-avhengigheter og frontend-avhengigheter:

```sh
uv sync
cd frontend
npm install
```

Start standardløsningen mot PROD-data fra prosjektroten:

```sh
./scripts/start_web.sh
```

Åpne deretter `http://127.0.0.1:8000`. Skriptet bygger React-klienten og lar
FastAPI servere frontend og API fra samme adresse. Administrer skriver til PROD
med backup før hver endring.

Utvikling og TEST-bruk kjøres fortsatt med Vite:

```sh
./scripts/dev_web.sh
```

Dette åpnes på `http://127.0.0.1:5173`. API-dokumentasjonen ligger på
`http://127.0.0.1:8000/docs`.

Midlertidig Streamlit-fallback:

```sh
STOCK_AGENT_ENV=prod uv run streamlit run app.py
```

Fallbacken kan lese PROD-data. Etter at React har tatt writer-eierskap, skal
endringer i eide aksjer og watchlists gjøres i React.

Se [lokal drifts- og migrasjonsveiledning](docs/operations/react-fastapi-local.md)
for Daily Refresh, paritetskontroller, backup, rollback og cutover-kriterier.
