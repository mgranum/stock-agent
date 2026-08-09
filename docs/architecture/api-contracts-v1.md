# API-kontrakter v1

Status: Fase 2 fullført

API-et er et presentasjonslag foran eksisterende Python-logikk. Det returnerer
små, typede modeller og eksponerer aldri hele interne `context`, DataFrames eller
lagringsobjekter.

## Ressurser

| Metode | Ressurs | Formål |
|---|---|---|
| GET | `/api/today` | Oppmerksomhet, eide aksjer, watchlist og kandidater |
| GET | `/api/stocks/{ticker}` | Skrivebeskyttede selskaps- og kursdetaljer |
| GET | `/api/search?q=` | Søk i kjente tickere og selskapsnavn |
| GET | `/api/explore` | Watchlist-rangering og discovery-kandidater |
| GET | `/api/positions` | Eide aksjer, GAV og eksisterende risiko-/rådsfelt |
| GET | `/api/watchlists` | Navngitte watchlists og medlemskap |
| GET | `/api/model-status` | Modellversjon, snapshotstatus og refresh-status |
| GET | `/api/refresh/status` | Pollbar status for Daily Refresh |
| POST | `/api/chat` | Tekstlig forklaring fra eksisterende Agent Chat |

Posisjoner og watchlists er kun lesbare i fase 2. Skriveendepunkter aktiveres i
Administrer-fasen etter eksplisitt TEST-verifikasjon og backup/rollback.

## Felles metadata

Context-baserte svar har `meta` med miljø, modellversjon, byggetidspunkt,
snapshotdato og én av statusene:

* `fresh`: snapshotet er gyldig og høyst 24 timer gammelt
* `stale`: snapshotet er gyldig, men eldre enn 24 timer
* `missing`: snapshotet mangler
* `invalid`: snapshotet finnes, men kan ikke leses eller valideres

Leseflater returnerer trygge tomme lister sammen med status når analysedata
mangler. Chat returnerer HTTP 503 fordi den ikke kan gi et pålitelig svar uten
context. Ugyldig input returnerer HTTP 422.

## Identitet og råd

Ticker normaliseres til store bokstaver. Selskapsnavn løses fra eksisterende
rapporter før navnecache brukes. Grunnanbefalingen kommer fra samme
watchlistanalyse på tvers av I dag, Utforsk og Posisjoner; posisjonsspesifikke
råd ligger i et separat `portfolio_action`-felt. Modellversjon følger alle
context-baserte ressurser i `meta`.

## Transport

Fase 2 bruker ordinær HTTP. Refresh-status kan poll-es. WebSocket og streaming
innføres bare dersom en senere brukerflyt dokumenterer et reelt behov.

## Datavern

JSON for brukerdata, context-snapshot, refresh-status og konfigurasjon skrives
via en atomisk tempfil og `os.replace`. En prosess- og trådsikker fillås
beskytter samtidige read-modify-write-operasjoner. Feil før erstatning bevarer
forrige gyldige fil og rydder tempfilen.
