# CodeLens 🔍

> AI-powered codebase Q&A with dual-mode RAG — paste a GitHub URL, ask questions, get answers with exact file + line citations.

---

## What It Does

- Ingests any public GitHub repository intelligently
- Answers **repo-specific questions** by searching the codebase with hybrid vector + keyword search
- Answers **general coding questions** by searching the web (Tavily, StackOverflow, GitHub)
- Returns answers grounded with file-level citations (`auth/middleware.py:L45–67`)
- Routes every query automatically — the user never has to specify

---

## Architecture

```
User Query
    │
    ▼
┌─────────────┐
│   Router    │  (LLM classifies: repo_specific vs general_coding)
└─────────────┘
    │              │
    ▼              ▼
Hybrid Search    Web Search
(Qdrant)        (Tavily + StackOverflow + GitHub)
    │              │
    └──────┬───────┘
           ▼
      Synthesizer
           │
           ▼
    Answer + Citations
```

---

## Key Design Decisions

### AST-Based Code Chunking
Code is chunked by **semantic boundaries** (function and class definitions) using Tree-sitter — not arbitrary token windows. Every chunk carries metadata: function name, class name, file path, start/end line, language.

Supported languages: Python · JavaScript · TypeScript · C#
Fallback (size-based): Markdown · JSON · config files

### Dual-Mode Retrieval
| Query Type | Retrieval Path |
|---|---|
| Repo-specific | Dense vector + BM25 hybrid search on Qdrant |
| General coding | Tavily + StackOverflow API + GitHub code search |

### Hybrid Search
Dense (semantic) + BM25 (keyword) retrieval combined and re-ranked before synthesis. Filtered by repo name in Qdrant payload to prevent session cross-contamination.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Agent | LangGraph |
| Vector DB | Qdrant Cloud |
| Embeddings | `voyage-code-2` / `text-embedding-3-small` |
| Code Parsing | Tree-sitter |
| LLM | Groq |
| Web Search | Tavily |
| UI | Chainlit |
| Deploy | Railway |

---

## API Endpoints

### `POST /ingest`
Ingest a public GitHub repository.

```json
{
  "repo_url": "https://github.com/fastapi/fastapi",
  "branch": "main"
}
```

**Response:**
```json
{
  "summary": "...",
  "files_indexed": 142,
  "chunks_created": 893
}
```

---

### `POST /query`
Ask a question about an ingested repo or a general coding question.

```json
{
  "question": "How does this project handle authentication?",
  "session_id": "abc123"
}
```

**Response:**
```json
{
  "answer": "...",
  "route": "repo_specific",
  "sources": [
    { "file": "auth/middleware.py", "lines": "45-67" }
  ]
}
```

---

## Production Controls

- **Rate limiting:** 10 requests/minute per IP (`slowapi`)
- **Request throttling:** Duplicate in-flight requests rejected per session
- **Circuit breaker:** Repos with >300 files or >50MB rejected with structured error
- **Ingest queue:** Same repo cannot be ingested simultaneously twice
- **Structured errors:**
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMITED",
  "retry_after": 60
}
```

---

## Setup

### Prerequisites
- Python 3.11+
- Qdrant Cloud account
- API keys: Groq, Tavily, Voyage (or OpenAI)

### Install

```bash
git clone https://github.com/yourusername/codelens
cd codelens
pip install -r requirements.txt
```

### Environment Variables

```env
GROQ_API_KEY=
TAVILY_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
VOYAGE_API_KEY=
```

### Run

```bash
uvicorn main:app --reload
```

### Deploy (Railway)

```bash
railway up
```

---

## Project Structure

```
codelens/
├── ingestor/
│   ├── github_ingestor.py     # GitHub API + file filtering
│   ├── ast_chunker.py         # Tree-sitter AST chunking
│   └── qdrant_indexer.py      # Embedding + Qdrant push
├── agent/
│   ├── router.py              # Query classification
│   ├── repo_search.py         # Hybrid search on Qdrant
│   ├── web_search.py          # Tavily + StackOverflow + GitHub
│   └── graph.py               # LangGraph state machine
├── api/
│   ├── main.py                # FastAPI app
│   ├── rate_limiter.py        # slowapi config
│   └── schemas.py             # Pydantic models
├── ui/
│   └── app.py                 # Chainlit UI
└── README.md
```

---

## License

MIT
