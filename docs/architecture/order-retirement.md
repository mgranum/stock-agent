# Avvikling av ordre og ordrehistorikk

Dato: 2026-08-10

## Resultat

Ordre er fjernet fra applikasjonsflyten. Kjøp registreres ved å markere en aksje
som eid og angi GAV. Salg registreres ved å markere aksjen som ikke eid eller
fjerne den fra listen over eide aksjer.

Følgende koblinger er fjernet:

* lasting og lagring av pending ordre og ordrehistorikk
* ordrebygging og simulert utførelse
* ordrevarsler og ordrekonflikter
* ordresammendrag og ordrehandlinger i Daily Flow
* ordreprioritering i Recommendation Engine og Daily Briefing
* ordrespørsmål og ordretekst i Agent Chat
* ordrelasting under Daily Refresh og context-bygging

Risiko-, stop-loss- og gevinstsikringsvarsler er beholdt. Handlingen «Følg
stop-nivå» er nå uttrykkelig en oppfølgingshandling, ikke forberedelse av en
ordre.

## Arkiverte brukerdata

De opprinnelige datafilene er flyttet uendret til lokale, miljøseparerte arkiv:

* `data/test/archive/orders/`
* `data/prod/archive/orders/`

PROD-filene var tomme ved arkivering. TEST inneholdt én pending ordre og én
historikkoppføring. Arkivene brukes ikke av runtime og kan flyttes tilbake ved
behov.

Decision Journal er ikke endret og er fortsatt dokumentasjon av agentens råd
og etterfølgende resultater, ikke en handelssimulator.
