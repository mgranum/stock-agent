# AGENTS.md

## Stock Agent – Development Instructions

This repository contains a local AI-powered stock analysis agent.

The goal is decision support for manual investing, not automated trading.

Primary focus:

* USA
* Norway (OBX)
* Sweden
* Denmark
* Finland

Time horizon:

* Days to weeks
* Not intraday trading

---

## Core Principles

### Small changes over large refactors

Prefer incremental improvements.

Avoid rewriting working systems.

Extend existing functionality before creating new systems.

If a change requires a large refactor, stop and explain why.

---

### One source of truth

Avoid duplicating logic.

Prefer reusing existing functions and data structures.

Particularly avoid duplicate logic across:

* alerts.py
* daily_flow.py
* dashboard.py
* agent.py

If similar logic already exists, extend it instead of creating a parallel implementation.

---

### Preserve existing trading logic

Do not modify:

* scoring rules
* recommendation logic
* portfolio action logic
* trend logic
* stop-loss logic

unless explicitly requested.

When changing behavior, explain exactly what changed.

---

### Preserve existing architecture

Current architecture:

Data
→ Analysis
→ Dashboard
→ Alerts
→ Daily Flow
→ Agent Chat

New features should integrate into existing flows whenever possible.

Avoid introducing independent feature pipelines.

---

## Data Sources

Primary source:

* yfinance

Secondary sources require approval before becoming core dependencies.

Do not introduce:

* cloud backends
* hosted databases
* external APIs requiring ongoing costs

without explicit approval.

---

## Portfolio Rules

The application is a portfolio analysis tool.

It is not:

* a broker
* an execution engine
* an automated trading system

Do not add:

* auto-trading
* automatic order placement
* broker integrations

without explicit approval.

---

## Configuration Rules

Do not hardcode:

* portfolio positions
* watchlists
* tickers
* thresholds intended to be configurable

Use:

* data/
* JSON configuration files
* existing configuration patterns

when appropriate.

---

## Environment Separation

Preserve TEST/PROD separation.

Use:

STOCK_AGENT_ENV

where applicable.

Never bypass environment-specific behavior.

---

## Testing Requirements

All new functionality should include tests when practical.

Minimum expectations:

* happy path
* empty data
* invalid data
* edge cases

Run before reporting completion:

uv run pytest -q

Include test results in completion reports.

---

## Dashboard & UX Rules

The application is used daily.

Optimize for:

* clarity
* signal over noise
* investor actions

Avoid:

* clutter
* duplicate information
* overly technical displays

Prefer:

* concise tables
* actionable alerts
* prioritized information

When adding a new dashboard section, ask:

"Does this help the investor decide what to do today?"

If not, reconsider.

---

## Alerts Rules

Alerts should be:

* actionable
* prioritized
* deduplicated

Avoid creating multiple alerts that represent the same underlying action.

Priority order:

1. Capital protection
2. Risk reduction
3. Portfolio management
4. New opportunities
5. Administrative tasks

---

## Daily Flow Rules

Daily Flow exists to answer:

1. What should I do today?
2. What should I watch?
3. What opportunities exist?
4. What risks require action?

Daily Flow should prioritize actions over status reporting.

Avoid creating duplicate information already visible elsewhere unless it improves prioritization.

---

## News & Earnings Rules

News and earnings are supporting signals.

They should enhance investment decisions, not overwhelm them.

Prefer:

* relevance
* quality
* recency

over volume.

A smaller number of high-quality items is preferred to a large number of low-quality items.

---

## Sentiment Rules

Sentiment is a supporting signal only.

Never allow sentiment alone to drive:

* recommendations
* portfolio actions
* buy/sell decisions

Sentiment should complement:

* technical analysis
* fundamentals
* earnings
* news

---

## Coding Style

Prefer:

* clear function names
* small functions
* explicit data structures
* predictable behavior

Keep existing function names unless there is a strong reason to change them.

Avoid clever solutions that reduce maintainability.

Readability is more important than brevity.

---

## Completion Reports

When reporting completed work:

Include:

1. What was implemented
2. Files changed
3. Tests added
4. Test results
5. Any limitations or follow-up work

Keep reports concise.

---

## Default Cursor Behavior

Before making changes:

1. Read AGENTS.md
2. Understand existing implementation
3. Reuse existing systems where possible
4. Make the smallest reasonable change
5. Add tests
6. Run pytest
7. Report results

If unsure:

Stop and ask rather than guessing.
