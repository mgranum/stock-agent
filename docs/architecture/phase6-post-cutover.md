# Fase 6.3 – post-cutover

Dato: 2026-08-09

Miljø: PROD

Resultat: React/FastAPI godkjent som standard, Streamlit beholdes som fallback

## Brukerakseptanse

Hele PROD-klienten er gjennomgått. En aksje er lagt til i watchlist og en
posisjon er fjernet gjennom React-klienten. Begge operasjonene oppførte seg som
forventet, og `writer_owner.json` bekrefter at React eier videre skriving.

## Post-cutover-paritet

Den første kontrollen etter de reelle endringene avdekket at en aksje som ble
flyttet fra portefølje til watchlist mistet anbefaling og score frem til neste
Daily Refresh. Presentasjonslaget gjenbruker nå aksjens eksisterende analyse fra
samme snapshot. Ingen score, anbefaling eller risiko beregnes på nytt.

Ny read-only PROD-kontroll bestod 75 av 75 kontroller.

## Kortvarig fallback

Streamlit og `app.py` beholdes uten videre funksjonsutvikling. Før de fjernes
skal minst én ordinær planlagt PROD Daily Refresh og én omstart av
standardstarteren være verifisert etter cutover. Ved feil kan Streamlit lese
PROD-data, men React forblir eneste writer så lenge writer-eierskapet ikke er
kontrollert tilbakeført.
