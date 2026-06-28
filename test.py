"""
DocMind — automated end-to-end test suite.

Hits the live deployed backend directly over HTTP. No mocking — this is a
real integration test against your actual Render + Supabase deployment.

Usage:
    pip install requests --break-system-packages
    python test_docmind.py

Edit BASE_URL below if your Render URL has changed.
"""

import time
import uuid
import sys
import requests

BASE_URL = "https://docmind-ojxl.onrender.com"

TEST_A_CONTENT = (
    "DOCUMENT A — PROJECT PHOENIX\n"
    "The secret launch code for Project Phoenix is ALPHA-7731.\n"
    "Project Phoenix is led by engineer Maria Chen and has a budget of $2.4 million.\n"
)
TEST_B_CONTENT = (
    "DOCUMENT B — PROJECT TITAN\n"
    "The secret launch code for Project Titan is OMEGA-9042.\n"
    "Project Titan is led by engineer David Park and has a budget of $5.1 million.\n"
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    status = PASS if ok else FAIL
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not ok else ""))


def session_headers(session_id):
    return {"X-Session-Id": session_id}


def upload(session_id, filename, content_bytes):
    files = {"file": (filename, content_bytes, "text/plain")}
    return requests.post(
        f"{BASE_URL}/upload",
        files=files,
        headers=session_headers(session_id),
        timeout=120,
    )


def list_documents(session_id):
    return requests.get(
        f"{BASE_URL}/documents",
        headers=session_headers(session_id),
        timeout=30,
    )


def delete_document(session_id, doc_id):
    return requests.delete(
        f"{BASE_URL}/documents/{doc_id}",
        headers=session_headers(session_id),
        timeout=30,
    )


def chat(session_id, message, history=None):
    return requests.post(
        f"{BASE_URL}/chat",
        json={"message": message, "conversation_history": history or []},
        headers=session_headers(session_id),
        timeout=120,
    )


def cleanup_session(session_id):
    """Best-effort: delete any docs left over from a previous failed run."""
    try:
        resp = list_documents(session_id)
        if resp.status_code == 200:
            for doc in resp.json():
                delete_document(session_id, doc["id"])
    except Exception:
        pass


def main():
    session_a = f"test-session-a-{uuid.uuid4()}"
    session_b = f"test-session-b-{uuid.uuid4()}"

    print(f"Session A: {session_a}")
    print(f"Session B: {session_b}")
    print(f"Target: {BASE_URL}\n")

    cleanup_session(session_a)
    cleanup_session(session_b)

    # ── Test 1: Missing session header is rejected ──────────────────
    resp = requests.get(f"{BASE_URL}/documents", timeout=30)
    record(
        "1. Missing X-Session-Id header is rejected",
        resp.status_code == 400,
        f"got {resp.status_code}, expected 400",
    )

    # ── Test 2: Session A starts with zero documents ────────────────
    resp = list_documents(session_a)
    record(
        "2. Fresh session starts empty",
        resp.status_code == 200 and resp.json() == [],
        f"got {resp.status_code}: {resp.text[:200]}",
    )

    # ── Test 3: Upload succeeds ──────────────────────────────────────
    resp = upload(session_a, "test-a.txt", TEST_A_CONTENT.encode())
    upload_ok = resp.status_code == 200
    record("3. Upload document A to session A", upload_ok, f"got {resp.status_code}: {resp.text[:300]}")
    doc_a_id = resp.json().get("doc_id") if upload_ok else None

    # ── Test 4: Document appears in session A's list ────────────────
    resp = list_documents(session_a)
    docs = resp.json() if resp.status_code == 200 else []
    record(
        "4. Uploaded document appears in session A's list",
        any(d.get("filename") == "test-a.txt" for d in docs),
        f"got: {docs}",
    )

    # ── Test 5: list_available_documents tool names the file in chat ─
    resp = chat(session_a, "What documents do you have?")
    chat_ok = resp.status_code == 200
    answer = resp.json().get("answer", "") if chat_ok else ""
    record(
        "5. Chat names the actual filename (not a vague non-answer)",
        chat_ok and "test-a.txt" in answer,
        f"status={resp.status_code}, answer={answer[:300]}",
    )

    # ── Test 6: Retrieval pulls correct content ──────────────────────
    resp = chat(session_a, "What is the secret launch code for Project Phoenix?")
    chat_ok = resp.status_code == 200
    answer = resp.json().get("answer", "") if chat_ok else ""
    record(
        "6. Retrieval answers with the correct fact (ALPHA-7731)",
        chat_ok and "ALPHA-7731" in answer,
        f"status={resp.status_code}, answer={answer[:300]}",
    )

    # ── Test 7: Greeting doesn't trigger retrieval/tool confusion ───
    resp = chat(session_a, "hi")
    chat_ok = resp.status_code == 200
    answer = resp.json().get("answer", "") if chat_ok else ""
    record(
        "7. Plain greeting gets a normal reply",
        chat_ok and len(answer) > 0 and "ALPHA" not in answer,
        f"status={resp.status_code}, answer={answer[:200]}",
    )

    # ── Test 8: Upload 2 more docs to hit the cap (3 total) ──────────
    upload(session_a, "test-c.txt", b"Filler document C content.")
    resp = upload(session_a, "test-d-should-still-fit.txt", b"Filler document D content.")
    record(
        "8. Session A now at 3 documents (cap not yet exceeded)",
        resp.status_code == 200,
        f"got {resp.status_code}: {resp.text[:300]}",
    )

    # ── Test 9: 4th upload is rejected by the cap ────────────────────
    resp = upload(session_a, "test-e-should-be-rejected.txt", b"Filler document E content.")
    record(
        "9. 4th upload is rejected (3-document cap enforced)",
        resp.status_code == 400 and "limit" in resp.text.lower(),
        f"got {resp.status_code}: {resp.text[:300]}",
    )

    # ── Test 10: Session B is completely separate ────────────────────
    resp = list_documents(session_b)
    docs_b = resp.json() if resp.status_code == 200 else []
    record(
        "10. Session B sees zero documents (no leakage from session A)",
        resp.status_code == 200 and docs_b == [],
        f"got: {docs_b}",
    )

    # ── Test 11: Session B uploads its own doc ────────────────────────
    resp = upload(session_b, "test-b.txt", TEST_B_CONTENT.encode())
    record("11. Session B can upload its own document", resp.status_code == 200, f"got {resp.status_code}: {resp.text[:300]}")

    # ── Test 12: Session A's list is unaffected by session B's upload ─
    resp = list_documents(session_a)
    docs_a = resp.json() if resp.status_code == 200 else []
    record(
        "12. Session A's document list excludes session B's file",
        not any(d.get("filename") == "test-b.txt" for d in docs_a),
        f"got: {docs_a}",
    )

    # ── Test 13: Session B's chat can't see session A's content ──────
    resp = chat(session_b, "What is the secret launch code for Project Phoenix?")
    chat_ok = resp.status_code == 200
    answer = resp.json().get("answer", "") if chat_ok else ""
    record(
        "13. Session B cannot retrieve session A's secret (ALPHA-7731 must NOT appear)",
        chat_ok and "ALPHA-7731" not in answer,
        f"status={resp.status_code}, answer={answer[:300]}",
    )

    # ── Test 14: Session B retrieves its OWN content correctly ───────
    resp = chat(session_b, "What is the secret launch code for Project Titan?")
    chat_ok = resp.status_code == 200
    answer = resp.json().get("answer", "") if chat_ok else ""
    record(
        "14. Session B correctly retrieves its own secret (OMEGA-9042)",
        chat_ok and "OMEGA-9042" in answer,
        f"status={resp.status_code}, answer={answer[:300]}",
    )

    # ── Test 15: Cross-session delete is blocked ──────────────────────
    if doc_a_id:
        resp = delete_document(session_b, doc_a_id)
        record(
            "15. Session B cannot delete session A's document (expect 404)",
            resp.status_code == 404,
            f"got {resp.status_code}: {resp.text[:300]}",
        )
    else:
        record("15. Cross-session delete is blocked", False, "skipped — no doc_a_id from test 3")

    # ── Test 16: Owning session CAN delete its own document ──────────
    if doc_a_id:
        resp = delete_document(session_a, doc_a_id)
        record(
            "16. Session A can delete its own document",
            resp.status_code == 200,
            f"got {resp.status_code}: {resp.text[:300]}",
        )
    else:
        record("16. Owning session can delete its own document", False, "skipped — no doc_a_id from test 3")

    # ── Cleanup ───────────────────────────────────────────────────────
    cleanup_session(session_a)
    cleanup_session(session_b)

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"RESULTS: {passed}/{total} passed")
    if passed < total:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}\n    {detail}")
        sys.exit(1)
    else:
        print("All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()