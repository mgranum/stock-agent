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

Recommendation Engine bygger i tillegg `decisions`: nøyaktig én samlet
sluttbeslutning per ticker. For en eid aksje er porteføljerådet hovedrådet,
mens grunnmodellens vurdering lagres som `model_recommendation`. Risiko,
stop-oppfølging, earnings og andre materielle signaler lagres som
`supporting_actions`. For en ikke-eid aksje er modell-/kandidatrådet
hovedrådet.

`material` skiller nye handlinger som skal journalføres fra ren status, som et
uendret `HOLD`. UI og Decision Journal leser de samlede sluttbeslutningene;
`actions` beholdes som bakoverkompatibel kilde for Daily Briefing og chat under
den videre migreringen.

Manglende kursmål, stop, inngangsbetingelse eller datakvalitetsvurdering blir
stående som manglende eller `not_assessed`. Kontrakten skal ikke finne på data
som dagens modell ikke produserer.

## Bakoverkompatibilitet

De eksisterende presentasjonsfeltene beholdes midlertidig på anbefalingen.
Dette gjør at Daily Briefing og chat gir samme svar som før, samtidig som nye
konsumenter kan migreres til `decision` uten et stort samtidig omslag.

Kontrakten valideres av Pydantic ved opprettelse. Ugyldig action, scope,
tidshorisont, konfidens eller datakvalitetsstatus avvises tidlig.
