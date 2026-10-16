"""Check Gemini works before deploying: models reachable, LC read correctly, one judgement call.

  cd backend
  AI_MODE=gemini GOOGLE_CLOUD_PROJECT=your-project python ../scripts/gemini_smoke.py

Compares what Gemini read from the demo LC and invoice with the known answers, field by field.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("AI_MODE", "gemini")

from app.config import settings  # noqa: E402
from app.extraction.extractor import GeminiExtractor  # noqa: E402
from app.models import DocType  # noqa: E402
from app.normalize import norm_text, to_date, to_number  # noqa: E402

DEMO = ROOT / "backend" / "demo_cases" / "demo_faisalabad_towels"


def same(a, b):
    """Lenient comparison: same text, or same date, or same number (Gemini may reformat slightly)."""
    if isinstance(a, list) or isinstance(b, list):
        return len(a or []) == len(b or [])
    if a is None or b is None:
        return a == b
    sa, sb = str(a), str(b)
    if norm_text(sa) == norm_text(sb):
        return True
    if any(c.isdigit() for c in sa) and any(c.isdigit() for c in sb):
        da, db = to_date(sa), to_date(sb)
        if da and db and da == db:
            return True
        na, nb = to_number(sa), to_number(sb)
        return na is not None and nb is not None and abs(na - nb) < 0.01
    return False


def main():
    print(f"Project {settings.gcp_project or '(from gcloud)'}, location {settings.gcp_location}")
    print(f"Extraction model {settings.model_extract}, reasoning model {settings.model_reason}\n")
    ex = GeminiExtractor()
    total = ok = 0
    for fname, dt in [("lc.pdf", DocType.LC), ("commercial_invoice.pdf", DocType.INVOICE)]:
        truth = json.loads((DEMO / fname.replace(".pdf", ".truth.json")).read_text())["data"]
        t0 = time.time()
        try:
            got_t, got = ex.extract((DEMO / fname).read_bytes(), fname, "application/pdf", dt, None)
        except Exception as e:  # noqa: BLE001
            print(f"FAILED to call Gemini on {fname}: {e}\n"
                  "Check: billing enabled, Vertex AI API enabled, model id available in this location, "
                  "`gcloud auth application-default login` done.")
            sys.exit(1)
        print(f"{fname}: read in {time.time() - t0:.1f} s")
        for k, v in truth.items():
            if k in ("evidence", "unreadable_fields") or v in (None, "", []):
                continue
            total += 1
            good = same(got.get(k), v)
            ok += good
            if not good:
                print(f"  MISMATCH {k}: expected {v!r}  got {got.get(k)!r}")
        boxes = sum(1 for e in got.get("evidence", []) if e.get("box_2d"))
        print(f"  evidence boxes returned: {boxes}")
        if got.get("unreadable_fields"):
            print(f"  flagged for manual check (implausible output after retry): {got['unreadable_fields']}")
        print()
    print(f"Fields correct: {ok}/{total} ({ok / total:.0%})")

    from app.ai.judge import GeminiJudge

    t0 = time.time()
    v = GeminiJudge().invoice_description("100% cotton bath towels, 500 GSM", "100% cotton bath sheets, 500 GSM")
    print(f"Judgement call ({time.time() - t0:.1f} s): {v.verdict} - {v.reason}")
    print("\nAll good if fields are mostly correct and the verdict is 'mismatch'.")


if __name__ == "__main__":
    main()
