# Backtest Validation v1

## Konklusjon

Backtesten for produksjonsmodell `2026.07.23-v1` er **ikke godkjent som
beslutningsgrunnlag**. Auditen fant én bestått kontroll og sju blokkerende
forhold. Historiske avkastningstall kan brukes til utviklingsdiagnostikk, men
ikke som dokumentasjon på at modellen skaper merverdi.

Den maskinlesbare valideringsporten ligger i
`src/backtest_validation.py`. Dashboardet viser samme status før resultatene.

## Funn og kodebevis

| Område | Status | Bevis i dagens implementasjon |
|---|---|---|
| Tekniske signaler | Bestått | `_technical_result_at()` avgrenser aksje- og benchmarkdata til og med aktuell signaldato. |
| Historiske fundamentaler | Blokkert | `analyze_fundamentals()` og `analyze_fundamental_history()` kalles én gang før løkken; samme nåtidsresultat brukes på alle historiske datoer. |
| Signaltidspunkt | Blokkert | Signal beregnes fra dagens `close`, og kjøp/salg bokføres umiddelbart til samme `close`. |
| Kostnader | Blokkert | Kontantbevegelsene bruker bare `shares * price`; kurtasje, spread og valuta mangler. |
| Splits og utbytte | Blokkert | yfinance lastes med `auto_adjust=False`, mens backtesten bruker `close`; `adjusted_close` og utbyttekontantstrøm brukes ikke. |
| Survivorship bias | Blokkert | Kjøringen mottar dagens watchlist og har ingen daterte univers-snapshots eller avnoterte selskaper. |
| Datasett-splitt | Blokkert | Perioder er relative strenger som `1y` og `6mo`, ikke faste, ikke-overlappende datointervaller. |
| Walk-forward | Blokkert | “Train” og “test” hentes hver for seg bakover fra samme kjøredato og kan derfor overlappe. |

## Konsekvens

Den største feilkilden er point-in-time-bruddet for fundamentaler. Dagens
regnskapstall kan påvirke et signal flere år tilbake. Selv perfekte
kostnadsantakelser eller flere nøkkeltall kan ikke gjøre en slik test gyldig.

At signal og handel skjer på samme sluttkurs gir i tillegg en pris som ikke var
tilgjengelig etter at signalet var ferdig beregnet. Ujusterte priser kan skape
kunstige stoppsignaler ved splits og undervurdurderer totalavkastning når
utbytte ikke håndteres.

## Krav før baseline kan godkjennes

1. Velg en point-in-time fundamental datakilde, eller definer en separat
   teknisk-only baseline som ikke bruker fundamentaler.
2. Beregn signal på dag `t` og utfør tidligst på open dag `t+1`.
3. Legg kurtasje, halv spread og valutaeffekt i felles konfigurasjon for både
   modell og benchmarks.
4. Bruk en dokumentert total-return-serie og test splits, utbytte, manglende
   data og avnotering eksplisitt.
5. Lagre daterte univers-snapshots.
6. Innfør faste dato-intervaller for in-sample, kalibrering og urørt
   out-of-sample.
7. Erstatt dagens relative walk-forward-vinduer med kronologiske folds.

Ingen score-, anbefalings-, stop- eller porteføljeregler ble endret i denne
auditen.

## Teknisk valideringsbaseline

`src/technical_baseline.py` gir en separat `technical_only_v1`-baseline som kan
brukes mens point-in-time fundamentaler mangler. Den endrer ikke
produksjonsmodellen.

Baseline-reglene er:

- signalet beregnes etter close på handelsdag `t`
- kjøp og salg utføres på justert open på neste tilgjengelige handelsdag
- teknisk inngang krever score minst 70, sterk opptrend og ikke-negativ relativ
  styrke
- hard stop og trailing/trend-exit bruker eksisterende exit-hjelpefunksjon
- sluttverdi verdsetter en åpen posisjon etter estimerte salgskostnader
- buy-and-hold bruker samme startkapital, periode og kostnadsmodell

Alle antakelser ligger i
`data/config/backtest_validation_config.json`. Standardprofilen bruker:

| Antakelse | Norden | USA/øvrige |
|---|---:|---:|
| Kurtasje | 0,10 % | 0,10 % |
| Minimumskurtasje i simuleringens valuta | 49 | 9,90 |
| Spread per side | 0,10 % | 0,10 % |
| Valutapåslag per side | 0 % | 0,25 % |

Minimumskurtasjen for USA er en praktisk omregnet simuleringsantakelse, ikke en
historisk valutakurs. Resultatene viser den anvendte profilen. Kostnadene er
konfigurerbare fordi Nordnet-priser avhenger av kurtasjeklasse, marked og
kontotype.

Prisene justeres ved å bruke forholdet mellom `adjusted_close` og `close` på
samme dato for open, high, low og close. Dette gir en konsistent
total-return-prisserie for splits og kontantutbytte. Det modellerer ikke
utbytte som separat kontantstrøm.

Standard datasettsplitt er:

| Datasett | Fra | Til | Bruk |
|---|---|---|---|
| In-sample | 2018-01-01 | 2022-12-31 | Utviklingsdiagnostikk |
| Kalibrering | 2023-01-01 | 2024-12-31 | Én kontroll før frys |
| Historisk test | 2025-01-01 | 2026-07-23 | Diagnose; ikke urørt |
| Fremoverskuende OOS | 2026-07-24 | 2027-07-23 | Reservert, urørt evaluering |

Kodevalideringen avviser tomme, ugyldige eller overlappende intervaller.
Dashboardet krever at brukeren velger ett navngitt datasett før kjøring.
Den historiske testperioden kalles ikke out-of-sample fordi modellutviklingen
kan ha brukt kunnskap fra perioden. Bare data etter frys 23. juli 2026 teller
som den reserverte, fremoverskuende OOS-testen.

### Gjenværende begrensninger

- Dagens watchlist er fortsatt survivorship-biased bakover i tid.
- Valutakostnaden modelleres, men historisk valutaavkastning mellom
  instrumentvaluta og NOK er foreløpig ikke med.
- Point-in-time fundamentaler inngår ikke; dette er med hensikt en teknisk
  referanse og ikke en historisk rekonstruksjon av fullmodellen.
- Walk-forward-resultatene mangler fortsatt risikojusterte nøkkeltall som
  drawdown, Sharpe og Sortino.

## Kronologisk rolling walk-forward

`src/walk_forward.py` erstatter den tidligere periodebaserte implementasjonen.
Den gamle løsningen sammenlignet relative yfinance-vinduer som kunne overlappe.

Den nye kontrollen:

- bruker bare `technical_only_v1`
- holder strategi- og kostnadsreglene faste uten tuning per fold
- bruker tre års train-vindu
- tester på de umiddelbart påfølgende seks månedene
- flytter vinduet seks måneder for hver fold
- krever at train slutter før test starter
- laster aksje- og benchmarkdata én gang per kjøring og gjenbruker dataene
- rapporterer relative resultater per fold og samlet stabilitet

Train-resultatet er diagnostikk. Det brukes ikke til å velge en vinnende
parameterkonfigurasjon. De historiske testfoldene er rolling tester, ikke den
reserverte fremoverskuende OOS-perioden.

Standardperioden 2018-01-01 til 2026-07-23 gir komplette folds frem til siste
hele seksmåneders testvindu. Ufullstendige testvinduer tas ikke med.

## Resultatmetrikker v1

`src/performance_metrics.py` beregner resultatmål fra daglig estimert netto
likvidasjonsverdi. En åpen posisjon verdsettes derfor etter beregnede
salgskostnader, ikke bare siste markedskurs.

Følgende mål rapporteres per ticker:

- total og annualisert avkastning (CAGR)
- maksimal drawdown
- annualisert Sharpe og Sortino med risikofri rente satt til null
- turnover som handlet notional dividert på gjennomsnittlig egenkapital
- antall lukkede handler
- treffprosent basert på netto gevinst etter kjøps- og salgskostnader
- gjennomsnittlig gevinst dividert på gjennomsnittlig absolutt tap
- gjennomsnittlig holdetid for lukkede handler

Sharpe og Sortino vises som manglende når datagrunnlaget eller variasjonen ikke
er tilstrekkelig. Åpne handler inngår ikke i treffprosent, gevinst/tap-forhold
eller gjennomsnittlig holdetid.

### Likt vektet portefølje

Walk-forward bygger også en faktisk porteføljekurve. Hver ticker får én lik
startvekt og sin egen kontantsleeve. Sleeve-verdiene slås sammen daglig uten
rebalansering mellom tickerne i testvinduet. Buy-and-hold-porteføljen bygges med
de samme startvektene og kostnadsantakelsene.

Porteføljeresultatet viser avkastning, relativ avkastning, maksimal drawdown,
Sharpe og Sortino. Dette er mer representativt enn et enkelt gjennomsnitt av
tickeravkastninger, men universet er fortsatt survivorship-biased.

### Regioner

Hver testfold rapporteres separat for:

- USA
- Norge (`.OL`)
- øvrige Norden (`.ST`, `.CO`, `.HE`)

Regionsresultatene er gjennomsnitt av tickerresultater i regionen. De er ikke
egne kapitalvektede regionale porteføljer i v1.

## Fremoverskuende trend-/momentumreferanse

Decision Journal bruker `trend_momentum_v1` for sammenligning på modellens
faktiske kjøpsråd. Referansen krever bare `STERK OPPTREND` og ikke-negativ
20-dagers relativ styrke. Den bruker faste 5/10/20/40-dagershorisonter og står i
kontanter når regelen ikke er oppfylt. Den skal derfor ikke forveksles med den
historiske `technical_only_v1`-testen, som også bruker teknisk totalscore,
markedsregime, stop- og trend-exit.
