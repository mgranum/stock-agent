# Daily Refresh – launchd på macOS

Automatisk lokal kjøring av Daily Refresh én gang per dag på MacBook Air.

Daily Refresh bruker state/lock i `cache/` for å sikre maks én vellykket kjøring per dag og trygg catch-up ved innlogging (`RunAtLoad`).

## Forutsetninger

- Prosjektet er klonet lokalt
- `uv` er installert og tilgjengelig via `PATH` (typisk `~/.local/bin` eller Homebrew)
- Daily Refresh v2 er på plass (`uv run python -m src.daily_refresh`)

## Filer

| Fil | Formål |
|-----|--------|
| `scripts/run_daily_refresh.sh` | Wrapper som setter miljø og logger |
| `scripts/com.stock-agent.daily-refresh.plist` | launchd-mal (krever `__PROJECT_ROOT__`) |
| `logs/daily_refresh.log` | Hovedlogg fra refresh-kjøring |
| `logs/launchd.stdout.log` | launchd stdout |
| `logs/launchd.stderr.log` | launchd stderr |

Wrapper-scriptet finner prosjektroot automatisk. Plist-filen må ha absolutte stier og må tilpasses din maskin før install.

## Installere

Kjør fra prosjektroot. Erstatt `__PROJECT_ROOT__` med faktisk sti (ingen hardkodet brukernavn i repo-filene):

```bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Hvis du står i prosjektroot:
PROJECT_ROOT="$(pwd)"

sed "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  scripts/com.stock-agent.daily-refresh.plist \
  > ~/Library/LaunchAgents/com.stock-agent.daily-refresh.plist

chmod +x scripts/run_daily_refresh.sh

launchctl load ~/Library/LaunchAgents/com.stock-agent.daily-refresh.plist
```

Hvis prosjektet ligger et annet sted enn da du klonet det, generer plist på nytt med riktig `PROJECT_ROOT`.

## Avinstallere

```bash
launchctl unload ~/Library/LaunchAgents/com.stock-agent.daily-refresh.plist
rm ~/Library/LaunchAgents/com.stock-agent.daily-refresh.plist
```

Repo-filer (`scripts/`, `docs/`) slettes ikke av dette.

## Teste manuelt

Start jobben med launchd (uten å vente til kl. 06:00):

```bash
launchctl start com.stock-agent.daily-refresh
```

Test wrapper direkte:

```bash
./scripts/run_daily_refresh.sh
```

Dry-run uten datahenting:

```bash
uv run python -m src.daily_refresh --dry-run
```

Tving ny kjøring samme dag:

```bash
uv run python -m src.daily_refresh --force
```

## Se logger

```bash
tail -f logs/daily_refresh.log
```

launchd-spesifikke logger:

```bash
tail -f logs/launchd.stdout.log logs/launchd.stderr.log
```

State etter kjøring:

```bash
cat cache/daily_refresh_state.json
```

## Oppførsel

| Tidspunkt | Hva skjer |
|-----------|-----------|
| Kl. 06:00 | launchd starter wrapper → `uv run python -m src.daily_refresh` |
| Ved innlogging | `RunAtLoad` starter jobben; app-laget hopper over hvis dagens refresh allerede er fullført |
| Maskin av kl. 06:00 | Catch-up ved neste innlogging (hvis ikke allerede kjørt i dag) |
| Refresh pågår | Lock-fil hindrer dobbeltkjøring |

`STOCK_AGENT_ENV=prod` settes i wrapper-scriptet.

## Feilsøking

**Jobben kjører ikke**

- Sjekk at plist er lastet: `launchctl list | grep stock-agent`
- Sjekk `logs/launchd.stderr.log`
- Verifiser at stier i plist matcher faktisk prosjektmappe

**`uv: command not found`**

- Installer uv eller legg til i PATH i `scripts/run_daily_refresh.sh`
- Test: `which uv` i samme shell-miljø

**Refresh hoppes over**

- Forventet hvis `cache/daily_refresh_state.json` viser `success` i dag
- Bruk `--force` for manuell re-kjøring
