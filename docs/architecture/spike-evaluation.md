# Evaluering av React/FastAPI-spike

Dato: 2026-08-08
Resultat: Godkjent for videre trinnvis migrasjon

## Verifisert

* FastAPI leverer et typet, skrivebeskyttet selskaps-API fra eksisterende
  Python-datafunksjoner.
* React-klienten kan åpnes direkte på `/stocks/{ticker}` og serveres fra samme
  origin i produksjonsbygg.
* Periodevelgeren støtter 1u, 1m, 3m, 6m, i år, 1 år, 3 år og maks.
* Løsningen bruker kun dagsdata. 1u er korteste periode; intradagdata er
  eksplisitt utenfor målbildet.
* Candlesticks, volum, SMA20 og SMA50 kan vises uten å kjøre fundamental- eller
  anbefalingsanalysen på nytt.
* Tickerbytte samt nettleserens tilbake- og fremoverhistorikk bevarer rute og
  periode.
* Desktop og 375 px mobilbredde er kontrollert uten horisontal overflow eller
  konsollfeil.
* TEST/PROD videreføres via `STOCK_AGENT_ENV`.

## Bevisste avgrensninger

* Spiken har kun tickeroppslag, ikke fullstendig søk etter selskapsnavn.
* Valuta, agentvurdering, fundamentaler og nyheter er ikke koblet på ennå.
* Dagsdata caches foreløpig i minnet per prosess og periode for grafen.
* Ingen brukerdata kan endres fra den nye frontend-en.

Ingen stoppkriterier ble utløst. Neste tekniske fase er å etablere de eksplisitte
API-kontraktene og datavernet beskrevet i backloggen før flere flater migreres.
