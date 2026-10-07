# NoobSync KnowledgeBot

Customer chat for NoobSync's knowledge base. React frontend, FastAPI backend, Anushka's RAG pipeline and Akshada's security layer.

```
frontend/    React + Vite + TypeScript + Tailwind        (Tanuja)
backend/     FastAPI: sign-in, chat history, uploads      (Tanuja)
rag/         RAG pipeline, analytics, scraper             (Anushka, unchanged)
security/    input validation, prompt guard, Zoho module  (Akshada, unchanged)
model_singletons.py                                       (Anushka, unchanged)
```

## What a visitor sees

1. **Entry screen.** Name and phone number are required before the chat opens.
2. **Chat.** Ask questions; answers come from the visitor's own uploaded files first, then NoobSync's built-in knowledge base. If neither has the answer the bot says so.
3. **Chat history.** Every conversation is saved and listed in the left sidebar (Today, Yesterday, ...). Open one to continue it, delete it, or start a new chat.
4. **Documents.** The right panel takes PDF, Word (.docx), Text, Markdown and CSV files. Drop several at once, or use the per-type buttons. Each file shows Reading / Ready / error status and can be removed.

On a phone the history and documents panels open as slide-over drawers.

## Run it

Python 3.10 or newer, Node 18 or newer.

### Backend (from the project root)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then put your GROQ_API_KEY in it
uvicorn backend.app:app --reload --port 8000
```

Run it from the project root: Anushka's pipeline stores its index in `./chroma_db` relative to where the server starts.

`model_singletons.py` sets `HF_HUB_OFFLINE=1`, so the embedding model (`all-MiniLM-L6-v2`) must already be downloaded. On a first run, start once with `HF_HUB_OFFLINE=0` and `TRANSFORMERS_OFFLINE=0` set in your shell.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to the backend on :8000
```

Production: `npm run build`, serve `frontend/dist`, set `VITE_API_URL` to the backend's public URL and `CORS_ORIGINS` on the backend to the site's origin.

## How sign-in works

The phone number is **not verified** (there is no OTP), so it is treated as contact information, not proof of identity. Each sign-in creates its own profile and a random session token kept in that browser (30 days). Chats and documents belong to that profile. This means typing someone else's number can never open their history; the trade-off is that clearing browser storage or switching device starts a fresh profile.

If the Zoho variables in `.env.example` are filled in, a first-time number is also sent to Zoho through Akshada's `security/zoho_crm.py`. Without them nothing is sent.

## API

All routes except register and health need `Authorization: Bearer <token>`. Errors are always `{"error": "..."}`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | `{name, phone}` returns `{token, user}` |
| GET | `/api/auth/me` | current user |
| POST | `/api/auth/logout` | revoke the token |
| GET / POST | `/api/conversations` | list (only chats with messages) / create |
| GET / DELETE | `/api/conversations/{id}` | messages / delete |
| POST | `/api/conversations/{id}/ask` | `{question}` returns the saved question and answer |
| GET / POST | `/api/documents` | list / upload (multipart, field `files`, many allowed) |
| DELETE | `/api/documents/{id}` | remove a document |
| GET | `/api/health` | readiness flags |

Every conversation and document is checked against the signed-in user, so one visitor can never read another's data.

## How answers are produced

`backend/router.py` embeds the question once, then tries, in order:

1. the visitor's own documents (a private Chroma collection per user, rebuilt from the saved text after a restart),
2. the global knowledge base through `rag/rag_pipeline.py`,
3. a plain "I couldn't find that" answer.

Questions pass through `security/input_validation.py` (3 to 500 characters, dangerous characters stripped), prompts are built by `security/prompt_guard.py`, and model failures become friendly messages through `security/error_handling.py`. Each answer is also logged through Anushka's `analytics_backend` and `unanswered_query_tracker` into `data/`.

Source files, confidence and timings are stored but **not shown to customers**. For testing, set `VITE_SHOW_SOURCES=true` in `frontend/.env`.

## Known issue in `rag/rag_pipeline.py` (Anushka's file)

In `answer_question()`, lines 116 to 120 (`log_unanswered_query(...)` through the `return (...)`) are not indented under `if not docs:`. Python raises `IndentationError` and the module cannot be imported.

The backend deliberately survives this: the server starts, the visitor's uploaded documents work, and the log says `Global knowledge base unavailable`. Until the file is fixed, the built-in NoobSync knowledge base will not answer. The fix is to indent those five lines by four spaces. Her line 141 also calls `log_query(question, answer, response_time)` with the wrong arguments; this backend never calls `answer_question()`, so it is not affected, but it will record wrong data if anything else does.

## Limits (all configurable in `.env`)

15 MB per file, 10 files per upload, 20 documents per user, 10 sign-ins per 10 minutes per IP. Questions are answered one at a time; earlier messages in a chat are not fed back to the model, so a follow-up like "and its price?" needs the subject restated.
