# Trustworthiness leaderboard

Ranked by **full-trust rate** (correct localization AND resolved AND consistent reasoning). Condition: `base`. Verdict per instance = majority@3 over 3 runs; every rate is over all 130 benchmark instances (non-attempts count as failures).

| # | Model | Attempted | FL | APR | Reasoning | **Full trust** (95% CI) | Fix-without-loc | Robustness |
|---|---|---|---|---|---|---|---|---|
| 1 | claude-opus | 100.0 | 72.3 | 70.0 | 84.6 | **51.5 [43.0, 60.0]** | 24.2 | _pending_ |
| 2 | minimax-m3 | 89.2 | 53.1 | 51.5 | 76.2 | **33.1 [25.6, 41.5]** | 32.8 | _pending_ |
| 3 | gpt-5-3-codex | 89.2 | 48.5 | 30.8 | 76.9 | **20.8 [14.7, 28.5]** | 32.5 | _pending_ |
| 4 | gemini-3.1-flash-lite | 58.5 | 23.1 | 22.3 | 51.5 | **10.0 [5.9, 16.4]** | 51.7 | _pending_ |

_All values are percentages._

**Legend**
- **Attempted** — instances the model produced a localization or patch for in ≥2 runs (engagement, not correctness).
- **FL** — correct fault line in ≥2 runs.
- **APR** — resolved patch in ≥2 runs.
- **Reasoning** — reasoning consistent with the human mechanism in ≥2 runs.
- **Full trust** — FL ∧ APR ∧ Reasoning on the same instance (Wilson 95% CI). The ranking metric.
- **Fix-without-loc** — of resolved instances, the fraction that localized the WRONG line (lower is better; a trust red flag).
- **Robustness** — retention (1 − mean break-rate) under semantics-preserving transforms; pending until transformed runs exist.
