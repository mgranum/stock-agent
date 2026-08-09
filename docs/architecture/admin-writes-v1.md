# Kontrollerte skriveoperasjoner v1

Status: Fase 6.2 verifisert i TEST og kontrollert PROD

## Omfang

React-klienten bruker én felles `PUT /api/admin/stocks/{ticker}`-operasjon for
eid-status, GAV og medlemskap i redigerbare watchlists. Samme dialog åpnes fra
I dag, søk, selskapsdetaljer og Administrer.

PROD-skriving er sperret som standard. API-et returnerer HTTP 403 dersom
`STOCK_AGENT_ENABLE_PROD_WRITES=1` ikke er satt. Den første React-skrivingen tar
eierskap til brukerdataene gjennom `writer_owner.json`; eldre
Streamlit-skrivinger til posisjoner og watchlists avvises deretter, slik at bare
én applikasjon kan skrive under overgangen.

## Datamodell

En eid aksje krever positiv GAV. Eksisterende `shares` bevares, fordi feltet
fortsatt brukes av dagens risikoanalyse. For en ny posisjon lagres `shares=1`
som et kompatibilitetsfelt. Antall og total porteføljeverdi eksponeres ikke i
det nye grensesnittet. Scoring, stop-loss, gevinstsikring og anbefalingslogikk er
ikke endret.

## Backup og rollback

Før hver godkjente mutasjon lagres en tidsstemplet kopi av `portfolio.json`,
`watchlists.json` og status for `writer_owner.json` under miljøets
`backups`-mappe. Dersom andre filskriving feiler, gjenopprettes all opprinnelig
tilstand automatisk.

TEST kan rulles tilbake med
`POST /api/admin/rollback/{backup_id}`. Backup-id og miljø valideres før
gjenoppretting. Verifikasjonen i fase 4 skrev en uendret NVDA-posisjon, opprettet
backup og bekreftet at begge filene var identiske etter rollback.

I fase 6.2 ble en semantisk uendret PROD-operasjon gjennomført på den unike
SUBC.OL-posisjonen og rullet tilbake umiddelbart. Portefølje, watchlists og
opprinnelig fravær av writer-owner ble gjenopprettet. Read-only PROD-paritet
bestod deretter 83/83 kontroller. Backupen beholdes som revisjonsspor.
