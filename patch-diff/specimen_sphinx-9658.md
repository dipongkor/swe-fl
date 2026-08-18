# Specimen differential: sphinx-doc__sphinx-9658 (minimax-m3 run3)

Both the gold patch and the agent patch are recorded RESOLVED by the standard
SWE-bench Verified harness (re-confirmed here: resolved_ids = [sphinx-doc__sphinx-9658]
for both). The bug: a class whose base is a mocked import renders as `unknown.secret.`
(empty final component) instead of `unknown.secret.Class`.

- GOLD repairs the fault at its source in `sphinx/ext/autodoc/mock.py`: gives the mock a
  real `__name__`, so `_MockObject.__init__` sets `__qualname__` to it. Every consumer of
  the mock's identity benefits.
- AGENT (minimax-m3 run3) adds a special case to ONE consumer, `_restify_py37` in
  `sphinx/util/typing.py`, returning `__display_name__` when `__sphinx_mock__` is set.

## Differential probe (Python 3.9 test env, `with mock(['unknown']): unknown.secret.Class`)

| probe                         | BASE (buggy)            | GOLD                      | AGENT                     |
|-------------------------------|-------------------------|---------------------------|---------------------------|
| object `__qualname__`         | `''`                    | `'Class'`                 | **`''` (still corrupted)**|
| `restify(C)`                  | `unknown.secret.`       | `unknown.secret.Class`    | `unknown.secret.Class`    |
| `stringify(C)`                | `unknown.secret.Class`  | `unknown.secret.Class`    | `unknown.secret.Class`    |
| `restify(List[C])`            | `...unknown.secret.`    | `...unknown.secret.Class` | `...unknown.secret.Class` |
| `restify(Optional[C])`        | `...unknown.secret.`    | `...unknown.secret.Class` | `...unknown.secret.Class` |

## Verdict (honest)

On the Python 3.9 test environment the agent patch is behaviorally EQUIVALENT to gold for
every *reachable* rendering path (restify, stringify, compound annotations) — so accuracy
cannot distinguish them, exactly as claimed.

The divergence is at the object level: the agent leaves the mock's identity corrupted
(`__qualname__ == ''`) and only masks one renderer's output string, whereas gold repairs
the identity. The residual fault is latent and surfaces:
  (1) for the sibling renderer `_restify_py36` (the Python-3.6 dispatch path this Sphinx
      still ships; not runtime-reachable on 3.9 because it references `typing.TupleMeta`,
      removed in 3.9 — a static-code gap), and
  (2) for any external consumer that reads the mock's `__qualname__`/identity directly.

This is a genuine resolution-vs-localization divergence (symptom-guard at one consumer vs
source repair), demonstrated executably by the residual `__qualname__` corruption. It is
NOT a case of the agent producing user-visible wrong output on the tested interpreter.
