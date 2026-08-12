# Decision Journal v1

Dato: 2026-08-10

## Formål

Decision Journal fryser de materielle rådene Recommendation Engine faktisk
ga. Journalen er grunnlaget for senere fremoverskuende måling, men utfører
ingen handler og antar ikke at brukeren fulgte rådet.

## Lagring

Daily Refresh lagrer ett atomisk JSON-dokument per signaldato i:

`snapshots/decision_journal/<miljø>/decisions_YYYY-MM-DD.json`

En ny kjøring samme dag erstatter dagens fil. Stabil `entry_id` og eksisterende
`dedupe_key` hindrer at samme slutt-råd telles flere ganger. Filene er lokale
runtime-data, er separert mellom TEST og PROD, og ignoreres av Git.

Hver post inneholder:

* signaldato, UTC-tidspunkt og modellversjon
* kilde, regel, prioritet og dedupliseringsnøkkel
* hele den validerte, samlede sluttbeslutningen fra Recommendation Engine
* et lite evidensobjekt med eksisterende begrunnelse og kategori

Manglende inngangsbetingelse, kursmål, stop, invalidasjon eller datakvalitet
beholdes som manglende. Journalen skal dokumentere hva modellen visste, ikke
etterfylle informasjon i ettertid.

Journalen lagrer bare sluttbeslutninger merket `material`. Status uten ny
handling, som et uendret `HOLD`, er fortsatt tilgjengelig i UI og API, men
oppretter ikke en kunstig ny journalhendelse hver dag.

## Avgrensning

Denne versjonen registrerer rådet. Den registrerer foreløpig ikke om brukeren
fulgte det. Dette skal eventuelt registreres eksplisitt og holdes adskilt fra
modellens opprinnelige beslutning.

## Resultatevaluering

Daily Refresh evaluerer journalpostene mot justerte kursdata fra første
børsåpning etter signaldatoen. Resultatene lagres separat i:

`snapshots/decision_journal_outcomes/<miljø>/outcomes.json`

For 5, 10, 20 og 40 handelsdager lagres avkastning samt maksimal positiv og
negativ kursutvikling. Absolutte kursmål og stop-nivåer kontrolleres mot
ujustert high/low, mens avkastningen bruker justerte priser for å unngå at
splitt og tilsvarende hendelser fremstår som modellresultat.

Manglende fremtidige dager markeres `pending`; delvis modne råd markeres
`partial`; manglende eller ugyldige prisdata markeres eksplisitt som `error`
eller `insufficient`. Originaljournalen endres aldri av evalueringen.
