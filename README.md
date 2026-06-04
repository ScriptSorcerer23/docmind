# DocMind

> Agent-native document intelligence powered by MCP + CrewAI

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite) |
| Backend | FastAPI (Python) |
| Vector DB | Supabase pgvector |
| Chunking & Embedding | LangChain + OpenAI `text-embedding-3-small` |
| Agent Orchestration | CrewAI |
| MCP Layer | MCP Python SDK (SSE transport) |
| MCP-CrewAI Bridge | `crewai-tools` MCPServerAdapter |

## Architecture

```
Upload (React) → FastAPI → LangChain chunk + embed → Supabase pgvector
Chat (React)   → FastAPI → CrewAI Agent → MCP retrieve_documents tool → pgvector similarity search → cited answer
```

## Getting Started

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_URL
npm run dev
```

### Database

Run `backend/migrations/001_initial.sql` in the Supabase SQL Editor.

## License

MIT
