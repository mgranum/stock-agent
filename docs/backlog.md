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

### Arkitekturprinsipper for neste versjon

* Behold Python og eksisterende domene-, analyse- og anbefalingslogikk.
* Bygg ny frontend med React, TypeScript og Vite.
* Legg et tynt, typet FastAPI-lag mellom frontend og Python-kjernen.
* Behold Daily Refresh som en separat Python-jobb.
* Behold lokal drift, TEST/PROD-separasjon og lokale datafiler i første omgang.
* Bruk kun dagsdata; laveste periode i alle flater er 1u. Intradagdata er ikke
  del av målbildet.
* Migrer trinnvis; Streamlit skal fungere til ny løsning har dokumentert paritet.
* Ikke endre scoring, anbefalinger, trend, stop-loss eller porteføljelogikk som
  del av UI-migrasjonen.

---

## Arbeidsrekkefølge

1. Fortsett fremoverskuende modellvalidering uten å endre den frosne modellen.
2. Gjennomfør en avgrenset, skrivebeskyttet arkitekturspike.
3. Etabler API-kontrakter og migrer leseflatene trinnvis.
4. Migrer vedlikehold av eide aksjer, GAV og watchlists med bare én aktiv skriver.
5. Migrer Utforsk, chat og Modell og data.
6. Verifiser funksjonell paritet og avvikle Streamlit kontrollert.

Hver fase skal kunne stoppes eller rulles tilbake uten å ødelegge eksisterende
data eller den fungerende Streamlit-appen.

---

## 🔥 Aktivt – Model Validation & Decision Journal v1

Målet er å finne ut om agenten faktisk tilfører verdi, ikke å optimalisere den
før målegrunnlaget er troverdig.

### Discovery-univers og kandidatvalg

* [ ] Definer regler for notering og markedsverdi
* [ ] Håndter nye noteringer, avnoteringer og tickerendringer
* [ ] Kjør full analyse bare på et begrenset antall topprangerte kandidater
* [ ] Begrens sektor- og regionskonsentrasjon i kandidatlisten
* [ ] Backtest hele kjeden fra historisk univers til kandidat og neste-dags
  utførelse når point-in-time-data gjør dette forsvarlig
* [ ] Mål hit-rate, turnover, drawdown og meravkastning uten dagens watchlist

### Strukturert anbefalingskontrakt

* [ ] Definer én kontrakt for action, scope, tidshorisont,
  inngangsbetingelse, kursmål, stop, begrunnelser, invalidasjon, konfidens og
  datakvalitet
* [ ] La Recommendation Engine være eneste eier av det endelige rådet

### Bias, referanser og beslutningsgrunnlag

* [ ] Audit for survivorship bias i screening-univers
* [ ] Verifiser at historiske fundamentaler bare bruker informasjon som var
  kjent på analysetidspunktet
* [ ] Dokumenter og implementer håndtering av avnoterte selskaper
* [ ] Sammenlign mot relevante lokale markedsindekser per region
* [ ] Implementer en enkel trend-/momentumreferanse
* [ ] Sammenlign dagens komplette modell mot referansene på identiske perioder
  og kostnadsantakelser
* [ ] Rapporter resultat separat per strategiprofil
* [ ] Definer skriftlige godkjenningskriterier før modellen kan sies å skape
  merverdi

### Decision Journal

* [ ] Lagre alle materielle råd med tidspunkt, modellversjon og tilgjengelige
  inputdata
* [ ] Lagre anbefalt inngang, kursmål, stop, tidshorisont, konfidens og
  invalidasjonsgrunn
* [ ] Registrer om brukeren fulgte rådet, uten å blande dette med
  modellresultatet
* [ ] Mål maksimal positiv og negativ kursutvikling etter rådet
* [ ] Registrer om kursmål eller stop ble truffet først
* [ ] Lag en aggregert rapport for faktisk fremoverskuende presisjon og
  avkastning
* [ ] Vis datadekning og marker råd som ikke kan evalueres pålitelig

### Beslutningsport

* [ ] Ikke endre scoring eller anbefalingsregler før baseline og bias-audit er
  ferdig
* [ ] Ikke øk kapital basert på modellen før et tilstrekkelig fremoverskuende
  datagrunnlag foreligger
* [ ] Behold modellen uendret dersom en foreslått forbedring bare virker
  in-sample
* [ ] Forenkle modellen dersom den komplette modellen ikke stabilt slår en
  enklere referanse etter risiko og kostnader
* [ ] Dokumenter beslutningen: fortsett, juster, forenkle eller stopp aktiv
  aksjeplukking

---

## 🧭 Neste – trygg migrasjon til React og FastAPI

Migrasjonen skal erstatte presentasjonslaget, ikke investeringsmodellen. Ny og
gammel frontend skal bruke samme Python-logikk og de samme lokale dataene til
Streamlit kan avvikles.

### Fase 0 – beslutninger og migrasjonsvern

* [x] Skriv en kort arkitekturbeslutning som dokumenterer React + TypeScript +
  Vite, FastAPI, Lightweight Charts og hvorfor Streamlit fases ut
* [x] Dokumenter hvilke moduler som er domene-/applikasjonslogikk og hvilke
  deler av `app.py` som kun er presentasjon
* [x] Definer paritetsmatrise for I dag, selskapsdetaljer, søk, chat, Utforsk,
  Administrer og Modell og data
* [x] Definer eksplisitte rollback-kriterier og sikkerhetskopi av brukerdata før
  hver fase med skriveoperasjoner
* [x] Frys nye Streamlit-flater; tillat bare feilretting frem til avvikling

### Fase 1 – skrivebeskyttet arkitekturspike

* [x] Sett opp en minimal FastAPI-applikasjon og en minimal React/TypeScript/Vite-
  klient uten å flytte eksisterende logikk
* [x] Server ferdigbygget frontend fra FastAPI på samme origin ved lokal kjøring
* [x] Lag én typet, skrivebeskyttet API-ressurs for selskapsdetaljer basert på
  eksisterende Python-funksjoner
* [x] Lag én selskapsdetaljside med direkte URL, eksempelvis `/stocks/NVDA`
* [x] Vis virkelig kursdata med felles periodevalg: 1u, 1m, 3m, 6m,
  i år, 1 år, 3 år og maks
* [x] Verifiser candlesticks, volum og glidende snitt uten å kjøre hele analysen
  på nytt ved hver UI-interaksjon
* [x] Bevar nettleserens tilbake-/fremoverhistorikk og last siden korrekt fra en
  direkte ticker-URL
* [x] Dokumenter én lokal startkommando for spiken og bevar TEST/PROD
* [x] Stopp og vurder rammeverksvalget før videre migrasjon dersom spiken ikke
  oppfyller akseptansekriteriene

### Fase 2 – API-grense og datatrygghet

* [ ] Innfør små presentasjons-/query-tjenester mellom API-et og eksisterende
  context; ikke eksponer hele interne context-objektet
* [ ] Definer Pydantic-kontrakter og eksplisitt håndtering av tomme, manglende,
  ugyldige og utdaterte data
* [ ] Etabler API-er for `today`, selskapsdetaljer, søk, Utforsk,
  posisjoner, watchlists, modellstatus, chat og refresh-status
* [ ] Sikre at ticker, selskapsnavn, anbefaling og modellversjon har én felles
  identitet på tvers av API-ressursene
* [ ] Gjør lokale JSON-skrivinger atomiske og beskytt dem mot samtidige
  skriveoperasjoner før ny frontend får skrive
* [ ] Bruk ordinær HTTP og kontrollert polling først; innfør bare streaming eller
  WebSocket ved dokumentert behov
* [ ] Legg til kontraktstester for API-et og regresjonstester mot eksisterende
  Python-resultater

### Fase 3 – leseflater

* [ ] Bygg I dag som primærflate med eide aksjer, watchlist og tre sidestilte
  nye kandidater
* [ ] Bygg full selskapsdetalj med kursutvikling, agentvurdering,
  selskapsvurdering, fundamentalt og nyheter/neste hendelser
* [ ] Bruk samme periodevalg i I dag og selskapsdetaljer
* [ ] Gjør alle ticker- og selskapsnavn til lenker til samme selskapsdetalj
* [ ] Bygg globalt søk etter ticker og selskapsnavn
* [ ] Bevar valgt flate, ticker og periode når søk eller chat åpnes og lukkes
* [ ] Bygg responsiv oppførsel og tastaturnavigasjon for de viktigste flytene
* [ ] Sammenlign innhold og råd med Streamlit på et fast sett tickere og
  datasituasjoner

### Fase 4 – Administrer og kontrollerte skriveoperasjoner

* [ ] Bygg én redigeringsflyt for eid/ikke eid, GAV og watchlist-medlemskap fra
  søk, ticker-rad, selskapsdetaljer og Administrer
* [ ] Behold risiko-, stop-loss- og gevinstsikringslogikk for eide aksjer
* [ ] Avklar om antall aksjer fortsatt skal lagres for konsentrasjonsrisiko, uten
  at samlet porteføljeverdi vises i grensesnittet
* [ ] La bare én applikasjon skrive eide aksjer, GAV og watchlists under
  overgangsperioden
* [ ] Valider input, vis tydelig lagringsstatus og test avbrutte/feilede
  skriveoperasjoner
* [ ] Verifiser sikkerhetskopi og rollback med kopier av TEST-data før PROD-data
  kan endres

### Fase 5 – øvrige flater

* [ ] Bygg Utforsk med rangering av watchlist, kjøpskandidater,
  kvalitetsselskaper, sykliske, underdogs, strategiprofiler og screening
* [ ] Bygg kontekstuell chat som forklarer strukturerte analyser uten en
  parallell investeringsmodell
* [ ] Bygg Modell og data med modellversjon, datakvalitet, refresh-status,
  snapshots, Decision Journal, backtest og walk-forward
* [ ] Flytt detaljerte grafverktøy og analyseindikatorer til selskapsdetaljer
* [ ] Legg til tilgjengelige feilmeldinger og tomtilstander uten å eksponere
  interne stack traces

### Fase 6 – paritet, overgang og avvikling

* [ ] Kjør paritetsmatrisen i TEST og deretter en kontrollert PROD-verifikasjon
* [ ] Verifiser at anbefaling, risiko, stop-loss og gevinstsikring er uendret for
  representative eide aksjer og kandidater
* [ ] Verifiser refresh, cache, direkte ticker-lenker, tilbakeknapp og
  gjenoppretting etter omstart
* [ ] Kjør automatiserte backend-, API- og frontendtester samt manuelle kritiske
  brukerflyter
* [ ] Dokumenter installasjon, lokal drift, bygging, backup og rollback
* [ ] Gjør ny løsning til standard først etter godkjent brukerakseptanse
* [ ] Behold Streamlit som kortvarig fallback etter første cutover
* [ ] Fjern Streamlit og tilhørende presentasjonskode først når paritet og
  datatrygghet er dokumentert

---

## 🚀 Produktfunksjoner etter grunnmigrasjonen

Disse punktene skal bygges på de nye API-kontraktene og den vedtatte
informasjonsarkitekturen.

### I dag og anbefalinger

* [ ] Prioriter «Krever handling», «Endret siden sist», «Risiko» og «Beste nye
  mulighet»
* [ ] Samle motstridende signaler i ett råd med eksplisitt konfliktforklaring
* [ ] Vis forventet oppside, risiko til stop og reward/risk for kjøpskandidater
* [ ] Vis hvorfor et råd er nytt eller endret
* [ ] Vis datatidspunkt, datakvalitet og modellversjon sammen med rådene
* [ ] Bygg Daily Briefing v3 på den strukturerte anbefalingskontrakten
* [ ] Legg til agentisk overvåkning/endringsvarsler uten dupliserte handlinger

### Chat

* [ ] Skill agent-routing fra svarformatering i `agent.py`
* [ ] Definer et lite verktøygrensesnitt for daglige råd, risiko,
  tickerforklaring, sammenligning, screening og endringer siden sist
* [ ] La chat bruke Recommendation Engine som kilde til endelige råd
* [ ] Lag en chat-eksempelsamling med regresjonstester
* [ ] Bedre samtalekontekst: «disse», «dem», «den andre» og «forrige resultat»
* [ ] Bedre synonym- og intensjonsmatching
* [ ] Dedupliser topplister og kandidatlister
* [ ] Gjør sammenligninger kontekstbevisste for tidshorisont, investeringsmål,
  eide aksjer og watchlist
* [ ] Bruk eventuell LLM til språk, oppsummering og forklaring – ikke til å
  beregne score eller fatte råd

---

## 🗑️ Skal avvikles – ordre og ordrehistorikk

Ordre er ikke en del av målbildet. Kjøp registreres ved å markere en aksje som
eid og angi GAV. Salg registreres ved å markere den som ikke eid eller fjerne
den fra listen over eide aksjer.

* [ ] Fjern Ordre- og Historikk-flatene
* [ ] Fjern pending ordre fra context, Alerts, Daily Flow, Recommendation Engine
  og Agent Chat uten å endre øvrig anbefalings- eller porteføljelogikk
* [ ] Arkiver eller migrer lokal lagring av pending ordre og ordrehistorikk på
  en kontrollert og gjenopprettelig måte
* [ ] Erstatt ordrebasert oppdatering med direkte vedlikehold av eid-status og
  GAV
* [ ] Legg til regresjonstester som bekrefter at ordrehandlinger og ordrespørsmål
  er fjernet
* [ ] Hold Decision Journal adskilt fra tidligere ordrehistorikk; journalen skal
  dokumentere agentens råd og resultater, ikke simulere handler

---

## 🛡️ Datakvalitet og robusthet

* [ ] Audit av alle kall til `get_daily_prices()`
* [ ] Gjennomgang av cache-strategi og ferskhetsregler per datatype
* [ ] Skill mellom manglende, utdatert og negativ informasjon
* [ ] Lag datakvalitetsscore og eksplisitt «ikke nok data til råd»
* [ ] Oppdag ekstreme eller åpenbart feilaktige leverandørverdier
* [ ] Sikre robusthet mot Yahoo/yfinance-feil
* [ ] Strukturere testmiljø bedre
* [ ] Kjør sekundære datakilder i shadow mode før de påvirker råd
* [ ] Vurder sekundær kilde for historiske regnskapstall og rapporteringsdatoer
* [ ] Vurder sekundær kilde for earningsdatoer og nordiske børsmeldinger

---

## 🧹 Dokumentasjon og teknisk gjeld

* [ ] Skriv README med formål, begrensninger, installasjon og kjøring
* [ ] Erstatt placeholder-metadata i `pyproject.toml`
* [ ] Dokumenter datafiler, cache, snapshots og backupbehov
* [ ] Definer retention- og `.gitignore`-policy for logger og snapshots
* [ ] Gjør utviklingskommandoer eksplisitt TEST der det er praktisk
* [ ] Reduser brede eller ignorerte `except Exception` der feil bør være synlige
* [ ] Vurder SQLite når Decision Journal gjør JSON upraktisk
* [ ] Rydd gamle worktrees og agent-branches

---

## 📊 Senere – modellutvikling etter validert baseline

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
* [ ] Historisk porteføljesammenligning per ticker i chat

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
* [ ] Deployment på Mac Mini/lokal server
* [ ] Cloud/VPS
* [ ] Postgres eller annen hosted database

---

## ✅ Ferdig – grunnlag og vedtatte beslutninger

### Produkt- og designbeslutninger

* [x] Erstatt 13 likestilte faner med færre, prioriterte flater og en enkel meny
* [x] Bruk I dag som primærflate og selskapsdetaljer som felles mål for ticker-
  og selskapslenker
* [x] Bruk globalt søk og kontekstuell chat på tvers av flatene
* [x] Samle discovery, screening og strategiprofiler i Utforsk
* [x] Samle eide aksjer, GAV og watchlist-vedlikehold i Administrer
* [x] Samle modell- og datastatus, journal og validering i Modell og data
* [x] Bruk samme periodevalg i I dag og selskapsdetaljer: 1u, 1m, 3m, 6m,
  i år, 1 år, 3 år og maks
* [x] Ikke vis samlet porteføljeverdi; dette følges i Nordnet
* [x] Definer kjøp som å markere en aksje som eid og registrere GAV
* [x] Definer salg som å markere aksjen som ikke eid eller fjerne den fra listen
  over eide aksjer
* [x] Beslutt at pending ordre og ordrehistorikk ikke skal videreføres
* [x] Velg React + TypeScript + Vite og FastAPI som målarkitektur, med
  eksisterende Python-kjerne og trinnvis migrasjon

### Discovery og modellvalidering levert

* [x] Skill discovery-kandidater fra watchlist og dedupliser regionale treff
* [x] Bygg Opportunity Advisor og Recommendation Engine fra
  discovery-kandidater
* [x] Etabler reproduserbare univers-snapshots for USA og Norden
* [x] Innfør pris-, likviditets- og datakvalitetsfiltre før fullanalyse
* [x] Hent prisdata batchvis, gjenbruk cache og fordel analysekapasitet mellom
  likviditetssegmenter og rotasjon
* [x] Rapporter filtreringsårsaker, feil og antall vurderte/analyserte selskaper
* [x] Start fremoverskuende discovery-journal og evaluer etter 5, 10, 20 og 40
  handelsdager
* [x] Sammenlign modne discovery-kohorter med ACWI og relevant lokal benchmark
* [x] Frys produksjonsmodellen med eksplisitt `model_version` og dokumenter
  dagens regler og konkurrerende råd
* [x] Gjennomfør look-ahead-audit, realistisk signaltidspunkt og
  kostnadsjustering
* [x] Skill in-sample, kalibrering, historisk test og urørt out-of-sample
* [x] Bruk rolling walk-forward som obligatorisk kontroll før modellendringer
* [x] Implementer buy-and-hold-referanse og rapportering av sentrale risiko- og
  avkastningsmål per region

### Produktfunksjoner levert i eksisterende app

* [x] Recommendation Engine v1 som felles orkestrator for daglige handlinger
* [x] Daily Briefing v2.2, Daily Flow v2, Alerts v2 og Daily Refresh v2.1
* [x] Dokumenterte snapshot-endringer i «Endret siden sist», korrekt Watchlist-
  bevaring og rangering av discovery-kandidater etter rank
* [x] Screening Engine, Strategy Screening, Strategy Profiles og Research Ideas
* [x] Opportunity Advisor v2, Watchlist Advisor og watchlist-ranking
* [x] Comparison Engine v1.1 og Score Explainability v1
* [x] Agent Chat v2 med screening, Daily Flow, eide aksjer og watchlist
* [x] Selskapsdata for analytikerkonsensus, sentiment, nyheter og earnings
* [x] Porteføljerisiko, GAV, trailing-exit-analyse og grunnleggende historikk
* [x] Strategy-specific backtesting og walk-forward
* [x] TEST/PROD-miljø og JSON-basert lagring av brukerdata
* [x] Stabilisering av agent-routing, screening-deduplisering, Yahoo-cache og
  Daily Refresh ved nettverksfeil

### Historisk levert, men besluttet avviklet

* [x] Pending orders, effektuering og kansellering
* [x] Ordre- og ordrehistorikk
