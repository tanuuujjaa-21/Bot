"""
app.py
FastAPI backend for the NoobSync KnowledgeBot.

Run from the project root:
    uvicorn backend.app:app --reload --port 8000

Layers
    rag/        Anushka  — RAG pipeline (unchanged)
    security/   Akshada  — input validation, prompt guard, error handling (unchanged)
    backend/    Tanuja   — API, sign-in, chat history, document uploads
"""

import asyncio
import json
import logging
import os
import sys
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

warnings.filterwarnings("ignore", message=".*SentenceTransformerEmbeddings.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*HuggingFaceEmbeddings.*", category=DeprecationWarning)

# ── Import paths ──────────────────────────────────────────────────────────
# Anushka's modules import each other by bare name (e.g. `from analytics_backend
# import ...`), so rag/ must be importable directly. model_singletons.py lives at
# the project root. Her analytics DBs default to the working directory, so point
# them at data/ before anything imports them.
ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "rag"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from backend.config import (  # noqa: E402
    CORS_ORIGINS, DATA_DIR, DOCS_DIR, MAX_DOCS_PER_USER, MAX_FILES_PER_REQUEST,
    MAX_UPLOAD_BYTES, MAX_UPLOAD_MB,
)

os.environ.setdefault("ANALYTICS_DB", str(DATA_DIR / "analytics.db"))
os.environ.setdefault("UNANSWERED_QUERY_DB", str(DATA_DIR / "unanswered_queries.db"))

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from backend import auth, crm, db, router  # noqa: E402
from backend.documents import DocumentError, check_extension, display_name, extract_text  # noqa: E402
from security.error_handling import FriendlyError, safe_call  # noqa: E402
from security.input_validation import ValidationError, validate_question  # noqa: E402

logger = logging.getLogger("noobsync.knowledgebot")
logging.basicConfig(level=logging.INFO)

DEFAULT_DOC = str(ROOT / "rag" / "NoobSync_Services.txt")
_executor = ThreadPoolExecutor(max_workers=4)

# Anushka's logging helpers. They must never be able to break a chat answer.
try:
    from analytics_backend import init_analytics_db, log_query
    from unanswered_query_tracker import init_db as init_unanswered_db
    from unanswered_query_tracker import log_unanswered_query
    _analytics_ok = True
except Exception as exc:  # pragma: no cover
    logger.warning("Analytics modules unavailable (%s); continuing without them.", exc)
    _analytics_ok = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if _analytics_ok:
        try:
            init_analytics_db()
            init_unanswered_db()
        except Exception as exc:
            logger.warning("Could not initialise analytics databases: %s", exc)
    # Model loading + default knowledge base ingestion can take a while; do it
    # in the background so the API (and sign-in screen) is available at once.
    threading.Thread(target=router.warm_up, args=(DEFAULT_DOC,), daemon=True).start()
    yield


app = FastAPI(title="NoobSync KnowledgeBot", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Reject oversized uploads before the body is parsed."""
    if request.method == "POST" and request.url.path == "/api/documents":
        declared = request.headers.get("content-length")
        cap = MAX_UPLOAD_BYTES * MAX_FILES_PER_REQUEST + 1024 * 1024
        if declared and declared.isdigit() and int(declared) > cap:
            return JSONResponse(
                status_code=413,
                content={"error": f"Upload too large. Each file can be up to {MAX_UPLOAD_MB} MB."},
            )
    return await call_next(request)


# ── Error shape: always {"error": "..."} so the frontend has one thing to read ──
@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "That request wasn't valid. Please check it and try again."})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Something went wrong. Please try again."})


# ── Health ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "NoobSync KnowledgeBot backend is running"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models_ready": router.status["models_ready"],
        "global_kb_ready": router.status["global_kb_ready"],
    }


# ── Auth ───────────────────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    name: str = Field(..., max_length=200)
    phone: str = Field(..., max_length=40)


@app.post("/api/auth/register")
def register(body: RegisterBody, request: Request):
    auth.check_register_rate(auth.client_ip(request))
    try:
        name = auth.clean_name(body.name)
        phone = auth.clean_phone(body.phone)
    except auth.RegistrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    first_time = not db.phone_seen_before(phone)
    user = db.create_user(name, phone)
    token = auth.issue_token(user["id"])
    if first_time:
        crm.capture_lead_in_background(name, phone)  # no-op unless Zoho is configured
    return {"token": token, "user": user}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.current_user)):
    return {"user": user}


@app.post("/api/auth/logout")
def logout(token: str = Depends(auth.current_token), user: dict = Depends(auth.current_user)):
    auth.revoke_token(token)
    return {"ok": True}


# ── Conversations (chat history) ───────────────────────────────────────────
def _public_message(row: dict) -> dict:
    source = None
    if row.get("source"):
        try:
            source = json.loads(row["source"])
        except (TypeError, ValueError):
            source = None
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "source": source,
        "latency_ms": row.get("latency_ms"),
        "created_at": row["created_at"],
    }


def _owned_conversation(user: dict, conversation_id: str) -> dict:
    conv = db.get_conversation(user["id"], conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    return conv


@app.get("/api/conversations")
def list_conversations(user: dict = Depends(auth.current_user)):
    return {"conversations": db.list_conversations(user["id"])}


@app.post("/api/conversations")
def create_conversation(user: dict = Depends(auth.current_user)):
    return {"conversation": db.create_conversation(user["id"])}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: dict = Depends(auth.current_user)):
    conv = _owned_conversation(user, conversation_id)
    return {
        "conversation": conv,
        "messages": [_public_message(m) for m in db.list_messages(conversation_id)],
    }


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: dict = Depends(auth.current_user)):
    if not db.delete_conversation(user["id"], conversation_id):
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    return {"ok": True}


class AskBody(BaseModel):
    question: str = Field(..., max_length=2000)


@app.post("/api/conversations/{conversation_id}/ask")
async def ask(conversation_id: str, body: AskBody, user: dict = Depends(auth.current_user)):
    _owned_conversation(user, conversation_id)

    try:
        question = validate_question(body.question)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ready_docs = [d for d in db.list_documents(user["id"]) if d["status"] == "ready"]

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            lambda: safe_call(router.route_question, user["id"], question, ready_docs),
        )
    except FriendlyError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    source = json.dumps({"type": result["source"], "files": result["files"]})
    user_msg, bot_msg = db.add_exchange(
        conversation_id, question, result["answer"], source,
        result["latency_ms"], title_if_new=question[:48],
    )

    if _analytics_ok:
        try:
            log_query(
                question=question,
                duration_ms=result["latency_ms"],
                model_used="groq",
                confidence_score=result["confidence"],
                answered=result["answered"],
                source_url=", ".join(result["files"]) or result["source"],
                session_id=conversation_id,
            )
            if not result["answered"]:
                log_unanswered_query(
                    question, confidence_score=result["confidence"],
                    session_id=conversation_id, channel="web",
                )
        except Exception as exc:
            logger.warning("Analytics logging failed: %s", exc)

    return {
        "user_message": _public_message(user_msg),
        "assistant_message": _public_message(bot_msg),
        "conversation_title": db.get_conversation(user["id"], conversation_id)["title"],
    }


# ── Documents (multi-file uploader) ────────────────────────────────────────
def _public_doc(d: dict) -> dict:
    return {k: d[k] for k in
            ("id", "filename", "ext", "size_bytes", "chunk_count", "status", "error", "created_at")}


def _ingest_job(user_id: int, doc_id: str) -> None:
    """Chunk + embed one document into the user's collection (background)."""
    try:
        doc = db.get_document(user_id, doc_id)
        if not doc:
            return
        others = [d for d in db.list_documents(user_id) if d["status"] == "ready"]
        chunks = router.ingest_user_document(user_id, doc, others)
        if db.get_document(user_id, doc_id) is None:  # removed while processing
            router.remove_user_document(user_id, doc_id)
            return
        db.set_document_status(doc_id, "ready", chunk_count=chunks)
    except Exception as exc:
        logger.exception("[ingest][user %s] %s failed: %s", user_id, doc_id, exc)
        db.set_document_status(
            doc_id, "error", error="This file could not be processed. Remove it and try again."
        )


@app.get("/api/documents")
def list_documents(user: dict = Depends(auth.current_user)):
    return {
        "documents": [_public_doc(d) for d in db.list_documents(user["id"])],
        "limits": {
            "max_file_mb": MAX_UPLOAD_MB,
            "max_documents": MAX_DOCS_PER_USER,
            "max_files_per_upload": MAX_FILES_PER_REQUEST,
        },
    }


@app.post("/api/documents")
async def upload_documents(
    files: list[UploadFile] = File(...),
    user: dict = Depends(auth.current_user),
):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Upload up to {MAX_FILES_PER_REQUEST} files at a time.",
        )

    loop = asyncio.get_running_loop()
    user_id = user["id"]
    held = db.count_documents(user_id)
    accepted, rejected = [], []

    for upload in files:
        name = display_name(upload.filename or "")
        try:
            ext = check_extension(name)
            if held + len(accepted) >= MAX_DOCS_PER_USER:
                raise DocumentError(
                    f"You can keep up to {MAX_DOCS_PER_USER} documents. Remove one to add more."
                )
            data = await upload.read(MAX_UPLOAD_BYTES + 1)
            if not data:
                raise DocumentError("This file is empty.")
            if len(data) > MAX_UPLOAD_BYTES:
                raise DocumentError(f"This file is larger than {MAX_UPLOAD_MB} MB.")
            text = await loop.run_in_executor(_executor, extract_text, name, data)
        except DocumentError as e:
            rejected.append({"filename": name, "error": str(e)})
            continue
        except Exception as exc:
            logger.exception("[upload][user %s] %s: %s", user_id, name, exc)
            rejected.append({"filename": name, "error": "This file could not be read."})
            continue
        finally:
            await upload.close()

        doc_id = db.new_id()
        user_dir = DOCS_DIR / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        text_path = user_dir / f"{doc_id}.txt"
        text_path.write_text(text, encoding="utf-8")

        doc = db.add_document(doc_id, user_id, name, ext, len(data), str(text_path))
        accepted.append(_public_doc(doc))
        loop.run_in_executor(_executor, _ingest_job, user_id, doc_id)

    return {"documents": accepted, "rejected": rejected}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(auth.current_user)):
    doc = db.delete_document(user["id"], doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="That document no longer exists.")
    try:
        Path(doc["text_path"]).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete %s", doc["text_path"])
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, router.remove_user_document, user["id"], doc_id)
    return {"ok": True}
