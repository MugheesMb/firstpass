"""Run every demo case once against the deployed API so Gemini's results are cached.

  python scripts/warm_demo.py https://firstpass-api-xxxx.a.run.app

Each demo case is read by Gemini, reviewed, checked, then its corrected documents are applied and
re-checked: every step of the recorded demo. After this, the same steps in the app return in about
a second, because the results come from the cache (same PDF bytes, same model, same prompt).
Takes a few minutes; safe to run again (a second run is fast).
"""
import json
import sys
import time
import urllib.request


def call(base, method, path, body=None):
    req = urllib.request.Request(base.rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = sys.argv[1]
    demos = [d for d in call(base, "GET", "/api/demo") if d["group"] == "demo"]
    print(f"{len(demos)} demo cases")
    for d in demos:
        t0 = time.time()
        case = call(base, "POST", f"/api/demo/{d['name']}")
        cid = case["id"]
        call(base, "POST", f"/api/cases/{cid}/lc-review")
        rep = call(base, "POST", f"/api/cases/{cid}/check", {})
        fixes = call(base, "GET", f"/api/cases/{cid}/sample-corrections")
        for fx in fixes:
            call(base, "POST", f"/api/cases/{cid}/sample-corrections/{fx['doc_type']}")
        if fixes:
            call(base, "POST", f"/api/cases/{cid}/check", {})
        print(f"  {d['name']}: {len(rep['findings'])} finding(s), {len(fixes)} correction(s), {time.time() - t0:.0f} s")
    print("Cached. Loading these cases in the app is now fast.")


if __name__ == "__main__":
    main()
