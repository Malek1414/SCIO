# ember — cohort typing & heat signature

**Date:** 2026-09-16
**Status:** approved in brainstorming; awaiting spec review
**Owner:** Malek
**Supersedes:** nothing. Extends the v1 design (§7 Graph), which specced a cohort scatter
and a subject radar. The subject view described there was never built; this spec builds it.

---

## 1. What this is

An operator-facing cohort page that answers one question: **what do these people have in
common, and where do they actually differ?** It replaces the 197-line `graph/index.html`
scatter with four panels driven by a deterministic typing analysis.

Typing is **bottom-up**. Profiles are clustered on their own shape; the resulting groups are
interpreted afterward. No personality taxonomy is imposed on the data and no subject is
fitted to a predefined type.

---

## 2. The findings this is built on

Two populations are referenced throughout and must not be confused:

- **n=18** — the 20 subjects in `graph/data.js` less the `TEST` and `S00` pilots.
- **n=16** — n=18 less `S06` and `S10`, the non-engaged subjects of §2.5.

The table below is **n=16**. The floors hold in both populations; on n=18 the means are
F1 1.72, C2 1.78, G1 1.61, C3 4.39, and no subject reaches 5 on F1, C2 or G1 in either.
Typing (§2.3–2.4) is n=16. Per-construct distributions on the page are n=18.

### 2.1 Cohort constants

Four constructs behave nearly identically for everyone and therefore distinguish nobody:

| Construct | mean | max | scored ≥5 | bank coverage |
|---|---|---|---|---|
| F1 Driver specificity | 1.81 | 3 | 0 / 16 | 5 of 21 questions |
| C2 Transcendence frame | 1.88 | 4 | 0 / 16 | 2 of 21 |
| G1 Solitude stance | 1.69 | 3 | 0 / 16 | **1 of 21** |
| C3 Fear specificity | 4.81 | 6 | 12 / 16 | 1 of 21 |

The headline: **this cohort describes what it fears precisely and what it wants vaguely.**
F1 is the credible half — it is the best-covered construct in the bank, so it was asked
repeatedly and still floored. G1 is confounded by coverage (one question in a seven-question
session) and is reported with that caveat attached, never as a finding on its own.

### 2.2 Type discriminators

F2, F3, C1, G2, G3 carry the between-person variance. Typing uses all nine constructs, but
these five are what separate the groups, and the UI marks them as such.

### 2.3 Method, and why the obvious method fails

Clustering raw 9-dimensional scores finds nothing (silhouette ≈ 0.17 at k=2,3,4) because
Euclidean distance on raw scores is dominated by overall level — it rediscovers "high scorer
vs low scorer." There is also no general factor (PC1 = 28%, mean inter-construct r = +0.08
with 12 of 36 pairs negative).

Clustering on **shape** does find structure. Within-person z-scoring removes level; correlation
distance with average linkage then yields merge heights of 0.08, 0.12, 0.12, 0.16, 0.18 before
jumping to 0.76 and 1.07.

### 2.4 Groups at k=4

| Group | n | Signature |
|---|---|---|
| Relational, uncosted | 4 | G3 4.2, C3 5.0 high; F2 1.8, F1 1.2 low |
| Costed | 7 | F2 3.4, F3 4.0, C3 5.1 |
| Processed | 4 (+2 excluded) | G2 3.3, F3 4.3; C3 lower at 3.5 |
| Inverse | 1 | The only subject with low C3, alongside high F2/F3/C1 |

Group names are descriptive labels for the observed pattern, not claims about psychological
types. The page states n for every group.

### 2.5 Subjects excluded from typing

`S06` and `S10` score at or near floor on all nine constructs (totals 1.1 and 1.3) and their
contributed files are markedly smaller than the rest. A flat profile has no shape, so
correlation distance places them arbitrarily. They are **excluded from typing and shown
separately as non-engaged**, with the reason stated on the page. They remain in the
per-construct distributions, where their scores are real data.

---

## 3. Scope

**In scope:** the four panels in §5; `ember/analysis.py`; the `load_bank` language fix in §6;
local repair of `RAFAEL` and `RUBEN`.

**Out of scope:** re-collecting the 15 German sessions from interviewers; a traina-style
standalone product; any change to the interview engine, the rubric, or the question bank;
longitudinal or repeat-session support.

---

## 4. Architecture

```
observer.json / results/*.json
        │
        ├─ export.collect()          existing, unchanged
        │
        └─ analysis.py               NEW — all statistics, pure functions, no I/O, no LLM
                 │
                 ▼
           graph/data.js             existing file, extended with an "analysis" key
                 │
                 ▼
           graph/index.html          rewritten — four panels, static, opens from file://
```

Constraints, following traina's split between computation and presentation:

- **Every number is computed in Python and tested.** The page renders what it is given and
  computes nothing beyond layout.
- **No model call in the render path.** Nothing on the page is worded by an LLM at view time.
- **Static and local.** The page opens from `file://` with no server and no network fetch.
  d3 is already vendored for the current page and stays.
- **Additive data contract.** `data.js` keeps every existing key; the analysis lands under a
  new `analysis` key so anything reading the current shape keeps working.

### 4.1 `ember/analysis.py`

Pure functions over the subject list, no file or network access, deterministic for a given
input. Ties in linkage are broken by subject code so output is byte-stable across runs.

| Function | Returns |
|---|---|
| `zprofile(scores)` | within-person z-scored 9-vector |
| `shape_distance(a, b)` | correlation distance, `1 - r`, over two z-profiles |
| `linkage(subjects)` | average-linkage merge sequence with heights |
| `seriate(linkage)` | subject order for heat-signature rows |
| `cut(linkage, k)` | k groups, each with members and a mean profile |
| `constants_and_discriminators(subjects)` | the §2.1 / §2.2 split, computed not hardcoded |
| `bank_coverage(bank)` | questions per construct, for the caveat annotations |
| `engagement_outliers(subjects)` | subjects excluded from typing, with reasons |
| `analyse(subjects, bank)` | the whole `analysis` block for `data.js` |

The §2 thresholds (floor, ceiling, flatness) are module constants with the observed values as
defaults, not literals buried in function bodies.

---

## 5. Panels

1. **Heat signature.** 18 × 9 grid, subject rows seriated by `seriate()`, colour = score 1–7,
   group cuts drawn as row separators. The vertical bands are the argument and must be legible
   without narration.
2. **Constants vs discriminators.** The two construct sets from §2.1/§2.2, each annotated with
   its bank coverage. `G1 · 1 of 21 questions` appears on the chart itself.
3. **The four groups.** Mean profile per group, members listed, discriminating constructs
   emphasised, n stated. Non-engaged subjects shown outside the groups.
4. **Subject detail.** Nine-spoke radar (1–7), evidence quotes per construct, flags, then the
   mirror and take-home. Satisfies v1 §7's subject view.

**Data-quality banner**, always visible: signal and declined are suppressed for the 15 German
sessions pending §6; `S06`/`S10` are excluded from typing; n is stated. Presenting the limits
is what makes the rest credible.

---

## 6. The instrument fix

`coverage()` (`observer.py:105`) matches transcript turns against a map keyed by **question
text** built from the bank. `cli.py:110` passes `load_bank()`, which defaults to English. A
German transcript looked up in an English map matches nothing, so `observer.py:144`
(`if not cov[cid]: declined.add(cid)`) marks all nine constructs declined, which sets
`skipped=True` and collapses `signal` to its floor.

Confirmed by perfect separation: all 15 German sessions have 9/9 declined; all 3 English
sessions are normal (3, 4, 7).

**Blast radius:** `declined` and `signal` are wrong for 83% of the cohort. **Scores are
unaffected** — they come from the model and never pass through `coverage()`. Every finding in
§2 rests on scores and therefore stands.

**Fix:** resolve the bank from the transcript's `language` in the observe path. The rubric
stays shared and English, which is correct and already documented at `cli.py:24`; only the
question bank is language-specific.

**Repair:** `RAFAEL` and `RUBEN` have local transcripts, so coverage and signal recompute
deterministically with no model call. The 14 contributed German subjects have no transcripts
here — by design, transcripts never leave the interviewer's machine — and are **not
repairable locally**. They stay flagged in the banner until re-contributed.

---

## 7. Testing

- `analysis.py` unit-tested against hand-computed fixtures: a known z-profile, a known
  correlation distance, a three-subject linkage with a hand-checked merge order, and a flat
  profile that must be reported as non-engaged rather than clustered.
- Determinism: `analyse()` on the same input twice is byte-identical.
- Regression for §6: a German transcript through `coverage()` yields non-empty coverage, and
  a German session no longer reports all nine declined. This test fails against current `main`.
- The existing suite stays green.

---

## 8. Known limits

Stated here and on the page; not to be discovered by the audience.

- **n=16 typed.** Groups of 7, 4, 4 and 1. Suggestive, not significant. No p-values are shown
  because none would survive correction at this n.
- **Group names are descriptive**, chosen from the observed pattern. They are not validated
  psychological types and nothing cross-references an external taxonomy.
- **G1 is confounded** by one-question coverage and is never reported as a standalone finding.
- **15 of 18 sessions are German**, scored against an English rubric. Deliberate per v1, but it
  is a translation step between what a subject said and how it was scored.
- **83% of the cohort has unusable `signal`/`declined`** until §6 is fixed and those sessions
  are re-contributed.
