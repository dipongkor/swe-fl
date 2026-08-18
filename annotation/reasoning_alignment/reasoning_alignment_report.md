# Reasoning-alignment report

- Instances: **94**  |  coded (binary): **93**  |  coverage: **98.9%**

- Jury: anthropic:claude-opus-4-8(T=None), openai:gpt-5.3-codex(T=None), google:gemini-3.6-flash(T=0.0)
- Repeats per (juror x ordering): 1
- Rubric hash: `fff5a48925cf`
- Generated: 2026-08-16T12:43:45

PRIMARY code = binary **consistent** (aligned+partial) vs **conflicting**
(divergent+contradictory). The 4-way split is an order-sensitive
diagnostic (see below). Panel label = strict majority over jurors; each
juror = strict majority over its orderings x repeats; ties ABSTAIN.

## Primary: consistent vs conflicting

- consistent: **91** (96.8%)
- conflicting: **2** (2.1%)
- _abstained_: **1**

- Model-model Krippendorff's alpha (binary): **0.173** — below Krippendorff's floor (< 0.667)
- consistent = aligned+partial; conflicting = divergent+contradictory.

## Diagnostic: 4-way split (ORDER-SENSITIVE, do not report alone)

coded (4-way): **82** (87.2%)   Krippendorff alpha (4-way): **0.596** — below Krippendorff's floor (< 0.667)

- aligned: **38** (40.4%)
- partial: **42** (44.7%)
- divergent: **2** (2.1%)

The aligned<->partial boundary is directional and position-sensitive;
its flips do not change the binary code and are excluded from the
primary result.

### Label legend

- **aligned** — Mutually recoverable mechanisms; neither adds causal content the other lacks (may differ in wording or detail).
- **partial** — One-way subsumption; one annotator's mechanism strictly elaborates the other's, with no conflict between them.
- **divergent** — Incomparable mechanisms; each has causal content the other lacks, but both could hold at once.
- **contradictory** — Incompatible mechanisms that cannot both be true; the annotators make opposing claims about what the code does.

## Per juror

| juror | coverage | order-flip (binary) | order-flip (4-way) | self-consistency |
|---|---|---|---|---|
| anthropic:claude-opus-4-8 | 92.6% | 7.4% | 27.7% | n/a (repeats=1) |
| google:gemini-3.6-flash | 98.9% | 1.1% | 27.7% | n/a (repeats=1) |
| openai:gpt-5.3-codex | 98.9% | 1.1% | 31.9% | n/a (repeats=1) |

### Pairwise juror agreement (4-way)

| pair | n | raw | alpha |
|---|---|---|---|
| anthropic:claude-opus-4-8 vs google:gemini-3.6-flash | 51 | 80.4% | 0.650 |
| anthropic:claude-opus-4-8 vs openai:gpt-5.3-codex | 47 | 74.5% | 0.519 |
| google:gemini-3.6-flash vs openai:gpt-5.3-codex | 47 | 83.0% | 0.682 |

High pairwise agreement across families is necessary but not
sufficient: it can reflect shared bias rather than validity. Run
judge_validation.py against the human gold codes [Ahmed2025].

## Flagged for manual adjudication (16)

Binary panel abstentions, binary cross-model/order-swap disagreement,
or failed calls. (4-way-only disagreements are noted, not flagged.)

### astropy__astropy-7606
- binary: **consistent** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=None per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': None}  4-way abstained; 4-way cross-model; indeterminate (aligned/partial)
- counts: {'divergent': 2, 'partial': 3, 'aligned': 1}  entropy=0.73

### django__django-12406
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=aligned per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': None, 'google:gemini-3.6-flash': 'aligned'}  4-way order-swap flip; indeterminate (aligned/partial)
- counts: {'divergent': 1, 'aligned': 3, 'partial': 2}  entropy=0.73

### pytest-dev__pytest-6197
- binary: **consistent** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=None per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': None}  4-way abstained; 4-way cross-model
- counts: {'divergent': 2, 'partial': 3, 'aligned': 1}  entropy=0.73

### scikit-learn__scikit-learn-13124
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=None per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': None, 'google:gemini-3.6-flash': None}  4-way abstained; 4-way order-swap flip; indeterminate (aligned/partial)
- counts: {'partial': 3, 'aligned': 2, 'divergent': 1}  entropy=0.73

### sphinx-doc__sphinx-9658
- binary: **consistent** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=None per juror={'anthropic:claude-opus-4-8': 'contradictory', 'openai:gpt-5.3-codex': None, 'google:gemini-3.6-flash': 'aligned'}  4-way abstained; 4-way cross-model
- counts: {'contradictory': 2, 'partial': 1, 'aligned': 3}  entropy=0.73

### django__django-14170
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': None}  indeterminate (aligned/partial)
- counts: {'divergent': 1, 'partial': 4, 'aligned': 1}  entropy=0.63

### pylint-dev__pylint-6528
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': None}  
- counts: {'partial': 4, 'aligned': 1, 'divergent': 1}  entropy=0.63

### django__django-16938
- binary: **None** (no panel majority on consistent/conflicting (abstained); cross-model disagreement (binary); order-swap disagreement (binary); 1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': None}
- 4-way: final=None per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': None}  4-way abstained; 4-way order-swap flip; 4-way cross-model
- counts: {'divergent': 3, 'partial': 3}  entropy=0.50

### astropy__astropy-13579
- binary: **consistent** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'consistent', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'conflicting'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': 'partial', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'divergent'}  4-way cross-model; indeterminate (partial/divergent)
- counts: {'partial': 4, 'divergent': 2}  entropy=0.46

### django__django-12155
- binary: **consistent** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'partial'}  4-way cross-model
- counts: {'divergent': 2, 'partial': 4}  entropy=0.46

### matplotlib__matplotlib-23299
- binary: **conflicting** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'conflicting'}
- 4-way: final=divergent per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'divergent'}  4-way cross-model; indeterminate (partial/divergent)
- counts: {'divergent': 4, 'partial': 2}  entropy=0.46

### matplotlib__matplotlib-24026
- binary: **conflicting** (cross-model disagreement (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'conflicting', 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'conflicting'}
- 4-way: final=divergent per juror={'anthropic:claude-opus-4-8': 'divergent', 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'divergent'}  4-way cross-model; indeterminate (partial/divergent)
- counts: {'divergent': 4, 'partial': 2}  entropy=0.46

### django__django-13810
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'partial'}  
- counts: {'divergent': 1, 'partial': 5}  entropy=0.33

### matplotlib__matplotlib-25287
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'partial'}  indeterminate (aligned/partial)
- counts: {'divergent': 1, 'partial': 5}  entropy=0.33

### pydata__xarray-6599
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'consistent', 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=partial per juror={'anthropic:claude-opus-4-8': None, 'openai:gpt-5.3-codex': 'partial', 'google:gemini-3.6-flash': 'partial'}  
- counts: {'divergent': 1, 'partial': 5}  entropy=0.33

### scikit-learn__scikit-learn-26194
- binary: **consistent** (1 juror(s) abstained (binary))
- per juror (binary): {'anthropic:claude-opus-4-8': 'consistent', 'openai:gpt-5.3-codex': None, 'google:gemini-3.6-flash': 'consistent'}
- 4-way: final=aligned per juror={'anthropic:claude-opus-4-8': 'aligned', 'openai:gpt-5.3-codex': None, 'google:gemini-3.6-flash': 'aligned'}  
- counts: {'aligned': 5, 'contradictory': 1}  entropy=0.33

