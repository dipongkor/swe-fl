#!/usr/bin/env python3
"""Trustworthiness leaderboard: rank models by joint FL x APR x reasoning trust.

The benchmark's thesis is that single-axis competence OVERSTATES trust, so the
leaderboard leads with the one metric that requires all axes at once -
*full trust* (correct localization AND resolved patch AND consistent reasoning) -
while still showing every axis separately.

Scoring decisions (locked):
  * rank key           = full-trust rate
  * denominator        = ALL benchmark instances (a model that never localizes an
                         instance fails FL/APR/reasoning on it; no free pass)
  * per-instance verdict = majority@3 over the model's 3 runs (>=2 of 3 True;
                         a missing run counts False)
  * a Wilson 95% CI on the full-trust rate separates close ranks honestly.

Input is trust-cells[-tag].csv from trust_axes.py (per model,run,instance:
fl_line_hit, resolved, reasoning_consistent).  The canonical instance set is the
ground-truth-fl/ directory, so absence is scored, not skipped.

Robustness is a live placeholder: pass --robustness robustness-diff.csv once the
transformed runs exist and the column fills with retention = 1 - mean break-rate;
until then it reads "N/A" and the schema is unchanged.

Usage:
    python leaderboard.py                       # base condition, 3 axes
    python leaderboard.py --robustness robustness-diff.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

import fl_eval as FE

REPO = os.path.dirname(os.path.abspath(__file__))
RUNS_EXPECTED = 3   # majority@3 denominator


def as_bool(s):
    return True if s in ("True", "true", "1") else False if s in ("False", "false", "0") else None


def wilson(k, n, z=1.96):
    """Wilson score 95% CI for a binomial proportion k/n."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, centre - half), min(1.0, centre + half))


RULES = ["any", "majority", "all"]           # any@3, majority@3, all@3
RULE_LABEL = {"any": "any@3", "majority": "majority@3", "all": "all@3"}


def reduce_rule(vals, rule, denom=RUNS_EXPECTED):
    """Collapse a cell's per-run booleans by the reliability rule (missing=False).

    any@3      = True in >=1 run
    majority@3 = True in >=2 of 3 runs
    all@3      = True in all 3 runs
    """
    t = sum(1 for v in vals if v)
    if rule == "any":
        return t >= 1
    if rule == "all":
        return t >= denom
    return t * 2 > denom                       # majority


def load_trust_cells(path):
    """-> {(model, instance): {axis: [bool over runs]}} and the model set."""
    per = defaultdict(lambda: {"fl": [], "apr": [], "cons": [], "loc": []})
    models = set()
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            m, inst = r["model"], r["instance"]
            models.add(m)
            fl = as_bool(r.get("fl_line_hit"))
            apr = as_bool(r.get("resolved"))
            cons = as_bool(r.get("reasoning_consistent"))
            per[(m, inst)]["fl"].append(fl is True)
            per[(m, inst)]["apr"].append(apr is True)
            per[(m, inst)]["cons"].append(cons is True)
            # "attempted" = the cell exists this run, i.e. the model produced a
            # localization or a patch for this instance (trust-cells is the union
            # of the FL/APR and reasoning sources). A cleaner "localized-only"
            # signal is not recoverable from the join: fl_line_hit=False mixes
            # wrong-line with no-localization (apr-only), so we report the honest
            # engagement measure and keep FL itself as the real localization axis.
            per[(m, inst)]["loc"].append(True)
    return per, sorted(models)


def load_robustness(path):
    """-> {model: retention} where retention = 1 - mean OVERALL break-rate."""
    if not path or not os.path.exists(path):
        return {}
    breaks = defaultdict(list)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            # per-model rows, full_trust axis, one per transform
            if r.get("scope") in ("OVERALL", "") or r.get("axis") != "full_trust":
                continue
            try:
                breaks[r["scope"]].append(float(r["break_rate"]))
            except (ValueError, KeyError):
                continue
    return {m: 1 - sum(v) / len(v) for m, v in breaks.items() if v}


def score(per, models, instances, robustness, rule="majority"):
    """Reduce to per-model rates over ALL instances under the reliability rule."""
    rows = []
    for m in models:
        loc = fl = apr = cons = full = 0
        resolved_fl_wrong = 0
        for inst in instances:
            cell = per.get((m, inst))
            if cell:
                is_loc = reduce_rule(cell["loc"], rule)
                is_fl = reduce_rule(cell["fl"], rule)
                is_apr = reduce_rule(cell["apr"], rule)
                is_cons = reduce_rule(cell["cons"], rule)
            else:
                is_loc = is_fl = is_apr = is_cons = False
            loc += is_loc
            fl += is_fl
            apr += is_apr
            cons += is_cons
            if is_fl and is_apr and is_cons:
                full += 1
            if is_apr and not is_fl:
                resolved_fl_wrong += 1
        n = len(instances)
        p, lo, hi = wilson(full, n)
        rows.append({
            "model": m, "n": n,
            "coverage": loc / n, "fl": fl / n, "apr": apr / n,
            "reasoning": cons / n, "full_trust": p,
            "full_trust_lo": lo, "full_trust_hi": hi,
            "fix_without_loc": (resolved_fl_wrong / apr) if apr else 0.0,
            "resolved_n": apr,
            "robustness": robustness.get(m),
        })
    rows.sort(key=lambda r: r["full_trust"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def write_csv(rows_by_rule, path):
    cols = ["reliability", "rank", "model", "n", "attempted", "fl", "apr",
            "reasoning", "full_trust", "full_trust_lo", "full_trust_hi",
            "fix_without_loc", "resolved_n", "robustness"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for rule in RULES:
            for r in rows_by_rule[rule]:
                w.writerow([RULE_LABEL[rule], r["rank"], r["model"], r["n"],
                            f"{r['coverage']:.3f}", f"{r['fl']:.3f}", f"{r['apr']:.3f}",
                            f"{r['reasoning']:.3f}", f"{r['full_trust']:.3f}",
                            f"{r['full_trust_lo']:.3f}", f"{r['full_trust_hi']:.3f}",
                            f"{r['fix_without_loc']:.3f}", r["resolved_n"],
                            "" if r["robustness"] is None else f"{r['robustness']:.3f}"])


def write_md(rows, path, condition):
    def pct(x):
        return f"{x * 100:.1f}"
    lines = ["# Trustworthiness leaderboard", ""]
    lines.append(f"Ranked by **full-trust rate** (correct localization AND resolved "
                 f"AND consistent reasoning). Condition: `{condition}`. "
                 f"Verdict per instance = majority@{RUNS_EXPECTED} over 3 runs; "
                 f"every rate is over all {rows[0]['n']} benchmark instances "
                 "(non-attempts count as failures).")
    lines.append("")
    hdr = ("| # | Model | Attempted | FL | APR | Reasoning | **Full trust** "
           "(95% CI) | Fix-without-loc | Robustness |")
    sep = "|---|---|---|---|---|---|---|---|---|"
    lines += [hdr, sep]
    for r in rows:
        rob = "_pending_" if r["robustness"] is None else pct(r["robustness"])
        ci = f"{pct(r['full_trust'])} [{pct(r['full_trust_lo'])}, {pct(r['full_trust_hi'])}]"
        lines.append(f"| {r['rank']} | {r['model']} | {pct(r['coverage'])} | "
                     f"{pct(r['fl'])} | {pct(r['apr'])} | {pct(r['reasoning'])} | "
                     f"**{ci}** | {pct(r['fix_without_loc'])} | {rob} |")
    lines += ["", "_All values are percentages._", "",
              "**Legend**",
              "- **Attempted** — instances the model produced a localization or "
              "patch for in ≥2 runs (engagement, not correctness).",
              "- **FL** — correct fault line in ≥2 runs.",
              "- **APR** — resolved patch in ≥2 runs.",
              "- **Reasoning** — reasoning consistent with the human mechanism in ≥2 runs.",
              "- **Full trust** — FL ∧ APR ∧ Reasoning on the same instance "
              "(Wilson 95% CI). The ranking metric.",
              "- **Fix-without-loc** — of resolved instances, the fraction that "
              "localized the WRONG line (lower is better; a trust red flag).",
              "- **Robustness** — retention (1 − mean break-rate) under "
              "semantics-preserving transforms; pending until transformed runs exist.",
              ""]
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SWE-FL Trust Leaderboard</title>
<style>
  :root {
    --ground:#F5F8F9; --panel:#FFFFFF; --ink:#0F1720; --muted:#586773;
    --faint:#8A97A2; --hairline:#E2E8EC; --track:#E9EEF1;
    --accent:#0E7C7B; --accent-ink:#0A5C5B; --accent-soft:rgba(14,124,123,.13);
    --sev-low:#3F7D62; --sev-mid:#B45309; --sev-high:#B4272C;
    --row-hover:rgba(14,124,123,.05);
    --font-sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;
    --font-mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark){
    :root{
      --ground:#0A0E13; --panel:#111922; --ink:#E7EEF3; --muted:#93A2AE;
      --faint:#5F6B76; --hairline:#1E2831; --track:#1A232C;
      --accent:#2DD4BF; --accent-ink:#7EE7DA; --accent-soft:rgba(45,212,191,.15);
      --sev-low:#5FBF93; --sev-mid:#E0973B; --sev-high:#F0716F;
      --row-hover:rgba(45,212,191,.06);
    }
  }
  :root[data-theme="light"]{
    --ground:#F5F8F9; --panel:#FFFFFF; --ink:#0F1720; --muted:#586773;
    --faint:#8A97A2; --hairline:#E2E8EC; --track:#E9EEF1;
    --accent:#0E7C7B; --accent-ink:#0A5C5B; --accent-soft:rgba(14,124,123,.13);
    --sev-low:#3F7D62; --sev-mid:#B45309; --sev-high:#B4272C;
    --row-hover:rgba(14,124,123,.05);
  }
  :root[data-theme="dark"]{
    --ground:#0A0E13; --panel:#111922; --ink:#E7EEF3; --muted:#93A2AE;
    --faint:#5F6B76; --hairline:#1E2831; --track:#1A232C;
    --accent:#2DD4BF; --accent-ink:#7EE7DA; --accent-soft:rgba(45,212,191,.15);
    --sev-low:#5FBF93; --sev-mid:#E0973B; --sev-high:#F0716F;
    --row-hover:rgba(45,212,191,.06);
  }

  *{box-sizing:border-box}
  body{
    margin:0; background:var(--ground); color:var(--ink);
    font-family:var(--font-sans); line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1060px; margin:0 auto; padding:clamp(1.5rem,4vw,3.5rem) clamp(1rem,4vw,2rem) 4rem}

  .eyebrow{
    font-family:var(--font-mono); font-size:.72rem; letter-spacing:.18em;
    text-transform:uppercase; color:var(--accent-ink); margin:0 0 .8rem;
    display:flex; align-items:center; gap:.6rem;
  }
  .eyebrow::before{content:""; width:26px; height:2px; background:var(--accent)}
  h1{
    font-size:clamp(2rem,5.5vw,3.1rem); line-height:1.02; margin:0 0 .7rem;
    font-weight:680; letter-spacing:-.025em; text-wrap:balance;
  }
  .lede{max-width:60ch; color:var(--muted); font-size:1.02rem; margin:0}
  .meta{
    font-family:var(--font-mono); font-size:.78rem; color:var(--faint);
    margin:1.1rem 0 0; display:flex; flex-wrap:wrap; gap:.4rem 1.1rem;
  }
  .meta b{color:var(--muted); font-weight:600}

  .board{
    margin-top:2.2rem; background:var(--panel);
    border:1px solid var(--hairline); border-radius:14px;
    overflow:hidden;
  }
  .toolbar{
    display:flex; align-items:center; gap:.7rem; flex-wrap:wrap;
    padding:.9rem 1.1rem; border-bottom:1px solid var(--hairline);
  }
  .toolbar .rulesel{
    font-family:var(--font-mono); font-size:.68rem; letter-spacing:.08em;
    text-transform:uppercase; color:var(--muted); font-weight:600;
  }
  .toolbar select{
    font-family:var(--font-mono); font-size:.85rem; color:var(--ink);
    background:var(--ground); border:1px solid var(--hairline);
    border-radius:8px; padding:.4em .7em; cursor:pointer; appearance:none;
    background-image:linear-gradient(45deg,transparent 50%,var(--accent) 50%),
      linear-gradient(135deg,var(--accent) 50%,transparent 50%);
    background-position:calc(100% - 16px) center,calc(100% - 11px) center;
    background-size:5px 5px,5px 5px; background-repeat:no-repeat;
    padding-right:2.2em;
  }
  .toolbar select:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
  .toolbar-note{font-size:.8rem; color:var(--faint); margin-left:auto}
  @media (max-width:640px){.toolbar-note{display:none}}
  .scroll{overflow-x:auto}
  table{border-collapse:collapse; width:100%; min-width:840px}
  thead th{
    font-family:var(--font-mono); font-size:.68rem; letter-spacing:.06em;
    text-transform:uppercase; color:var(--muted); font-weight:600;
    text-align:right; padding:1rem .85rem .8rem; white-space:nowrap;
    border-bottom:1px solid var(--hairline); cursor:pointer;
    user-select:none; position:relative;
  }
  thead th.lft{text-align:left}
  thead th:hover{color:var(--ink)}
  thead th .arrow{opacity:0; margin-left:.35em; font-size:.85em; color:var(--accent-ink)}
  thead th.sorted .arrow{opacity:1}
  thead th.trust{color:var(--accent-ink)}
  tbody td{
    padding:.95rem .85rem; text-align:right; border-bottom:1px solid var(--hairline);
    font-family:var(--font-mono); font-variant-numeric:tabular-nums;
    font-size:.92rem; vertical-align:middle;
  }
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover{background:var(--row-hover)}

  .rank{color:var(--faint); font-size:.9rem; text-align:center; width:44px}
  .rank .dot{
    display:inline-flex; align-items:center; justify-content:center;
    width:1.7em; height:1.7em; border-radius:50%;
  }
  tr.top .rank .dot{background:var(--accent); color:#fff; font-weight:700}
  :root[data-theme="dark"] tr.top .rank .dot{color:#08110F}
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]) tr.top .rank .dot{color:#08110F}}

  td.model{text-align:left; white-space:nowrap}
  td.model .name{font-size:.98rem; color:var(--ink); font-weight:600}

  .gauge{display:flex; align-items:center; gap:.6rem; justify-content:flex-end}
  .gauge .val{min-width:3.1ch; text-align:right; color:var(--ink)}
  .gauge .bar{
    width:74px; height:6px; border-radius:3px; background:var(--track);
    overflow:hidden; flex:none;
  }
  .gauge .bar i{display:block; height:100%; background:var(--accent); opacity:.55; border-radius:3px}

  td.trust{background:var(--accent-soft)}
  .trustcell{display:flex; align-items:center; gap:.7rem; justify-content:flex-end}
  .trustcell .val{font-size:1.06rem; font-weight:700; color:var(--accent-ink); min-width:3.6ch; text-align:right}
  .whisker{position:relative; width:96px; height:14px; flex:none}
  .whisker .axis{position:absolute; top:50%; left:0; right:0; height:6px; transform:translateY(-50%); background:var(--track); border-radius:3px}
  .whisker .ci{position:absolute; top:50%; height:6px; transform:translateY(-50%); background:var(--accent); opacity:.32; border-radius:3px}
  .whisker .pt{position:absolute; top:50%; width:2px; height:14px; transform:translate(-50%,-50%); background:var(--accent)}

  .chip{
    display:inline-block; font-family:var(--font-mono); font-size:.82rem;
    font-weight:600; padding:.2em .6em; border-radius:6px; min-width:3.4ch;
  }
  .chip.low{color:var(--sev-low); background:color-mix(in srgb,var(--sev-low) 14%,transparent)}
  .chip.mid{color:var(--sev-mid); background:color-mix(in srgb,var(--sev-mid) 15%,transparent)}
  .chip.high{color:var(--sev-high); background:color-mix(in srgb,var(--sev-high) 15%,transparent)}
  .chip.pending{
    color:var(--faint); background:transparent;
    border:1px dashed var(--hairline); font-weight:500; letter-spacing:.02em;
  }

  .foot{margin-top:2rem; display:grid; gap:1.4rem; grid-template-columns:1fr 1fr}
  @media (max-width:640px){.foot{grid-template-columns:1fr}}
  .foot h2{
    font-family:var(--font-mono); font-size:.7rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--accent-ink); margin:0 0 .7rem; font-weight:600;
  }
  .foot dl{margin:0; display:grid; gap:.6rem}
  .foot dt{font-weight:640; font-size:.9rem}
  .foot dd{margin:.05rem 0 0; color:var(--muted); font-size:.88rem; max-width:52ch}
  .foot .thesis{color:var(--muted); font-size:.92rem; max-width:56ch}
  .foot .thesis b{color:var(--ink); font-weight:640}

  .credit{margin-top:2.4rem; font-family:var(--font-mono); font-size:.72rem; color:var(--faint); border-top:1px solid var(--hairline); padding-top:1rem}

  @media (prefers-reduced-motion:no-preference){
    .gauge .bar i, .whisker .ci{transition:width .6s cubic-bezier(.2,.7,.2,1)}
  }
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">SWE-FL &middot; Trustworthiness Benchmark</p>
  <h1>Trust Leaderboard</h1>
  <p class="lede">Models ranked not by whether they fix bugs, but by whether their
    fixes can be <em>trusted</em> &mdash; correct localization, a resolved patch, and reasoning
    that matches the human mechanism, all on the same instance.</p>
  <div class="meta">
    <span><b>__COND__</b> condition</span>
    <span><b>__N__</b> instances &times; 3 runs</span>
    <span>reduce &rarr; <b id="ruleLabel">majority@3</b></span>
    <span>rates over <b>all __N__</b> &middot; non-attempts count as failures</span>
    <span>rank key &rarr; <b>full trust</b></span>
  </div>

  <div class="board">
    <div class="toolbar">
      <label class="rulesel" for="rule">Reliability bar</label>
      <select id="rule" aria-label="Reliability bar">
        <option value="any">any@3 &mdash; passed in &ge;1 of 3 runs</option>
        <option value="majority" selected>majority@3 &mdash; passed in &ge;2 of 3 runs</option>
        <option value="all">all@3 &mdash; passed in all 3 runs</option>
      </select>
      <span class="toolbar-note">how each model's 3 runs collapse to one verdict per instance</span>
    </div>
    <div class="scroll">
      <table id="lb">
        <thead>
          <tr>
            <th class="rank lft" data-k="rank" data-dir="asc">#<span class="arrow">&uarr;</span></th>
            <th class="lft" data-k="model" data-dir="asc">Model<span class="arrow">&uarr;</span></th>
            <th data-k="attempted" data-dir="desc">Attempted<span class="arrow">&darr;</span></th>
            <th data-k="fl" data-dir="desc">FL<span class="arrow">&darr;</span></th>
            <th data-k="apr" data-dir="desc">APR<span class="arrow">&darr;</span></th>
            <th data-k="reasoning" data-dir="desc">Reasoning<span class="arrow">&darr;</span></th>
            <th class="trust sorted" data-k="full" data-dir="desc">Full trust<span class="arrow">&darr;</span></th>
            <th data-k="fix" data-dir="asc">Fix w/o loc<span class="arrow">&uarr;</span></th>
            <th data-k="rob" data-dir="desc">Robustness<span class="arrow">&darr;</span></th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div class="foot">
    <div>
      <h2>How to read it</h2>
      <dl>
        <dt>Full trust <span style="color:var(--faint);font-weight:400">&mdash; the ranking metric</span></dt>
        <dd>FL &and; APR &and; Reasoning on the same instance, with a Wilson 95% interval.
          The bar shows the interval; the tick is the point estimate.</dd>
        <dt>Fix without localizing</dt>
        <dd>Of instances the model resolved, the share where it pointed at the
          <em>wrong</em> fault line &mdash; a passing patch built on a wrong diagnosis. Lower is better.</dd>
        <dt>Attempted</dt>
        <dd>Instances the model produced a localization or patch for in &ge;2 runs.
          Engagement, not correctness &mdash; context for a low score.</dd>
        <dt>Robustness</dt>
        <dd>Retention under semantics-preserving code transforms. Pending until the
          transformed runs complete.</dd>
      </dl>
    </div>
    <div>
      <h2>Why joint trust</h2>
      <p class="thesis">Single-axis competence overstates trustworthiness. A model can
        pass tests while misreading the bug: across this set, <b>~31% of resolved
        patches localized the wrong line</b>. The leaderboard therefore leads with the
        one number that requires every axis at once &mdash; the metric no single-axis
        score can stand in for.</p>
      <p class="thesis" style="margin-top:1rem">Verdicts collapse each model's three runs by
        majority vote, so a single lucky run can't carry a rank; run-to-run instability
        shows up as a lower joint score.</p>
    </div>
  </div>

  <p class="credit">Generated from trust-cells-__COND__.csv &middot; FL &times; APR &times; Reasoning &middot; jury: opus-4.8 / gpt-5.3-codex / gemini-3.6-flash</p>
</div>

<script>
  const DATASETS = __DATASETS__;
  let DATA = DATASETS.majority;
  const fmt = v => v.toFixed(1);
  const sev = f => f < 25 ? "low" : f <= 40 ? "mid" : "high";
  const gauge = v => `<div class="gauge"><span class="val">${fmt(v)}</span>`+
    `<span class="bar"><i style="width:${v}%"></i></span></div>`;
  const trust = r => {
    const w = Math.max(2, r.hi - r.lo);
    return `<div class="trustcell"><span class="val">${fmt(r.full)}</span>`+
      `<span class="whisker"><span class="axis"></span>`+
      `<span class="ci" style="left:${r.lo}%;width:${w}%"></span>`+
      `<span class="pt" style="left:${r.full}%"></span></span></div>`;
  };
  const tbody = document.querySelector("#lb tbody");
  function render(rows){
    tbody.innerHTML = rows.map(r => `
      <tr class="${r.rank===1?'top':''}">
        <td class="rank"><span class="dot">${r.rank}</span></td>
        <td class="model"><span class="name">${r.model}</span></td>
        <td>${gauge(r.attempted)}</td>
        <td>${gauge(r.fl)}</td>
        <td>${gauge(r.apr)}</td>
        <td>${gauge(r.reasoning)}</td>
        <td class="trust">${trust(r)}</td>
        <td><span class="chip ${sev(r.fix)}">${fmt(r.fix)}</span></td>
        <td>${r.rob===null?'<span class="chip pending">pending</span>':gauge(r.rob)}</td>
      </tr>`).join("");
  }
  let curKey = "full", curDir = "desc";
  function sortBy(key, dir){
    const rows = [...DATA].sort((a,b)=>{
      let x=a[key], y=b[key];
      if(typeof x==="string") return dir==="asc"? x.localeCompare(y): y.localeCompare(x);
      x = x===null?-1:x; y = y===null?-1:y;
      return dir==="asc"? x-y : y-x;
    });
    render(rows);
  }
  document.querySelectorAll("#lb thead th").forEach(th=>{
    th.addEventListener("click", ()=>{
      const key = th.dataset.k;
      let dir = th.dataset.dir;
      if(key===curKey){ dir = curDir==="asc"?"desc":"asc"; }
      curKey=key; curDir=dir; th.dataset.dir=dir;
      document.querySelectorAll("#lb thead th").forEach(h=>{
        h.classList.remove("sorted");
        const a=h.querySelector(".arrow"); if(a) a.textContent = h.dataset.dir==="asc"?"↑":"↓";
      });
      th.classList.add("sorted");
      sortBy(key, dir);
    });
  });

  const ruleSel = document.getElementById("rule");
  const ruleLabel = document.getElementById("ruleLabel");
  const RULE_TXT = {any:"any@3", majority:"majority@3", all:"all@3"};
  ruleSel.addEventListener("change", ()=>{
    DATA = DATASETS[ruleSel.value];
    if(ruleLabel) ruleLabel.textContent = RULE_TXT[ruleSel.value];
    sortBy(curKey, curDir);
  });

  sortBy(curKey, curDir);
</script>
</body>
</html>
"""


def write_html(rows_by_rule, path, condition):
    def pack(rows):
        return [{"rank": r["rank"], "model": r["model"],
                 "attempted": round(r["coverage"] * 100, 1),
                 "fl": round(r["fl"] * 100, 1), "apr": round(r["apr"] * 100, 1),
                 "reasoning": round(r["reasoning"] * 100, 1),
                 "full": round(r["full_trust"] * 100, 1),
                 "lo": round(r["full_trust_lo"] * 100, 1),
                 "hi": round(r["full_trust_hi"] * 100, 1),
                 "fix": round(r["fix_without_loc"] * 100, 1),
                 "rob": None if r["robustness"] is None else round(r["robustness"] * 100, 1)}
                for r in rows]
    datasets = {rule: pack(rows_by_rule[rule]) for rule in RULES}
    n = rows_by_rule["majority"][0]["n"]
    html = (HTML_TEMPLATE
            .replace("__DATASETS__", json.dumps(datasets))
            .replace("__COND__", condition)
            .replace("__N__", str(n)))
    with open(path, "w") as fh:
        fh.write(html)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag", default="base", help="trust-cells suffix (default: base)")
    p.add_argument("--trust-cells", default=None, help="override trust-cells path")
    p.add_argument("--gt-dir", default=FE.DEFAULT_GT_DIR)
    p.add_argument("--robustness", default=None,
                   help="robustness-diff.csv to fill the retention column")
    p.add_argument("--out-csv", default=os.path.join(REPO, "leaderboard.csv"))
    p.add_argument("--out-md", default=os.path.join(REPO, "leaderboard.md"))
    p.add_argument("--out-html", default=os.path.join(REPO, "leaderboard.html"))
    args = p.parse_args(argv)

    suffix = f"-{args.tag}" if args.tag else ""
    tc_path = args.trust_cells or os.path.join(REPO, f"trust-cells{suffix}.csv")
    if not os.path.exists(tc_path):
        sys.exit(f"missing {tc_path} - run trust_axes.py --tag {args.tag}")

    instances = sorted(FE.load_ground_truth(args.gt_dir))
    if not instances:
        sys.exit(f"no instances under {args.gt_dir}")
    per, models = load_trust_cells(tc_path)
    robustness = load_robustness(args.robustness)
    rows_by_rule = {rule: score(per, models, instances, robustness, rule)
                    for rule in RULES}
    rows = rows_by_rule["majority"]           # primary for CSV headline / console / MD

    write_csv(rows_by_rule, args.out_csv)
    write_md(rows, args.out_md, args.tag or "base")
    write_html(rows_by_rule, args.out_html, args.tag or "base")

    # console (primary = majority@3; any@3/all@3 also in CSV + HTML dropdown)
    print(f"Trustworthiness leaderboard  (n={len(instances)} instances, "
          f"majority@{RUNS_EXPECTED}, condition={args.tag or 'base'})")
    print(f"{'#':>2} {'model':22}{'attn':>6}{'FL':>6}{'APR':>6}{'reas':>6}"
          f"{'FULL':>7}{'  95% CI':>16}{'fix\\loc':>8}{'robust':>8}")
    for r in rows:
        rob = "  pending" if r["robustness"] is None else f"{r['robustness']:.3f}"
        ci = f"[{r['full_trust_lo']:.2f},{r['full_trust_hi']:.2f}]"
        print(f"{r['rank']:>2} {r['model']:22}{r['coverage']:>6.2f}{r['fl']:>6.2f}"
              f"{r['apr']:>6.2f}{r['reasoning']:>6.2f}{r['full_trust']:>7.3f}"
              f"{ci:>16}{r['fix_without_loc']:>8.2f}{rob:>8}")
    print(f"\n-> {args.out_csv}\n-> {args.out_md}\n-> {args.out_html}")
    print(f"   serve: python3 -m http.server 8000  ->  "
          f"http://localhost:8000/{os.path.basename(args.out_html)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
