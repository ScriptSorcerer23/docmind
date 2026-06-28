"""
DocMind — full automated test suite (final pass).

Covers everything from the manual test prompt set:
  A. Basic agent behavior (no tools)
  B. Single tool call
  C. Multi-step chained tool calls (the agentic loop)
  D. Edge cases (not-found, repeated-question consistency)
  E. 3-document cap + race condition
  F. Session isolation
  G. Stress / regression

IMPORTANT — read this before trusting a red line:
  Tests in sections A, B, E, F assert on deterministic application behavior
  (status codes, session scoping, the cap). A failure there is a real bug.

  Tests in sections C, D, G depend on a small LLM's judgment (does it chain
  two tools, does it phrase things consistently). These are marked SOFT in
  the output. A SOFT failure MIGHT mean a real bug, but it might also just be
  normal model variance — rerun before concluding it's broken. HARD failures
  are never expected to be flaky.

Usage:
    pip install requests --break-system-packages
    python test_docmind_full.py
"""

import time
import uuid
import sys
import requests

BASE_URL = "https://docmind-ojxl.onrender.com"

# ── Fill these in with REAL filenames already uploaded, or let the script
# upload its own fresh ones (default). Set USE_OWN_UPLOADS = False and fill
# in EXISTING_FILENAMES if you'd rather test against docs already sitting in
# a specific session.
USE_OWN_UPLOADS = True
EXISTING_FILENAMES = []  # e.g. ["Sumama-AI.pdf", "other-doc.pdf"]

TEST_A_CONTENT = (
    "DOCUMENT A — PROJECT PHOENIX\n"
    "Project Phoenix is an internal codename for a satellite imaging initiative.\n"
    "Project Phoenix is led by engineer Maria Chen and has a budget of $2.4 million.\n"
    "The project started in March 2025 and is based in Austin, Texas.\n"
)
TEST_B_CONTENT = (
    "DOCUMENT B — PROJECT TITAN\n"
    "Project Titan is an internal codename for a weather forecasting initiative.\n"
    "Project Titan is led by engineer David Park and has a budget of $5.1 million.\n"
    "The project started in January 2025 and is based in Denver, Colorado.\n"
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SOFT_FAIL = "\033[93mSOFT-FAIL\033[0m"

results = []  # (name, status, detail) where status in {"pass", "fail", "soft-fail"}


def record(name, ok, detail="", soft=False):
    if ok:
        status = "pass"
    elif soft:
        status = "soft-fail"
    else:
        status = "fail"
    results.append((name, status, detail))
    label = {"pass": PASS, "fail": FAIL, "soft-fail": SOFT_FAIL}[status]
    print(f"[{label}] {name}" + (f" — {detail}" if detail and status != "pass" else ""))


def headers(session_id):
    return {"X-Session-Id": session_id}


def upload(session_id, filename, content_bytes):
    files = {"file": (filename, content_bytes, "text/plain")}
    return requests.post(f"{BASE_URL}/upload", files=files, headers=headers(session_id), timeout=120)


def list_documents(session_id):
    return requests.get(f"{BASE_URL}/documents", headers=headers(session_id), timeout=30)


def delete_document(session_id, doc_id):
    return requests.delete(f"{BASE_URL}/documents/{doc_id}", headers=headers(session_id), timeout=30)


def chat(session_id, message, history=None):
    resp = requests.post(
        f"{BASE_URL}/chat",
        json={"message": message, "conversation_history": history or []},
        headers=headers(session_id),
        timeout=120,
    )
    # Groq's free tier caps at 8000 tokens/minute. Each chat call can be 2+
    # litellm completions (the agentic loop), so pace requests to avoid
    # tripping that ceiling mid-suite — a 429 here is a quota artifact of
    # running many tests back-to-back, not a real bug in the app.
    time.sleep(3)
    return resp


def cleanup_session(session_id):
    try:
        resp = list_documents(session_id)
        if resp.status_code == 200:
            for doc in resp.json():
                delete_document(session_id, doc["id"])
    except Exception:
        pass


def answer_of(resp):
    """Extract the answer from a /chat response. On non-200, surface the
    real error detail instead of silently returning an empty string —
    otherwise a 429/500 looks identical to 'the model said nothing'."""
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text
        return f"[HTTP {resp.status_code}] {detail}"
    try:
        return resp.json().get("answer", "")
    except Exception:
        return ""


def normalize(text):
    """Normalize cosmetic unicode the model likes to use (en-dash, non-breaking
    space, etc.) to plain ASCII equivalents, so 'test-phoenix.txt' still matches
    even if the model rendered it as 'test‑phoenix.txt' with a unicode hyphen."""
    return (
        text.replace("\u2011", "-")  # non-breaking hyphen
        .replace("\u2010", "-")      # hyphen
        .replace("\u2013", "-")      # en dash
        .replace("\u2014", "-")      # em dash
        .replace("\u202f", " ")      # narrow no-break space
        .replace("\xa0", " ")        # non-breaking space
    )


def contains(haystack, needle):
    """Substring check that's tolerant of cosmetic unicode formatting."""
    return normalize(needle) in normalize(haystack)


def main():
    session_a = f"test-a-{uuid.uuid4()}"
    session_b = f"test-b-{uuid.uuid4()}"
    print(f"Session A: {session_a}")
    print(f"Session B: {session_b}")
    print(f"Target: {BASE_URL}\n")

    cleanup_session(session_a)
    cleanup_session(session_b)

    # Set up documents for session A
    if USE_OWN_UPLOADS:
        r1 = upload(session_a, "test-phoenix.txt", TEST_A_CONTENT.encode())
        r2 = upload(session_a, "test-titan.txt", TEST_B_CONTENT.encode())
        doc_a1_id = r1.json().get("doc_id") if r1.status_code == 200 else None
        doc_a2_id = r2.json().get("doc_id") if r2.status_code == 200 else None
        filenames = ["test-phoenix.txt", "test-titan.txt"]
        record("Setup: upload two seed documents to session A", r1.status_code == 200 and r2.status_code == 200,
               f"r1={r1.status_code}, r2={r2.status_code}")
    else:
        filenames = EXISTING_FILENAMES
        doc_a1_id = doc_a2_id = None
        record("Setup: using existing filenames", len(filenames) >= 2,
               "EXISTING_FILENAMES needs at least 2 entries", soft=False)

    fname_1 = filenames[0] if filenames else "unknown-1.pdf"
    fname_2 = filenames[1] if len(filenames) > 1 else "unknown-2.pdf"

    # ══════════════════════════════════════════════════════════════
    # SECTION A — Basic agent behavior (HARD)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section A: Basic agent behavior ---")

    resp = chat(session_a, "hi")
    ans = answer_of(resp)
    record("A1. Greeting gets a normal reply, no doc leakage", resp.status_code == 200 and len(ans) > 0,
           f"status={resp.status_code}, answer={ans[:150]}")

    resp = chat(session_a, "what's the capital of France?")
    ans = answer_of(resp)
    record("A2. General knowledge answered directly (Paris)", resp.status_code == 200 and "paris" in ans.lower(),
           f"status={resp.status_code}, answer={ans[:150]}")

    # ══════════════════════════════════════════════════════════════
    # SECTION B — Single tool call (HARD)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section B: Single tool call ---")

    resp = chat(session_a, "what documents do you have?")
    ans = answer_of(resp)
    record(
        "B1. Lists real filenames (not vague non-answer)",
        resp.status_code == 200 and contains(ans, fname_1) and contains(ans, fname_2),
        f"status={resp.status_code}, answer={ans[:300]}",
    )

    resp = chat(session_a, "list them again")
    ans2 = answer_of(resp)
    record(
        "B2. Repeated listing is consistent (no hallucinated filenames)",
        resp.status_code == 200 and contains(ans2, fname_1) and contains(ans2, fname_2),
        f"status={resp.status_code}, answer={ans2[:300]}",
    )

    if USE_OWN_UPLOADS:
        resp = chat(session_a, "What is the budget for Project Phoenix?")
        ans = answer_of(resp)
        record(
            "B3. Retrieval pulls correct fact ($2.4 million)",
            resp.status_code == 200 and "2.4" in ans,
            f"status={resp.status_code}, answer={ans[:300]}",
        )

    # ══════════════════════════════════════════════════════════════
    # SECTION C — Multi-step chained tool calls (SOFT — model-dependent)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section C: Multi-step chained tool calls (SOFT — model-dependent) ---")

    resp = chat(session_a, f"what documents do you have, and summarize {fname_1}")
    ans = answer_of(resp)
    record(
        "C1. Chained list+summarize: names the file AND gives real summary content",
        resp.status_code == 200 and contains(ans, fname_1) and len(ans) > 100,
        f"status={resp.status_code}, answer={ans[:300]}",
        soft=True,
    )

    resp = chat(session_a, f"compare {fname_1} and {fname_2}")
    ans = answer_of(resp)
    record(
        "C2. Compare names both files and gives a real comparison",
        resp.status_code == 200 and contains(ans, fname_1) and contains(ans, fname_2) and len(ans) > 100,
        f"status={resp.status_code}, answer={ans[:300]}",
        soft=True,
    )

    resp = chat(session_a, "list my documents then compare the first two")
    ans = answer_of(resp)
    record(
        "C3. Multi-step (list -> compare) completes without error",
        resp.status_code == 200 and len(ans) > 50,
        f"status={resp.status_code}, answer={ans[:300]}",
        soft=True,
    )

    # ══════════════════════════════════════════════════════════════
    # SECTION D — Edge cases (mixed)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section D: Edge cases ---")

    resp = chat(session_a, "summarize a-document-that-does-not-exist.pdf")
    ans = answer_of(resp)
    record(
        "D1. Nonexistent document handled gracefully (no 500)",
        resp.status_code == 200,
        f"status={resp.status_code}, answer={ans[:300]}",
    )

    if USE_OWN_UPLOADS:
        answers = []
        for _ in range(3):
            r = chat(session_a, "What is the budget for Project Phoenix?")
            answers.append(answer_of(r))
        consistent = all("2.4" in a for a in answers)
        record(
            "D2. Same factual question answered consistently x3 (SOFT)",
            consistent,
            f"answers={[a[:80] for a in answers]}",
            soft=True,
        )

    # ══════════════════════════════════════════════════════════════
    # SECTION E — 3-document cap + race condition (HARD)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section E: Document cap + race condition ---")

    if USE_OWN_UPLOADS:
        r3 = upload(session_a, "test-third-doc.txt", b"Filler third document content.")
        record("E1. 3rd upload succeeds (at cap, not over)", r3.status_code == 200,
               f"got {r3.status_code}: {r3.text[:200]}")

        r4 = upload(session_a, "test-fourth-should-fail.txt", b"Filler fourth document content.")
        record(
            "E2. 4th upload rejected (cap enforced)",
            r4.status_code == 400 and "limit" in r4.text.lower(),
            f"got {r4.status_code}: {r4.text[:300]}",
        )

        # Race condition check: delete one, then fire two uploads back-to-back
        if doc_a1_id:
            delete_document(session_a, doc_a1_id)

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(upload, session_a, "race-1.txt", b"Race condition test file one.")
            f2 = ex.submit(upload, session_a, "race-2.txt", b"Race condition test file two.")
            race_r1 = f1.result()
            race_r2 = f2.result()

        succeeded = sum(1 for r in (race_r1, race_r2) if r.status_code == 200)
        list_resp = list_documents(session_a)
        final_count = len(list_resp.json()) if list_resp.status_code == 200 else -1
        record(
            "E3. Concurrent uploads never push session over the cap (trigger holds under race)",
            final_count <= 3,
            f"succeeded={succeeded}/2, final document count={final_count} (must be <= 3)",
        )

    # ══════════════════════════════════════════════════════════════
    # SECTION F — Session isolation (HARD — the most important section)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section F: Session isolation ---")

    resp = list_documents(session_b)
    docs_b = resp.json() if resp.status_code == 200 else []
    record("F1. Fresh session B starts empty", resp.status_code == 200 and docs_b == [],
           f"got: {docs_b}")

    rb = upload(session_b, "session-b-only.txt", b"This file belongs only to session B.")
    record("F2. Session B can upload its own document", rb.status_code == 200,
           f"got {rb.status_code}: {rb.text[:200]}")

    resp = list_documents(session_a)
    docs_a = resp.json() if resp.status_code == 200 else []
    record(
        "F3. Session A's list excludes session B's file",
        not any(d.get("filename") == "session-b-only.txt" for d in docs_a),
        f"got: {docs_a}",
    )

    if USE_OWN_UPLOADS:
        resp = chat(session_b, "What is the budget for Project Phoenix?")
        ans = answer_of(resp)
        record(
            "F4. Session B cannot retrieve session A's content (no leakage)",
            resp.status_code == 200 and "2.4" not in ans,
            f"status={resp.status_code}, answer={ans[:300]}",
        )

    resp = chat(session_b, "what documents do you have?")
    ans = answer_of(resp)
    record(
        "F5. Session B's document list only shows its own file",
        resp.status_code == 200 and contains(ans, "session-b-only.txt") and not contains(ans, fname_1),
        f"status={resp.status_code}, answer={ans[:300]}",
    )

    if doc_a2_id:
        resp = delete_document(session_b, doc_a2_id)
        record(
            "F6. Cross-session delete is blocked (expect 404)",
            resp.status_code == 404,
            f"got {resp.status_code}: {resp.text[:200]}",
        )

    # ══════════════════════════════════════════════════════════════
    # SECTION G — Stress / regression (SOFT)
    # ══════════════════════════════════════════════════════════════
    print("\n--- Section G: Stress / regression (SOFT) ---")

    resp = chat(session_a, f"compare {fname_1}, {fname_2}, and a-totally-fake-file.pdf")
    ans = answer_of(resp)
    record(
        "G1. Compare with one nonexistent file degrades gracefully (no 500)",
        resp.status_code == 200,
        f"status={resp.status_code}, answer={ans[:300]}",
        soft=True,
    )

    long_rambling = (
        "So I was thinking about a lot of things today, work has been busy, "
        "the weather is weird, anyway, quick question, completely unrelated, "
        f"what is the budget for Project Phoenix? anyway let me know whenever, no rush."
    )
    resp = chat(session_a, long_rambling)
    ans = answer_of(resp)
    record(
        "G2. Extracts the real question from a rambling message",
        resp.status_code == 200 and "2.4" in ans,
        f"status={resp.status_code}, answer={ans[:300]}",
        soft=True,
    )

    # ── Cleanup ───────────────────────────────────────────────────
    cleanup_session(session_a)
    cleanup_session(session_b)

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    hard_results = [r for r in results if r[1] in ("pass", "fail")]
    soft_results = [r for r in results if r[1] == "soft-fail" or (r[1] == "pass" and False)]
    n_pass = sum(1 for _, s, _ in results if s == "pass")
    n_fail = sum(1 for _, s, _ in results if s == "fail")
    n_soft = sum(1 for _, s, _ in results if s == "soft-fail")
    print(f"RESULTS: {n_pass} passed, {n_fail} HARD failures, {n_soft} soft failures (model-dependent)")

    if n_fail:
        print("\nHARD failures (real bugs — investigate these):")
        for name, status, detail in results:
            if status == "fail":
                print(f"  - {name}\n    {detail}")

    if n_soft:
        print("\nSoft failures (model-dependent — rerun before concluding it's broken):")
        for name, status, detail in results:
            if status == "soft-fail":
                print(f"  - {name}\n    {detail}")

    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()