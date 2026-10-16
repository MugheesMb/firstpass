"""Benchmark FirstPass on a generated test set.

  # offline: checks the rules engine against the answer key (extraction = ground truth)
  AI_MODE=mock   python eval/run_eval.py --data data/testset

  # real: Gemini extraction + judgement on the same PDFs
  AI_MODE=gemini GOOGLE_CLOUD_PROJECT=your-project python eval/run_eval.py --data data/testset

  # baseline for the deck: one plain Gemini prompt per case, no rules engine
  AI_MODE=gemini python eval/run_eval.py --data data/testset --baseline

Scoring is per (case, rule id). Only 'discrepancy' and 'possible' findings count as predictions;
'needs_review' items are reported separately.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import pipeline  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import FindingKind  # noqa: E402

COUNTED = {FindingKind.DISCREPANCY, FindingKind.POSSIBLE}


class _NoFreeTextReview:
    """Wraps the judge but skips the open-ended AI review of LC free text (A99).

    A99 is not scored (the answer key has no free-text risks) and it is the slowest call,
    so the benchmark skips it unless --with-ai-lc is given.
    """

    def __init__(self, judge):
        self._j = judge

    def __getattr__(self, name):
        return getattr(self._j, name)

    def review_lc(self, *a, **kw):
        return []


def run_firstpass(case_dir: Path, with_ai_lc: bool = False) -> tuple[set[str], set[str], int]:
    from app.ai.judge import get_judge

    case = pipeline.load_demo_case(case_dir)
    doc = pipeline.run_document_check(case)
    lc = pipeline.run_lc_review(case, judge=None if with_ai_lc else _NoFreeTextReview(get_judge()))
    pred_doc = {f.rule_id for f in doc.findings if f.kind in COUNTED}
    pred_lc = {f.rule_id for f in lc.findings if f.kind == FindingKind.LC_RISK and f.rule_id != "A99"}
    needs = sum(1 for f in doc.findings if f.kind == FindingKind.NEEDS_REVIEW)
    return pred_doc, pred_lc, needs


BASELINE_CATEGORIES = {
    "R01": "presentation after LC expiry", "R02": "shipment after latest shipment date", "R03": "presentation period exceeded",
    "R04": "invoice currency differs", "R05": "invoice amount exceeds LC", "R06": "quantity outside tolerance",
    "R07": "invoice issuer/addressee wrong", "R08": "invoice goods description differs", "R09": "other document description conflicts",
    "R10": "data conflict between documents (packages, weight, quantity)", "R11": "port differs from LC",
    "R12": "no on-board notation", "R13": "B/L not clean", "R14": "insurance dated after shipment",
    "R15": "insurance amount/currency wrong", "R16": "required document missing", "R20": "country of origin differs",
    "R21": "B/L consignee wrong", "R22": "trade term differs", "R23": "freight notation wrong", "R24": "wrong LC number",
}


def run_baseline(case_dir: Path) -> set[str]:
    """One plain prompt with all page images: what a generic chatbot would do."""
    from pydantic import BaseModel

    from app.ai.gemini import generate_json, png_part
    from app.extraction import render

    class Out(BaseModel):
        categories: list[str]

    meta = json.loads((case_dir / "case.json").read_text())
    parts = []
    for f in meta["files"]:
        for png in render.to_pngs((case_dir / f["file"]).read_bytes(), f["file"]):
            parts.append(png_part(png))
    cats = "\n".join(f"{k}: {v}" for k, v in BASELINE_CATEGORIES.items())
    parts.append(f"These are a Letter of Credit and the documents presented under it. Planned presentation date: "
                 f"{meta['presentation_date']}. List the discrepancy categories you find, using only these codes:\n{cats}")
    return set(generate_json(settings.model_extract, parts, Out).categories) & set(BASELINE_CATEGORIES)


def pick_covering(cases: list[Path], n: int) -> list[Path]:
    """N cases that together contain every planted rule (greedy), ~30% clean, rest filled in order."""
    meta = {c: json.loads((c / "case.json").read_text()) for c in cases}
    rules = lambda c: set(meta[c]["expected_document_rules"]) | {"LC:" + r for r in meta[c]["expected_lc_rules"]}
    clean = [c for c in cases if not meta[c]["expected_document_rules"]][: max(1, round(n * 0.3))]
    pick, need = list(clean), set().union(*(rules(c) for c in cases))
    rest = [c for c in cases if c not in pick]
    while need and len(pick) < n:
        best = max(rest, key=lambda c: len(need & rules(c)))
        if not need & rules(best):
            break
        pick.append(best); rest.remove(best); need -= rules(best)
    pick += [c for c in rest if meta[c]["expected_document_rules"]][: n - len(pick)]
    return sorted(pick)


def score(rows: list[tuple[set, set]]) -> dict:
    tp = sum(len(p & e) for p, e in rows)
    fp = sum(len(p - e) for p, e in rows)
    fn = sum(len(e - p) for p, e in rows)
    return dict(tp=tp, fp=fp, fn=fn,
                recall=round(tp / (tp + fn), 3) if tp + fn else None,
                precision=round(tp / (tp + fp), 3) if tp + fp else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "testset"))
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.json"))
    ap.add_argument("--limit", type=int, default=0, help="only the first N cases (try 5 first with Gemini)")
    ap.add_argument("--cover", type=int, default=0,
                    help="pick N cases that together cover every planted rule, plus clean cases")
    ap.add_argument("--only", default="", help="comma-separated case names to run, e.g. case_012,case_014")
    ap.add_argument("--workers", type=int, default=0, help="cases run at the same time (default 4 with Gemini, 1 in mock)")
    ap.add_argument("--cache", action="store_true", help="reuse cached Gemini results (fast re-runs; timings not real)")
    ap.add_argument("--with-ai-lc", action="store_true", help="also run the unscored AI review of LC free text (slow)")
    a = ap.parse_args()
    from app.ai import cache

    cache.enabled = a.cache
    workers = a.workers or (4 if settings.use_gemini else 1)
    if settings.use_gemini:
        from app.ai import gemini

        if not hasattr(gemini, "_lock"):
            sys.exit("backend/app/ai/gemini.py is an old version (no shared client). Unzip the latest firstpass.zip.")
        gemini.client()  # create the one shared client before any threads start
    data = Path(a.data)
    cases = sorted(p for p in data.iterdir() if (p / "case.json").exists())
    if a.limit:
        # keep a mix of clean and problem cases: the first 10 are clean, so take from both ends
        cases = (cases[: max(1, a.limit // 3)] + cases[-(a.limit - max(1, a.limit // 3)):])[: a.limit]
    if a.cover:
        cases = pick_covering(cases, a.cover)
    if a.only:
        cases = [c for c in cases if c.name in set(a.only.split(","))]
    doc_rows, lc_rows, base_rows, per_case = [], [], [], []
    clean_alarms = clean_total = needs_total = 0
    t0 = time.time()
    def one(cd: Path):
        t = time.time()
        try:
            return cd, run_firstpass(cd, a.with_ai_lc), None, time.time() - t
        except Exception as e:  # noqa: BLE001 - one failed case should not lose the whole run
            return cd, None, e, time.time() - t

    print(f"{len(cases)} cases, {workers} at a time ({settings.ai_mode} mode)...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = list(pool.map(one, cases)) if workers == 1 else None
        if done is None:
            futures = [pool.submit(one, cd) for cd in cases]
            done = []
            for f in as_completed(futures):
                done.append(f.result())
                cd, res, err, secs = done[-1]
                print(f"  [{len(done)}/{len(cases)}] {cd.name} {secs:.0f} s" + (f"  FAILED: {err}" if err else ""), flush=True)
    failed = []
    for cd, res, err, secs in sorted(done, key=lambda d: d[0].name):
        if err:
            failed.append(dict(case=cd.name, error=str(err)))
            continue
        pred_doc, pred_lc, needs = res
        meta = json.loads((cd / "case.json").read_text())
        exp_doc, exp_lc = set(meta["expected_document_rules"]), set(meta["expected_lc_rules"])
        needs_total += needs
        doc_rows.append((pred_doc, exp_doc))
        lc_rows.append((pred_lc, exp_lc))
        if not exp_doc:
            clean_total += 1
            clean_alarms += bool(pred_doc)
        row = dict(case=cd.name, seconds=round(secs, 1), expected=sorted(exp_doc), predicted=sorted(pred_doc),
                   missed=sorted(exp_doc - pred_doc), false_alarms=sorted(pred_doc - exp_doc),
                   lc_expected=sorted(exp_lc), lc_predicted=sorted(pred_lc))
        if a.baseline:
            b = run_baseline(cd)
            base_rows.append((b, exp_doc))
            row["baseline_predicted"] = sorted(b)
        per_case.append(row)
        print(f"{cd.name}: expected {sorted(exp_doc)} got {sorted(pred_doc)}"
              + (f" | baseline {row['baseline_predicted']}" if a.baseline else ""))

    result = dict(ai_mode=settings.ai_mode, cache_used=a.cache, model_extract=settings.model_extract, cases=len(cases),
                  seconds=round(time.time() - t0, 1),
                  document_check=score(doc_rows), lc_review=score(lc_rows),
                  clean_cases=clean_total, clean_cases_with_false_alarm=clean_alarms, needs_review_items=needs_total, failed_cases=failed,
                  baseline=score(base_rows) if a.baseline else None, per_case=per_case)
    Path(a.out).write_text(json.dumps(result, indent=1))
    print("\n=== FirstPass results ===")
    print(json.dumps({k: v for k, v in result.items() if k != "per_case"}, indent=1))


if __name__ == "__main__":
    main()
