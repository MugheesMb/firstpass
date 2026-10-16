"""Exercise the Gemini code path with a fake client (no network, no credentials)."""
import json
from pathlib import Path
from types import SimpleNamespace

from app.ai import gemini, judge
from app.extraction.extractor import Classification, GeminiExtractor
from app.models import DocType

DEMO = Path(__file__).resolve().parents[1] / "demo_cases" / "demo_faisalabad_towels"


class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        schema = config.response_schema
        return SimpleNamespace(parsed=schema.model_validate(self.replies[schema.__name__]), text=None)


def _patch(monkeypatch, replies):
    fake = FakeModels(replies)
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=fake))
    return fake


def test_gemini_extraction_sends_page_images_and_schema(monkeypatch):
    truth = json.loads((DEMO / "lc.truth.json").read_text())["data"]
    fake = _patch(monkeypatch, {"LetterOfCredit": truth, "Classification": {"doc_type": "letter_of_credit", "confidence": 0.99}})
    t, data = GeminiExtractor().extract((DEMO / "lc.pdf").read_bytes(), "lc.pdf", "application/pdf", None, None)
    assert t == DocType.LC and data["lc_number"] == truth["lc_number"]
    # first call classifies, second extracts with the LC schema and a PNG page part
    assert fake.calls[0][2].response_schema is Classification
    model, contents, cfg = fake.calls[1]
    assert cfg.response_schema.__name__ == "LetterOfCredit"
    assert contents[0].inline_data.mime_type == "image/png"


def test_gemini_judge_falls_back_when_reasoning_model_fails(monkeypatch):
    calls = []

    def flaky(model, contents, config):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("model not found")
        return SimpleNamespace(parsed=config.response_schema(verdict="mismatch", reason="different product"), text=None)

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=flaky)))
    v = judge.GeminiJudge().invoice_description("tablet computers", "tablet PCs")
    assert v.verdict == "mismatch" and len(calls) == 2 and calls[0] != calls[1]


def test_runaway_field_is_retried_then_quarantined(monkeypatch):
    truth = json.loads((DEMO / "commercial_invoice.truth.json").read_text())["data"]
    junk = dict(truth, incoterm="CIF Rotterdam" + " Drafting your own legal forms <strong>US Legal Forms</strong>" * 20)
    replies = [junk, truth]  # bad first answer, good retry

    def gen(model, contents, config):
        data = replies.pop(0) if replies else truth
        return SimpleNamespace(parsed=config.response_schema.model_validate(data), text=None)

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    _, data = GeminiExtractor().extract((DEMO / "commercial_invoice.pdf").read_bytes(), "inv.pdf", "application/pdf",
                                        DocType.INVOICE, None)
    assert data["incoterm"] == "CIF Rotterdam" and not data["unreadable_fields"]

    # if both attempts are junk, the field is blanked and flagged for a human instead
    replies[:] = [junk, junk]
    _, data = GeminiExtractor().extract((DEMO / "commercial_invoice.pdf").read_bytes(), "inv.pdf", "application/pdf",
                                        DocType.INVOICE, None)
    assert data["incoterm"] is None and "incoterm" in data["unreadable_fields"]


def test_thinking_level_is_sent(monkeypatch):
    seen = []

    def gen(model, contents, config):
        seen.append(config.thinking_config)
        return SimpleNamespace(parsed=config.response_schema(doc_type="letter_of_credit", confidence=1.0), text=None)

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    GeminiExtractor().classify([b"x"])
    assert seen[0] is not None and str(seen[0].thinking_level).upper().endswith("LOW")


def test_client_is_created_once_under_concurrency(monkeypatch):
    """Threads racing on the first call must share one client (extra clients close the connection)."""
    import sys
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    made = []

    class SlowClient:
        def __init__(self, **kw):
            time.sleep(0.05)  # widen the race window
            self.kw = kw
            made.append(self)

    from google.genai import types as real_types

    fake_genai = SimpleNamespace(Client=SlowClient, types=real_types)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(sys.modules["google"], "genai", fake_genai, raising=False)
    monkeypatch.setattr(gemini, "_client", None)
    barrier = threading.Barrier(6)

    def get(_):
        barrier.wait()
        return gemini.client()

    with ThreadPoolExecutor(6) as pool:
        got = list(pool.map(get, range(6)))
    assert len(made) == 1 and all(c is made[0] for c in got)
    assert made[0].kw["http_options"].retry_options.attempts == 6
    monkeypatch.setattr(gemini, "_client", None)


def test_closed_client_is_rebuilt_and_retried(monkeypatch):
    calls = []

    def gen(model, contents, config):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        return SimpleNamespace(parsed=config.response_schema(doc_type="letter_of_credit", confidence=1.0), text=None)

    resets = []
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    monkeypatch.setattr(gemini, "_reset_client", lambda: resets.append(1))
    assert GeminiExtractor().classify([b"x"]) == DocType.LC
    assert len(calls) == 2 and resets == [1]


def test_cache_makes_second_read_free(monkeypatch, tmp_path):
    """Same PDF bytes + same model/prompt -> second extraction and judgement come from the cache."""
    from app import storage
    from app.ai import cache

    monkeypatch.setattr(cache, "enabled", True)
    store = storage.LocalFileStore.__new__(storage.LocalFileStore)
    store.root = tmp_path
    monkeypatch.setattr(storage, "files", lambda: store)
    truth = json.loads((DEMO / "commercial_invoice.truth.json").read_text())["data"]
    calls = []

    def gen(model, contents, config):
        calls.append(config.response_schema.__name__)
        if config.response_schema.__name__ == "Verdict":
            return SimpleNamespace(parsed=config.response_schema(verdict="mismatch", reason="x"), text=None)
        return SimpleNamespace(parsed=config.response_schema.model_validate(truth), text=None)

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    pdf = (DEMO / "commercial_invoice.pdf").read_bytes()
    a = GeminiExtractor().extract(pdf, "inv.pdf", "application/pdf", DocType.INVOICE, None)
    b = GeminiExtractor().extract(pdf, "inv.pdf", "application/pdf", DocType.INVOICE, None)
    assert a == b and calls == ["CommercialInvoice"]
    judge.GeminiJudge().invoice_description("towels", "sheets")
    v = judge.GeminiJudge().invoice_description("towels", "sheets")
    assert v.verdict == "mismatch" and calls == ["CommercialInvoice", "Verdict"]
    # a different document is not served from the cache
    GeminiExtractor().extract(pdf + b" ", "inv.pdf", "application/pdf", DocType.INVOICE, None)
    assert calls.count("CommercialInvoice") == 2


def test_cut_off_reply_keeps_complete_fields(monkeypatch):
    """A runaway field that hits the token limit is dropped and flagged; the rest of the document is kept."""
    truth = json.loads((DEMO / "packing_list.truth.json").read_text())["data"]
    good = {k: v for k, v in truth.items() if k != "goods_description"}
    text = json.dumps(good, indent=2)[:-2] + ',\n  "goods_description": "' + "Cotton polo as per invoice INV-1\\n" * 400

    def gen(model, contents, config):
        return SimpleNamespace(parsed=None, text=text)

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    _, data = GeminiExtractor().extract((DEMO / "packing_list.pdf").read_bytes(), "pl.pdf", "application/pdf",
                                        DocType.PACKING_LIST, None)
    assert data["packages_count"] == truth["packages_count"]
    assert data["goods_description"] is None and "goods_description" in data["unreadable_fields"]


def test_unreadable_document_does_not_fail_the_case(monkeypatch):
    def gen(model, contents, config):
        return SimpleNamespace(parsed=None, text='{\n  "packages_count": "12')  # nothing salvageable

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    t, data = GeminiExtractor().extract((DEMO / "packing_list.pdf").read_bytes(), "pl.pdf", "application/pdf",
                                        DocType.PACKING_LIST, None)
    assert t == DocType.PACKING_LIST and data["unreadable_fields"]
