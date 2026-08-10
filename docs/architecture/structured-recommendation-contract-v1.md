# Strukturert anbefalingskontrakt v1

Dato: 2026-08-10

## Formål

Recommendation Engine er eneste eier av endelige handlingsråd. Kildene kan
fortsatt levere tekniske signaler, fundamentale vurderinger, risiko, hendelser
og kandidater, men API, UI, chat og Decision Journal skal lese den samme
strukturerte beslutningen.

Dette er en representasjonsendring. Scoring, prioritering, deduplisering,
porteføljelogikk, stop-loss og gevinstsikring er ikke endret.

## Kontrakt

Hver eksisterende anbefaling har et `decision`-objekt med:

* `contract_version` og frosset `model_version`
* kanonisk `ticker`, inkludert markedssuffiks som `.OL`
* maskinlesbar `action_code` og `scope`
* `time_horizon`, fastsatt til `days_to_weeks`
* valgfri `entry_condition`, `target_price` og `stop_level`
* en eller flere `reasons`
* valgfri `invalidation`
* `confidence`
* `data_quality` med status, tidspunkt og konkrete mangler

Manglende kursmål, stop, inngangsbetingelse eller datakvalitetsvurdering blir
stående som manglende eller `not_assessed`. Kontrakten skal ikke finne på data
som dagens modell ikke produserer.

## Bakoverkompatibilitet

De eksisterende presentasjonsfeltene beholdes midlertidig på anbefalingen.
Dette gjør at Daily Briefing og chat gir samme svar som før, samtidig som nye
konsumenter kan migreres til `decision` uten et stort samtidig omslag.

Kontrakten valideres av Pydantic ved opprettelse. Ugyldig action, scope,
tidshorisont, konfidens eller datakvalitetsstatus avvises tidlig.
