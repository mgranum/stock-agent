# Kontrollerte skriveoperasjoner v1

Status: Fase 4 implementert i TEST

## Omfang

React-klienten bruker én felles `PUT /api/admin/stocks/{ticker}`-operasjon for
eid-status, GAV og medlemskap i redigerbare watchlists. Samme dialog åpnes fra
I dag, søk, selskapsdetaljer og Administrer.

PROD-skriving er hardt sperret. API-et returnerer HTTP 403 dersom miljøet ikke
er TEST. Den første React-skrivingen tar eierskap til brukerdataene gjennom
`writer_owner.json`; eldre Streamlit-skrivinger til posisjoner og watchlists
avvises deretter, slik at bare én applikasjon kan skrive under overgangen.

## Datamodell

En eid aksje krever positiv GAV. Eksisterende `shares` bevares, fordi feltet
fortsatt brukes av dagens risikoanalyse. For en ny posisjon lagres `shares=1`
som et kompatibilitetsfelt. Antall og total porteføljeverdi eksponeres ikke i
det nye grensesnittet. Scoring, stop-loss, gevinstsikring og anbefalingslogikk er
ikke endret.

## Backup og rollback

Før hver godkjente mutasjon lagres en tidsstemplet kopi av både
`portfolio.json` og `watchlists.json` under miljøets `backups`-mappe. Dersom
andre filskriving feiler, gjenopprettes begge originalfilene automatisk.

TEST kan rulles tilbake med
`POST /api/admin/rollback/{backup_id}`. Backup-id og miljø valideres før
gjenoppretting. Verifikasjonen i fase 4 skrev en uendret NVDA-posisjon, opprettet
backup og bekreftet at begge filene var identiske etter rollback.
