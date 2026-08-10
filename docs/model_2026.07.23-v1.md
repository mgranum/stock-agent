# Production model 2026.07.23-v1

## Status

`2026.07.23-v1` is the frozen identity of the production decision model as it
existed on 23 July 2026.

The version identifies decision behavior, not the application release. Change
the model version when a change can alter scores, recommendations, portfolio
actions, ranking, risk priority, stop logic, or the signals included in the
final Recommendation Engine output. Do not change it for presentation,
documentation, logging, tests, or backward-compatible storage changes.

This document describes the implementation; it does not validate that the model
outperforms an index. Model validation and a forward-looking Decision Journal
are the next milestone.

## Purpose and boundaries

The model provides decision support for manual investing over days to weeks.
It does not place orders. Its primary data source is yfinance, supported by
local JSON data and daily caches.

The deterministic rules decide what the system means. News, sentiment,
earnings, analyst data, and chat are supporting or presentation layers and must
not independently create an undocumented buy/sell model.

## Core stock analysis

`src.analysis.analyze_stock()` is the stock-level orchestration path:

1. Load daily prices and calculate indicators.
2. Select a regional benchmark.
3. Calculate technical strength and relative strength.
4. Score current fundamentals.
5. Score up to five years of fundamental history.
6. Combine the scores into the stock recommendation.
7. Calculate target and stop levels.

### Indicators

The model uses SMA20, SMA50, SMA100, SMA200, RSI14, MACD 12/26 with signal 9,
20-day average volume, and ATR14.

Regional benchmarks are:

| Market | Benchmark |
|---|---|
| Norway (`.OL`) | `OSEBX.OL` |
| Sweden (`.ST`) | `^OMX` |
| Denmark (`.CO`) | `^OMXC25` |
| Finland (`.HE`) | `^OMXH25` |
| Other/USA | `SPY` |

### Technical score

The maximum implemented technical contribution is 80 points:

| Condition | Points |
|---|---:|
| Price above SMA20 | 15 |
| SMA20 above SMA50 | 15 |
| Price above SMA50 | 10 |
| RSI 50–70 | 15 |
| RSI above 70 | 8 |
| MACD above signal | 15 |
| Volume above 20-day average | 10 |
| Positive 20-day relative strength versus benchmark | 10 |

All three trend conditions produce `STERK OPPTREND`; two produce
`MODERAT OPPTREND`; zero or one produces `SVAK / NEGATIV TREND`.

### Current fundamentals

`src.fundamentals.score_fundamentals()` scores revenue and earnings growth,
profit and operating margins, return on equity, debt/equity, P/E, forward P/E,
and price/book. The score is clamped to 0–100.

Current fundamental labels are:

| Score | Label |
|---|---|
| 70 or higher | `STERK FUNDAMENTAL KVALITET` |
| 45–69 | `AKSEPTABEL FUNDAMENTAL KVALITET` |
| Below 45 | `SVAK / UKLAR FUNDAMENTAL KVALITET` |

### Fundamental history

`src.fundamental_history.score_fundamental_history()` uses up to five annual
periods of revenue growth, EPS growth, margins, ROE, debt/equity, and free cash
flow. Its result is clamped to 0–100. Missing history yields score 0 rather than
an imputed positive value.

### Combined score and stock recommendation

The combined score is:

```text
technical score
+ 20% of current fundamental score
+ 20% of fundamental history score
```

The result is clamped to 0–100. A buy setup additionally requires:

- combined score at least 70
- technical score at least 50
- all three trend conditions
- positive 20-day relative strength

Recommendations are:

| Rule | Recommendation |
|---|---|
| Score ≥70 and buy setup passes | `KJØP / ØK` |
| Otherwise score ≥45 | `HOLD / OBSERVER` |
| Score below 45 | `UNNGÅ / SELG` |

Strong fundamentals without the technical buy setup do not produce a buy.

### Target and stops

| Output | Rule |
|---|---|
| Course target | Current price × 1.12 |
| Fixed stop-loss | Current price × 0.92 |
| ATR stop | Current price − 3 × ATR14 |
| Trailing stop | SMA50 |
| Trailing stop triggered | Current price below SMA50 |

These are mechanical levels, not statistically validated forecasts.

## Portfolio action model

`src.portfolio._portfolio_action()` is a separate position-management layer.
It combines trend, relative strength, unrealized gain/loss, score, and trailing
stop status. It can produce reduction/sell, profit-protection, hold, or monitor
actions. Capital protection takes priority over supportive analyst or sentiment
signals.

The portfolio action is not the same field as the stock-level recommendation.
Both feed later presentation and prioritization layers.

## Final Recommendation Engine

`src.recommendation_engine.build_recommendations()` is the single orchestrator
for the final daily action list. It collects, prioritizes, merges, and
deduplicates candidates from:

1. Daily Flow actions
2. alerts
3. earnings
4. analyst changes
5. sentiment
6. Watchlist Advisor
7. Opportunity Advisor
8. dashboard key opportunities
9. Portfolio Advisor

It returns a model-versioned summary and ordered actions. The Daily Briefing
and recommendation questions in Agent Chat consume this result.

This is one final orchestrator, but several upstream modules still contain
domain-specific action rules. They are documented below because they can
compete before Recommendation Engine conflict resolution.

## Advice-source inventory

| Layer | Module | Output/role |
|---|---|---|
| Stock model | `scoring.py` | `KJØP / ØK`, `HOLD / OBSERVER`, `UNNGÅ / SELG` |
| Position model | `portfolio.py` | Position-specific hold/reduce/sell/protect action |
| Risk alerts | `alerts.py` | Capital protection, research and earnings alerts |
| Daily orchestration | `daily_flow.py` | Converts alerts and portfolio signals to daily actions |
| Portfolio conflicts | `advisor.py` | Resolves portfolio signals against analyst, sentiment and earnings |
| Watchlist actions | `watchlist_advisor.py` | Buy/review/wait/remove/research actions |
| New opportunities | `opportunity_advisor.py` | Relative assessment of screened candidates |
| Final actions | `recommendation_engine.py` | Priority, conflict merge and deduplication |
| Daily presentation | `daily_briefing.py` | Presents Recommendation Engine actions and changes |
| Chat presentation/routing | `agent.py` | Explains existing context and also exposes specialist screening/comparison paths |

### Known competing paths

- Stock recommendation and portfolio action can legitimately disagree because
  one evaluates the security and the other evaluates an owned position.
- Alerts, Daily Flow, Portfolio Advisor, and Recommendation Engine all perform
  some prioritization or conflict handling.
- Watchlist Advisor and Opportunity Advisor contain their own eligibility
  rules before Recommendation Engine sees their outputs.
- Agent Chat uses Recommendation Engine for general daily recommendation
  questions, but specialist screening, comparison, risk, portfolio, and
  watchlist questions have dedicated routing and formatting paths.

No behavior in these paths was changed when this version was introduced.

## Versioned artifacts

New artifacts carry `model_version`:

- built agent context
- context snapshot metadata
- model snapshot CSV rows
- Recommendation Engine output

Legacy model snapshot CSV files remain readable and are labeled
`legacy-unversioned`. Legacy context snapshots remain readable and report no
model version unless they already contain one.

## Change control

Before changing the model:

1. State the hypothesis.
2. Define evaluation metrics and baselines in advance.
3. Add or update tests.
4. Evaluate out of sample and with rolling walk-forward.
5. Record the decision.
6. Assign a new `MODEL_VERSION` only if decision behavior changes.

The current rules must not be silently tuned while the validation baseline is
being established.
