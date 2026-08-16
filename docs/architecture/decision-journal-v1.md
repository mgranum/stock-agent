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

### Benchmark-relativ evaluering

Kjøpsråd (`consider_buy`) sammenlignes også med `ACWI` fra første tilgjengelige
børsåpning etter samme signaldato og over de samme 5, 10, 20 og 40
handelsdagshorisontene. Både aksjen og referansen bruker justerte priser.
Bruttoavkastning beholdes for sporbarhet. I tillegg beregnes nettoavkastning
med samme hypotetiske kapital og de eksisterende konfigurerbare forutsetningene
for kurtasje, minimumskurtasje, spread og valuta. Netto meravkastning er aksjens
nettoavkastning minus ACWIs nettoavkastning.

Andre handlinger holdes utenfor den aggregerte benchmark-statistikken. Et råd
om å redusere, beskytte eller følge opp en posisjon kan ikke tolkes som et
kjøpsråd uten en egen, eksplisitt retningsmodell.

Benchmark-statistikk skjules til minst 30 sammenlignbare kjøpsråd har nådd den
aktuelle horisonten. Benchmark-grunnlaget markeres klart for vurdering først
når minst 60 kjøpsråd har fullført 40 handelsdager. Dette er en datamodenhetsport,
ikke i seg selv dokumentasjon på meravkastning.

Hvert kjøpsråd sammenlignes i tillegg med en lokal markedsreferanse: `SPY` for
USA, `OSEBX.OL` for Norge, `^OMX` for Sverige, `^OMXC25` for Danmark og
`^OMXH25` for Finland. Lokal brutto- og netto meravkastning beregnes på de samme
horisontene og med aksjens regionale kostnadsforutsetninger. Statistikken
skjules til minst 30 modne råd per lokal referanse og horisont. Lokale
resultater er sekundær diagnostikk og inngår ikke i ACWI-beslutningsporten.

### Enkel trend-/momentumreferanse

Nye kjøpsråd får også et prospektivt signal fra `trend_momentum_v1`. Referansen
er bevisst enkel: `STERK OPPTREND` og ikke-negativ 20-dagers relativ styrke.
Regel, signalverdier og et regelfingeravtrykk lagres på signaltidspunktet.

På hvert av modellens kjøpsråd kjøper referansen samme aksje på samme neste
børsåpning dersom regelen er oppfylt; ellers står den i kontanter. Modell og
referanse måles med samme hypotetiske kapital, kostnadsmodell og 5, 10, 20 og
40 handelsdager. Dette isolerer om fullmodellen tilfører verdi utover den enkle
trend-/momentumregelen.

Råd fra før referansen ble innført etterfylles ikke med dagens tekniske data.
Statistikk vises først ved minst 30 sammenlignbare råd per horisont. Referansen
er sekundær diagnostikk, har ingen egen godkjenningsport og endrer ikke
ACWI-beslutningsporten eller produksjonsrådene.

Region og primær strategiprofil lagres sammen med hvert nytt råd slik de var
kjent på signaltidspunktet. Manglende profil lagres eksplisitt som `unknown`.
Eldre journalposter etterfylles ikke med dagens klassifisering.

### Låst beslutningsport `2026.08.15-v2`

`v2` erstattet bruttoporten `v1` før noen råd hadde nådd 40 dager. Porten bruker
bare nettoresultater. Kostnadsforutsetningene leses fra
`data/config/backtest_validation_config.json`; kapital og et fingerprint lagres
med evalueringen slik at endringer eller blandede forutsetninger blir synlige.

Porten gir ingen vurdering før minst 60 kjøpsråd har fullført 40 handelsdager.
Deretter må alle kriteriene være oppfylt samtidig:

1. Samme kostnadsmodell brukes for alle modne råd.
2. Gjennomsnittlig netto meravkastning mot ACWI er større enn null etter 10, 20
   og 40 handelsdager.
3. Mer enn 50 prosent av kjøpsrådene slår ACWI netto etter 20 og 40 handelsdager.
4. Median netto meravkastning er minst null etter 20 og 40 handelsdager.
5. Gjennomsnittlig netto meravkastning er fortsatt positiv etter at de beste 5
   prosentene av resultatene er fjernet, både etter 20 og 40 handelsdager.
6. Minst 90 prosent av de modne rådene har kjent region og profil.
7. Ingen enkeltregion eller -profil utgjør mer enn 80 prosent av de modne rådene.
8. Minst to regioner og to profiler, hver med minst 10 modne råd, har positiv
   gjennomsnittlig netto meravkastning.

En bestått port betyr at de forhåndsdefinerte kriteriene er oppfylt. Den endrer
ikke modellen automatisk og er ikke alene bevis for varig fremtidig alfa.
