# ADR-001: Trinnvis migrasjon av presentasjonslaget

Status: Vedtatt for arkitekturspike
Dato: 2026-08-08

## Kontekst

Stock Agent er i dag en lokal Streamlit-app med 13 likestilte faner. Nytt
produktdesign krever direkte selskapslenker, globalt søk og chat, presis
responsiv layout og interaktive finansgrafer. Analyse-, anbefalings- og
risikologikken i Python skal bevares.

## Beslutning

* Frontend bygges med React, TypeScript og Vite.
* FastAPI blir et tynt, typet HTTP-lag foran eksisterende Python-moduler.
* TradingView Lightweight Charts brukes til kursgrafen.
* Daily Refresh fortsetter som separat Python-jobb.
* Kursflater bruker dagsdata med 1u som korteste periode; intradagdata skal ikke
  innføres.
* Den ferdigbygde klienten serveres fra FastAPI på samme origin.
* Migrasjonen skjer trinnvis. Streamlit fjernes først etter dokumentert paritet.

## Grenser for migrasjonen

Følgende er domene-/applikasjonslogikk og skal gjenbrukes: datahenting,
indikatorer, fundamentaler, scoring, anbefalinger, porteføljerisiko, stop-loss,
Daily Refresh, context og chat-routing. `app.py` og Streamlit-spesifikk
`session_state`, faner, widgets og formatering er presentasjon som kan erstattes.

Spiken er skrivebeskyttet. Den kan skrive ordinær markedscache, men kan ikke
endre eide aksjer, GAV, watchlists, ordre, anbefalinger eller modellregler.

## Konsekvenser

Frontend får sitt eget byggesteg med Node.js. API-kontrakter må være små og
eksplisitte; hele interne context-objekter skal ikke sendes til klienten.
Streamlit og ny løsning eksisterer parallelt i overgangsperioden.
Nye produktflater skal bygges i den nye løsningen; Streamlit begrenses til
feilretting og nødvendig drift frem til avvikling.

## Stoppkriterier etter spiken

Rammeverksvalget vurderes på nytt dersom direkte ticker-URL, tilbake-/fremover-
navigasjon, samtlige perioder, candlesticks, volum og glidende snitt ikke kan
leveres uten full analyse ved hver grafinteraksjon, eller dersom lokal drift og
TEST/PROD blir vesentlig mer komplisert enn dokumentert her.
