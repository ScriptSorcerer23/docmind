# DocMind

**Live Deployment:** https://docmind1.netlify.app/

DocMind is a real-time, agentic Retrieval-Augmented Generation (RAG) platform. Rather than relying on a standard single-pass retrieval pipeline, DocMind executes a bounded autonomous loop that dynamically selects and executes tools based on user queries, streaming its execution state to the client in real time.

---

## Architecture & Core Systems

* **Bounded Agentic Loop:** The core engine is a custom autonomous loop (max 5 iterations) powered by `gpt-oss-20b` via Groq. 
* **Real-Time Telemetry:** Tool executions and intermediate results are streamed to the React client via Server-Sent Events (SSE) using `fetch` and `ReadableStream`. No black-box buffering.
* **Strict Session Isolation:** Fully stateless architecture. A `session_id` is generated client-side, injected via the `X-Session-Id` header, and securely scoped into every Supabase DB query. Identifiers never bleed into streamed events.
* **Concurrency & Rate Limit Handling:** Implements a Postgres trigger (`enforce_session_document_cap`) to close race conditions on the 3-document upload limit, paired with idempotent ingestion (hash-based) and exponential backoff wrappers (2s/4s/8s) for LLM rate limits.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + Vite (Deployed on Netlify) |
| **Backend** | FastAPI / Python 3.11 (Deployed on Render) |
| **LLM Inference** | `openai/gpt-oss-20b` via Groq (`litellm`) |
| **Embeddings** | Google `gemini-embedding-2` (768-dim) |
| **Vector DB** | Supabase `pgvector` (Cosine Similarity Search) |

---

## Tooling & Capabilities

The agent has autonomous access to the following callable tools:
1. `retrieve_documents`: Semantic vector search over ingested chunks.
2. `list_available_documents`: Contextual awareness of the current session's state.
3. `summarize_document`: Full-text document synthesis.
4. `compare_documents`: Cross-document analysis and routing.

---

## Local Environment Setup

### Prerequisites
* Python 3.11+ & Node.js 18+
* Supabase instance (with `pgvector` enabled)
* Groq API Key & Google API Key (for embeddings)


### Backend Pipeline
```bash
cd backend
cp .env.example .env 
# Configure SUPABASE_URL, SUPABASE_SERVICE_KEY, GROQ_API_KEY, GOOGLE_API_KEY

pip install -r requirements.txt
uvicorn main:app --reload

```

### Frontend Client

```bash
cd frontend
cp .env.example .env 
# Set VITE_API_URL=http://localhost:8000

npm install
npm run dev

```

---

## API Reference

| Method | Endpoint | Function |
| --- | --- | --- |
| `GET` | `/health` | System health check |
| `POST` | `/upload` | Ingest PDF/TXT (Requires `X-Session-Id`) |
| `GET` | `/documents` | List session-scoped documents |
| `DELETE` | `/documents/{id}` | Purge document from session |
| `POST` | `/chat` | Standard synchronous agent chat |
| `POST` | `/chat/stream` | SSE streaming endpoint |

*Note: The Render deployment utilizes the `X-Accel-Buffering: no` header on `/chat/stream` to prevent proxy buffering of SSE chunks.*

---
