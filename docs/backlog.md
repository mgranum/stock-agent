# Backlog

## Mål og styrende prinsipp

Stock Agent skal finne og følge opp investeringsmuligheter for en tidshorisont på
dager til uker. Den skal bare anses som verdiskapende dersom rådene over tid gir
bedre risikojustert resultat enn en passiv global indeks og enkle,
implementerbare referansestrategier.

Videre utvikling skal derfor prioritere:

1. målbar investeringsverdi
2. kapitalbeskyttelse og datakvalitet
3. tydelige, etterprøvbare råd
4. enkel daglig bruk
5. nye funksjoner

Inntil modellen er validert, skal faktiske kjøp behandles som eksperimenter med
begrenset kapital. Sentiment, analytikervurderinger eller språkmodelltekst skal
ikke alene styre kjøp eller salg.

---

## 🔥 Neste milepæl – Discovery Universe & Candidate Selection v1

Målet er å gjøre watchlist til et sted for oppfølging, ikke kilden til hvilke
aksjer modellen får lov til å vurdere. Discovery skal finne kandidater brukeren
ikke allerede kjenner, før de eventuelt legges i watchlist.

### 1. Skill discovery fra watchlist

* [x] Kombiner regionale screeningresultater til én deduplisert kandidatliste
* [x] Behold kandidater uavhengig av watchlist og marker bare watchlist-status
* [x] Bygg Opportunity Advisor automatisk fra discovery-kandidatene
* [x] La Recommendation Engine konsumere discovery-kandidater i daglig context
* [x] Vis discovery-kandidater i en egen, alltid synlig Dashboard-seksjon
* [x] Skjul dupliserte detaljer og støttedata bak utvidbare Dashboard-seksjoner

### 2. Etabler et bredt og reproduserbart univers

* [ ] Erstatt de håndplukkede tickerlistene med dokumenterte USA- og Norden-univers
* [x] Lag daterte univers-snapshots slik at kjøringer kan reproduseres
* [ ] Definer regler for notering og markedsverdi
* [x] Innfør konfigurerbare minimumskrav til likviditet, kurshistorikk og prisdata
* [ ] Håndter nye noteringer, avnoteringer og tickerendringer
* [x] Rapporter antall vurderte, analyserte, filtrerte og feilede selskaper per kjøring

### 3. To-trinns kandidatvalg

* [x] Bruk et billig pris-/likviditetsfilter før full analyse
* [x] Hent prisdata batchvis og gjenbruk dags-cache i grovfilteret
* [ ] Kjør full analyse bare på et begrenset antall topprangerte kandidater
* [x] Dokumenter ticker, trinn og årsak for filtrerte og feilede analyser
* [ ] Begrens sektor- og regionskonsentrasjon i kandidatlisten

### 4. Valider discovery-pipelinen

* [ ] Backtest hele kjeden fra historisk univers til kandidat og neste-dags utførelse
* [ ] Sammenlign discovery-porteføljen mot globale og regionale investerbare referanser
* [ ] Mål hit-rate, turnover, drawdown og meravkastning uten dagens watchlist
* [ ] Ikke utvikle nye features før kandidatvalg og benchmarkdata er troverdige

---

## Model Validation & Decision Journal v1

Målet er å finne ut om agenten faktisk tilfører verdi, ikke å optimalisere den
før målegrunnlaget er troverdig.

### 1. Frys og dokumenter dagens modell

* [x] Gi produksjonsmodellen en eksplisitt `model_version`
* [x] Lagre modellversjon i context snapshots, model snapshots og anbefalinger
* [x] Dokumenter dagens score-, anbefalings-, stop- og porteføljeregler uten å endre dem
* [ ] Definer én strukturert anbefalingskontrakt:
  action, scope, tidshorisont, inngangsbetingelse, kursmål, stop, begrunnelser,
  invalidasjon, konfidens og datakvalitet
* [ ] La Recommendation Engine være eneste eier av det endelige rådet
* [x] Kartlegg hvilke moduler som produserer signaler, og hvilke som i dag produserer konkurrerende råd

### 2. Valider backtesten

* [x] Audit for look-ahead bias
* [ ] Audit for survivorship bias i screening-univers
* [ ] Verifiser at historiske fundamentaler bare bruker informasjon som var kjent på analysetidspunktet
* [x] Verifiser realistisk signaltidspunkt og inngangskurs
* [x] Legg inn konfigurerbar kurtasje, spread og eventuell valutaeffekt
* [x] Dokumenter håndtering av splits, utbytte og manglende data
* [ ] Dokumenter og implementer håndtering av avnoterte selskaper
* [x] Skill tydelig mellom in-sample, kalibrering, historisk test og urørt out-of-sample
* [x] Bruk kronologisk rolling walk-forward som obligatorisk kontroll før modellendringer

### 3. Etabler referanser agenten må slå

* [ ] Velg og dokumenter en investerbar global indeksreferanse
* [ ] Sammenlign også mot relevante lokale markedsindekser per region
* [x] Implementer kostnadsjustert buy-and-hold-referanse
* [ ] Implementer en enkel trend-/momentumreferanse
* [ ] Sammenlign dagens komplette modell mot referansene på identiske perioder og kostnadsantakelser
* [x] Rapporter CAGR/annualisert avkastning, maksimal drawdown, Sharpe/Sortino,
  treffprosent, gevinst/tap-forhold, turnover, antall handler og gjennomsnittlig holdetid
* [x] Rapporter resultat separat for USA, Norge og øvrige Norden
* [ ] Rapporter resultat separat per strategiprofil
* [ ] Definer skriftlige godkjenningskriterier før modellen kan sies å skape merverdi

### 4. Bygg Decision Journal

* [ ] Lagre alle materielle råd med tidspunkt, modellversjon og tilgjengelige inputdata
* [ ] Lagre anbefalt inngang, kursmål, stop, tidshorisont, konfidens og invalidasjonsgrunn
* [ ] Registrer om brukeren fulgte rådet, uten å blande dette med modellresultatet
* [ ] Evaluer råd etter 5, 10, 20 og 40 handelsdager
* [ ] Mål maksimal positiv og negativ kursutvikling etter rådet
* [ ] Registrer om kursmål eller stop ble truffet først
* [ ] Sammenlign hvert råd med global indeks og relevant lokal benchmark i samme periode
* [ ] Lag en aggregert rapport for faktisk fremoverskuende presisjon og avkastning
* [ ] Vis datadekning og marker råd som ikke kan evalueres pålitelig

### 5. Beslutningsport

* [ ] Ikke endre scoring eller anbefalingsregler før baseline og bias-audit er ferdig
* [ ] Ikke øk kapital basert på modellen før et tilstrekkelig fremoverskuende datagrunnlag foreligger
* [ ] Behold modellen uendret dersom en foreslått forbedring bare virker in-sample
* [ ] Forenkle modellen dersom den komplette modellen ikke stabilt slår en enklere referanse etter risiko og kostnader
* [ ] Dokumenter beslutningen: fortsett, juster, forenkle eller stopp aktiv aksjeplukking

---

## 🚀 Deretter – Daily Product v1

Startes etter at målegrunnlaget er på plass. Målet er at hovedbildet skal svare
på hva investoren bør gjøre i dag, uten å lete gjennom mange faner.

* [ ] Gjør Daily Briefing til primærvisningen
* [ ] Prioriter «Krever handling», «Endret siden sist», «Risiko» og «Beste nye mulighet»
* [ ] Samle motstridende signaler i ett råd med eksplisitt konfliktforklaring
* [ ] Vis forventet oppside, risiko til stop og reward/risk for kjøpskandidater
* [ ] Vis hvorfor et råd er nytt eller endret
* [ ] Flytt backtest, walk-forward og detaljerte analyseverktøy til sekundære visninger
* [ ] Reduser støy og antall likestilte faner
* [ ] Vis datatidspunkt, datakvalitet og modellversjon sammen med rådene
* [ ] Daily Briefing v3 – bygges på den strukturerte anbefalingskontrakten
* [ ] Agentisk overvåkning/endringsvarsler uten dupliserte handlinger

---

## 🧠 Agent Chat – etter strukturert anbefalingskontrakt

Chat skal forklare og utforske strukturerte analyser. Den skal ikke ha en
parallell investeringsmodell eller finne på manglende fakta.

* [ ] Skill agent-routing fra svarformatering i `agent.py`
* [ ] Definer et lite verktøygrensesnitt for daglige råd, risiko, tickerforklaring,
  sammenligning, screening og endringer siden sist
* [ ] La chat bruke Recommendation Engine som kilde til endelige råd
* [ ] Lag en chat-eksempelsamling med regresjonstester
* [ ] Bedre samtalekontekst: «disse», «dem», «den andre» og «forrige resultat»
* [ ] Bedre synonym- og intensjonsmatching
* [ ] Dedupliser topplister og kandidatlister
* [ ] Kontekstbevisst sammenligning basert på tidshorisont, investeringsmål,
  portefølje og watchlist
* [ ] Porteføljesammenligning per ticker
* [ ] Bruk eventuell LLM til språk, oppsummering og forklaring – ikke til å beregne score eller fatte råd

---

## 🛡️ Datakvalitet og robusthet

* [ ] Audit av alle kall til `get_daily_prices()`
* [ ] Gjennomgang av cache-strategi og ferskhetsregler per datatype
* [ ] Skill mellom manglende, utdatert og negativ informasjon
* [ ] Lag datakvalitetsscore og eksplisitt «ikke nok data til råd»
* [ ] Oppdag ekstreme eller åpenbart feilaktige leverandørverdier
* [ ] Sikre robusthet mot Yahoo/yfinance-feil
* [ ] Gjennomgang av `session_state`/refresh-logikk
* [ ] Strukturere testmiljø bedre
* [ ] Kjør sekundære datakilder i shadow mode før de påvirker råd
* [ ] Vurder sekundær kilde for historiske regnskapstall og rapporteringsdatoer
* [ ] Vurder sekundær kilde for earningsdatoer og nordiske børsmeldinger

---

## 🧹 Dokumentasjon og teknisk gjeld

* [ ] Skriv README med formål, begrensninger, installasjon og kjøring
* [ ] Dokumenter `streamlit run app.py`, Daily Refresh og TEST/PROD
* [ ] Erstatt placeholder-metadata i `pyproject.toml`
* [ ] Dokumenter datafiler, cache, snapshots og backupbehov
* [ ] Definer retention- og `.gitignore`-policy for logger og snapshots
* [ ] Gjør utviklingskommandoer eksplisitt TEST der det er praktisk
* [ ] Del Streamlit-visninger gradvis ut av `app.py` uten stor refaktor
* [ ] Reduser brede eller ignorerte `except Exception` der feil bør være synlige
* [ ] Vurder SQLite når Decision Journal eller historikk gjør JSON upraktisk
* [ ] Rydd gamle worktrees og agent-branches

---

## 📊 Senere modellutvikling – bare etter validert baseline

Hvert punkt må ha en hypotese, en forhåndsdefinert evalueringsmetode og
out-of-sample-resultater før det kan påvirke produksjonsråd.

* [ ] Historiske analyser og signalhistorikk
* [ ] Porteføljehistorikk over tid
* [ ] Faktor-modeller: Quality, Momentum og Value
* [ ] OBX-/commodity-spesifikk modell
* [ ] Sektorbasert screening
* [ ] Flere screening-univers
* [ ] Guidance v1 og analytikerendringer
* [ ] Sentiment v2 – aggregert ticker-sentiment og chat
* [ ] Sentimenthistorikk og endringsvarsler
* [ ] FinBERT-evaluering
* [ ] Monte Carlo/porteføljesimulering
* [ ] Automatisk watchlist-generering

---

## 🧊 Parkert inntil dokumentert behov

* [ ] Sosiale medier som sentimentkilde
* [ ] Macro/sentiment-agent
* [ ] Teknisk agent + fundamental agent + portfolio manager agent
* [ ] Multi-agent-diskusjon før råd
* [ ] AI-generert investeringsnotat per aksje
* [ ] Advisor med LLM-generert investeringskonklusjon
* [ ] Broker-import fra Nordnet
* [ ] Automatisk ordreimport
* [ ] E-postrapport/morgenrapport
* [ ] Bedre grafer og heatmaps
* [ ] Deployment på Mac Mini/lokal server
* [ ] Cloud/VPS
* [ ] SQLite/Postgres før datamengden krever det

---

## ✅ Ferdig (siste)

* [x] Recommendation Engine v1 som felles orkestrator for daglige handlinger
* [x] Stabilisering av agent-routing og felles screening-deduplisering
* [x] Comparison Engine v1.1 – bedre forklaring av hvorfor én kandidat vinner
* [x] Comparison Engine v1 – ticker-parser, deduplisering og konsistent profilscore
* [x] Strategy Screening v1
* [x] Opportunity Advisor v2 og relativ rangering
* [x] Full screening snapshot
* [x] Daily Refresh v2.1 – network preflight og retry
* [x] Daily Briefing v2.2
* [x] Score Explainability v1
* [x] Watchlist Advisor
* [x] Portfolio Snapshot – average cost
* [x] Strategy Profiles v2
* [x] Agent Chat v2 – Watchlist Advisor
* [x] Screening Engine v1
* [x] Opportunity Advisor (watchlist)
* [x] Daily Briefing v1
* [x] Daily Refresh v1
* [x] Screening Engine – Agent Chat
* [x] Analyst Consensus v1 steg 2 og 3
* [x] Analyst Advisor Layer v1
* [x] Sentiment v1
* [x] News v1
* [x] Earnings v1 (datoer, kalender og varsler)
* [x] Porteføljerisiko v1: posisjonsstørrelse, konsentrasjon, sektor, USA/Norden/OBX
* [x] Daily Flow v2: tydeligere «hva bør jeg gjøre i dag?»
* [x] Alerts v2: bedre handlingsvarsler
* [x] Full audit etter NaN-cache-fix
* [x] Fundamental historikk og ranking
* [x] Watchlist-ranking
* [x] Research Ideas
* [x] Watchlist-editor i UI
* [x] Dashboard redesign
* [x] Daily Flow/Morning Briefing
* [x] Alerts Engine v1
* [x] Agent Chat koblet til Daily Flow, portefølje og ordre
* [x] Portfolio- og ordrehistorikk
* [x] Pending orders, effektuering og kansellering
* [x] Test/prod-miljø
* [x] Alle brukerdata flyttet til JSON
* [x] Strategy classification og strategy profiles
* [x] Strategy-specific backtesting og walk-forward
* [x] Trailing-exit analyse
* [x] NaN-cache bug i Yahoo-data løst
