# Reasoning-alignment report

- Instances judged: **94**
- Jury: anthropic:claude-opus-4-8, openai:gpt-5.3-codex, google:gemini-3.6-flash
- Each juror judges every instance twice (2 orderings); the final label is the majority across all juror x ordering verdicts.

## Final alignment distribution

- aligned: **87**
- partial: **7**

## Label legend

- **aligned** — Same causal mechanism; both describe the same faulty behavior producing the same failure (may differ only in wording/detail).
- **partial** — Consistent but uneven; one annotator names a step, condition, or cause the other omits, with no conflict between them.
- **divergent** — Different mechanisms that could both be true at once; two distinct causal stories that don't clash.
- **contradictory** — Incompatible mechanisms that can't both be true; the annotators make opposing claims about what the code does.

## Reliability signals

- Cross-model disagreements: **18** / 94
- Order-swap disagreements: **7** / 94

## Flagged for manual adjudication (19)

Cross-model or order-swap disagreements, divergent/contradictory finals, low-confidence, or failed verdicts.

### astropy__astropy-13579
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 1, 'aligned': 5}, order0=aligned, order1=aligned

### astropy__astropy-7606
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 1, 'aligned': 5}, order0=aligned, order1=aligned

### django__django-11138
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'aligned': 5, 'partial': 1}, order0=aligned, order1=aligned

### django__django-12155
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 2, 'aligned': 4}, order0=aligned, order1=aligned

### django__django-13810
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 2, 'aligned': 4}, order0=aligned, order1=aligned

### django__django-14011
- final: **partial** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'partial': 3, 'aligned': 3}, order0=aligned, order1=partial

### django__django-14053
- final: **aligned** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 4, 'partial': 2}, order0=aligned, order1=partial

### django__django-14170
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'aligned', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 5, 'partial': 1}, order0=aligned, order1=aligned

### django__django-15563
- final: **partial** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'partial': 3, 'aligned': 3}, order0=aligned, order1=partial

### django__django-15572
- final: **partial** (order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'partial', 'openai': 'partial'}
- label counts: {'aligned': 3, 'partial': 3}, order0=partial, order1=aligned

### django__django-16502
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'aligned', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 5, 'partial': 1}, order0=aligned, order1=aligned

### matplotlib__matplotlib-24026
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 1, 'aligned': 5}, order0=aligned, order1=aligned

### matplotlib__matplotlib-25479
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'partial': 2, 'aligned': 4}, order0=aligned, order1=aligned

### pytest-dev__pytest-6197
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'aligned': 5, 'partial': 1}, order0=aligned, order1=aligned

### pytest-dev__pytest-7236
- final: **aligned** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 4, 'partial': 2}, order0=aligned, order1=partial

### scikit-learn__scikit-learn-26194
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'aligned', 'google': 'aligned', 'openai': 'divergent'}
- label counts: {'aligned': 5, 'divergent': 1}, order0=aligned, order1=aligned

### scikit-learn__scikit-learn-9288
- final: **aligned** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 4, 'partial': 2}, order0=aligned, order1=partial

### sphinx-doc__sphinx-9658
- final: **aligned** (cross-model disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'aligned'}
- label counts: {'partial': 2, 'aligned': 4}, order0=aligned, order1=aligned

### sympy__sympy-21379
- final: **aligned** (cross-model disagreement; order-swap disagreement)
- per-model: {'anthropic': 'partial', 'google': 'aligned', 'openai': 'partial'}
- label counts: {'aligned': 4, 'partial': 2}, order0=aligned, order1=partial

