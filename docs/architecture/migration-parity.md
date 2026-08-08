# Paritetsmatrise for frontendmigrasjonen

Denne matrisen er porten for å gjøre den nye løsningen til standard. «Ikke i
spike» betyr at funksjonen fortsatt skal brukes i Streamlit inntil senere fase.

| Flate | Kritisk funksjon | Spike | Før cutover |
|---|---|---:|---:|
| I dag | Eide aksjer, watchlist, oppmerksomhet og kandidater | Ikke i spike | Påkrevd |
| Selskapsdetaljer | Direkte ticker-URL og tilbake/frem | Påkrevd | Påkrevd |
| Selskapsdetaljer | Perioder fra 1u til maks, candlesticks, volum, SMA20 og SMA50 | Påkrevd | Påkrevd |
| Selskapsdetaljer | Agentvurdering, fundamentalt og nyheter/hendelser | Ikke i spike | Påkrevd |
| Søk | Globalt ticker- og selskapssøk | Kun tickerfelt | Påkrevd |
| Chat | Kontekstuell forklaring fra felles anbefalingsgrunnlag | Ikke i spike | Påkrevd |
| Utforsk | Rangering, kandidater og strategiprofiler | Ikke i spike | Påkrevd |
| Administrer | Eid-status, GAV og watchlist | Forbudt i spike | Påkrevd |
| Modell og data | Modell-, data- og refresh-status, journal og validering | Ikke i spike | Påkrevd |
| Miljø | TEST/PROD og lokale data | Påkrevd | Påkrevd |
| Drift | Samme-origin produksjonsbygg og dokumentert lokal start | Påkrevd | Påkrevd |

## Rollback og datavern

Spiken har ingen brukerdata-skriving og kan fjernes uten datamigrasjon. Før
Administrer får skrive, skal gjeldende JSON-filer sikkerhetskopieres og testes i
TEST. I overgangsperioden skal bare én frontend ha skrivetilgang. Streamlit
beholdes som fallback til PROD-paritet og gjenoppretting etter omstart er
verifisert.
