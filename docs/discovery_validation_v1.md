# Discovery Validation v1

Målet er å avgjøre om discovery-verktøyet tilfører målbar verdi mot passiv
global investering. Modellen fryses mens datagrunnlaget bygges.

## Hvorfor testen er fremoverskuende

Det brede, daterte screening-universet finnes først fra 24. juli 2026, og
historiske fundamentaler er ikke lagret slik de var kjent på hver signaldato.
En rekonstruert historisk discovery-backtest ville derfor ha både survivorship-
og look-ahead-risiko. Den brukes ikke som beslutningsgrunnlag.

## Frosset testoppsett

- De tre kandidatene som faktisk vises under «Nye kandidater» lagres daglig.
- En ny kjøring samme dag erstatter dagens journalfil og lager ikke duplikater.
- Signalet observeres etter sluttkurs; hypotetisk kjøp skjer på neste
  tilgjengelige børsåpning.
- Kandidatene vektes likt innen hver signaldagskohort.
- Eksisterende konfigurerbare kurtasje-, spread- og valutakostnader brukes.
- Resultatet måles etter 5, 10, 20 og 40 handelsdager.
- Primær global referanse er `ACWI`, en investerbar ETF som følger globale
  utviklede og fremvoksende aksjemarkeder.
- Hver kandidat sammenlignes også med samme lokale markedsreferanse som brukes
  av produksjonsmodellen.
- Watchlist er ikke utgangspunkt for kandidatene.

`ACWI` er en markedsproxy, ikke en eksakt replika av DNB Global Indeks A eller
Nordnet One Offensiv. Direkte fonds-NAV kan legges til senere dersom det finnes
en stabil og tidspunktkorrekt kilde, men det skal ikke forsinke OOS-målingen.

## Beslutningsport

Det trekkes ingen konklusjon før minst 60 signaldagskohorter har fullført
40-handelsdagershorisonten. For å fortsette aktiv modellutvikling må
discovery-porteføljen etter kostnader:

1. ha positiv gjennomsnittlig differanse mot `ACWI` på 10, 20 og 40
   handelsdager;
2. slå `ACWI` i mer enn halvparten av signaldagskohortene på 20 og 40
   handelsdager; og
3. ikke være avhengig av én region eller et fåtall ekstreme vinnere.

Hvis disse kravene ikke nås, skal modellen forenkles eller aktiv aksjeplukking
stoppes før nye features utvikles.
