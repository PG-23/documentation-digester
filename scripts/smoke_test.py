"""I-2 milestone check: run ingest, start the API, and confirm /search returns results with metadata.

Usage (from the repo root):
    python scripts/smoke_test.py                     # ingest, start the API, query it, stop it
    python scripts/smoke_test.py --skip-ingest       # reuse the existing index
    python scripts/smoke_test.py --url http://localhost:8000   # test an API you already started

Exits 0 if every check passes, 1 otherwise. Uses only the standard library.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Per-result fields from task board A-2. Update here if the team changes the format.
REQUIRED_FIELDS = ["text", "score", "title", "url", "source_file", "chunk_index"]
# Stored by ingest (G-2) but not required in /search results; reported as a warning only.
OPTIONAL_FIELDS = ["section"]

DEFAULT_QUESTIONS = [
    "How do I use signals to communicate between nodes?",
    "What is a scene and how does it relate to nodes?",
    "How do I declare a variable in GDScript?",
]

HOST, PORT = "127.0.0.1", 8000


def step(msg):
    print(f"\n== {msg}")


def run_ingest():
    step("Running ingest: python -m ingest.ingest")
    start = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "ingest.ingest"])
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        print(f"FAIL  ingest exited with code {result.returncode}")
        return False
    print(f"OK    ingest finished in {elapsed:.1f}s")
    return True


def start_api():
    step(f"Starting API: uvicorn api.main:app on {HOST}:{PORT}")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", HOST, "--port", str(PORT)]
    )


def wait_for_api(base_url, proc=None, timeout=90):
    # Model loading can take a while on first start, so poll /docs (always served by FastAPI).
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            print(f"FAIL  API process exited early with code {proc.returncode}")
            return False
        try:
            with urllib.request.urlopen(f"{base_url}/docs", timeout=3):
                print("OK    API is up")
                return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(1)
    print(f"FAIL  API did not respond within {timeout}s")
    return False


def search(base_url, query, k):
    """Try GET /search?query=..&k=.., then POST /search with a JSON body, since the method isn't fixed yet."""
    params = urllib.parse.urlencode({"query": query, "k": k})
    attempts = [
        urllib.request.Request(f"{base_url}/search?{params}"),
        urllib.request.Request(
            f"{base_url}/search",
            data=json.dumps({"query": query, "k": k}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
    ]
    last_error = None
    for req in attempts:
        try:
            start = time.perf_counter()
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
            return body, (time.perf_counter() - start) * 1000, None
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code} on {req.get_method()} /search"
            if e.code not in (404, 405, 422):
                break
        except (urllib.error.URLError, ValueError) as e:
            last_error = str(e)
            break
    return None, 0, last_error


def extract_results(body):
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        return body["results"]
    return None


def check_results(results, k):
    problems = []
    if not results:
        problems.append("no results returned")
    if len(results) > k:
        problems.append(f"returned {len(results)} results, more than k={k}")
    for i, r in enumerate(results):
        flat = dict(r)
        if isinstance(r.get("metadata"), dict):  # allow metadata nested under "metadata"
            flat.update(r["metadata"])
        missing = [f for f in REQUIRED_FIELDS if flat.get(f) in (None, "")]
        if missing:
            problems.append(f"result {i + 1} ({flat.get('source_file') or '?'}) missing: {', '.join(missing)}")
    absent = sorted({f for r in results for f in OPTIONAL_FIELDS
                     if {**r, **(r.get('metadata') or {})}.get(f) in (None, "")})
    if absent:
        print(f"WARN  optional field(s) not returned: {', '.join(absent)}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="test an already-running API instead of starting one")
    ap.add_argument("--skip-ingest", action="store_true", help="don't run ingest first")
    ap.add_argument("-k", type=int, default=5, help="results per query (default 5)")
    ap.add_argument("-q", "--question", action="append", help="question to ask (repeatable)")
    args = ap.parse_args()

    questions = args.question or DEFAULT_QUESTIONS
    base_url = (args.url or f"http://{HOST}:{PORT}").rstrip("/")
    proc = None
    failures = 0

    try:
        if not args.skip_ingest and not run_ingest():
            return 1
        if not args.url:
            proc = start_api()
        if not wait_for_api(base_url, proc):
            return 1

        for q in questions:
            step(f"Query: {q}")
            body, ms, err = search(base_url, q, args.k)
            if err:
                print(f"FAIL  {err}")
                failures += 1
                continue
            results = extract_results(body)
            if results is None:
                print(f"FAIL  unexpected response shape: {json.dumps(body)[:200]}")
                failures += 1
                continue
            problems = check_results(results, args.k)
            for i, r in enumerate(results, 1):
                meta = {**r, **(r.get("metadata") or {})}
                score = meta.get("score")
                score_s = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
                where = " > ".join(str(x) for x in (meta.get("title"), meta.get("section")) if x)
                print(f"  {i}. [{score_s}] {where} ({meta.get('source_file')} #{meta.get('chunk_index')})")
            if problems:
                for p in problems:
                    print(f"FAIL  {p}")
                failures += 1
            else:
                print(f"OK    {len(results)} results with full metadata in {ms:.0f} ms")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    step("Result")
    if failures:
        print(f"I-2 NOT MET: {failures} of {len(questions)} queries failed")
        return 1
    ingest_note = "existing index" if args.skip_ingest else "fresh ingest"
    print(f"I-2 MET ({ingest_note}): all {len(questions)} queries returned results with metadata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
