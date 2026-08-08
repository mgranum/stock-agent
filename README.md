# Stock Agent

Lokal beslutningsstøtte for manuell aksjeinvestering. Den eksisterende
Streamlit-appen beholdes mens et nytt presentasjonslag migreres trinnvis.

## Arkitekturspike: React og FastAPI

Installer Python-avhengigheter og frontend-avhengigheter:

```sh
uv sync
cd frontend
npm install
```

Start FastAPI og Vite sammen fra prosjektroten:

```sh
./scripts/dev_web.sh
```

Åpne deretter `http://127.0.0.1:5173/stocks/NVDA`. API-dokumentasjonen ligger på
`http://127.0.0.1:8000/docs`.

Skriptet bruker `STOCK_AGENT_ENV=test` som standard. Et eksplisitt miljø kan
velges slik:

```sh
STOCK_AGENT_ENV=prod ./scripts/dev_web.sh
```

For å verifisere samme-origin-produksjonsbygg:

```sh
cd frontend
npm run build
cd ..
uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Da åpnes selskapsdetaljen på `http://127.0.0.1:8000/stocks/NVDA`.
