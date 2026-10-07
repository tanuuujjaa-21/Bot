"""
router.py
Hybrid routing between a user's own uploaded documents and the shared
NoobSync knowledge base (Anushka's rag/rag_pipeline.py).

Order for every question:
  A. the signed-in user's uploaded documents (all of their files at once)
  B. the global NoobSync knowledge base
  C. a clear "I couldn't find that" answer — never a guess

Design notes
  * Each user gets their OWN Chroma collection (user_<id>). Chroma's
    in-memory client shares one process-wide system, so a default collection
    name would let different users' documents mix. Never drop the name.
  * Only extracted text is stored on disk. If the server restarts, a user's
    collection is rebuilt lazily from that text on their next question, so
    uploaded documents survive restarts.
  * Models are loaded lazily so the API can start (and report a clear
    status) even if the embedding model or GROQ_API_KEY is not ready yet.
"""

import functools
import logging
import os
import threading
import time
from collections import OrderedDict, defaultdict
from pathlib import Path

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from security.prompt_guard import build_safe_prompt, contains_injection_attempt

logger = logging.getLogger("noobsync.knowledgebot")

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.30"))
TOP_K = 3
MAX_USER_STORES = 50          # in-memory collections kept at once (LRU)
STORE_TTL_SECONDS = 60 * 60   # idle collections are dropped after this

NOT_FOUND_ANSWER = (
    "I couldn't find that in the available documents. "
    "Try rephrasing, upload a document that covers it, or contact our team directly."
)

# ── Lazy model loading ──────────────────────────────────────────────────────
_models = None
_models_lock = threading.Lock()


def get_models():
    """(embeddings, llm) from model_singletons.py, loaded on first use."""
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                from model_singletons import embeddings, llm_with_fallback

                _models = (embeddings, llm_with_fallback)
    return _models


@functools.lru_cache(maxsize=128)
def _embed_question(question: str):
    return get_models()[0].embed_query(question)


# ── Status shown by /api/health ─────────────────────────────────────────────
status = {"models_ready": False, "global_kb_ready": False, "problems": []}
_rag_pipeline = None


def warm_up(default_doc: str) -> None:
    """Runs in a background thread at startup: loads the models and ingests
    the default NoobSync knowledge base through Anushka's ingest_document()."""
    global _rag_pipeline
    try:
        get_models()
        status["models_ready"] = True
    except Exception as exc:
        logger.exception("Could not load embedding/LLM models")
        status["problems"].append(
            f"Models failed to load ({type(exc).__name__}). "
            "Check GROQ_API_KEY in .env and that the embedding model is downloaded."
        )

    if not Path(default_doc).exists():
        status["problems"].append(f"Default knowledge base file not found: {default_doc}")
        return
    try:
        from rag import rag_pipeline

        rag_pipeline.ingest_document(default_doc)
        _rag_pipeline = rag_pipeline
        status["global_kb_ready"] = True
        logger.info("Global knowledge base ready: %s", default_doc)
    except Exception as exc:  # includes SyntaxError/IndentationError in rag_pipeline.py
        logger.exception("Global knowledge base unavailable")
        status["problems"].append(
            f"Global knowledge base unavailable ({type(exc).__name__}: {exc}). "
            "Uploaded documents still work."
        )


# ── Per-user vector stores ──────────────────────────────────────────────────
_stores: "OrderedDict[int, dict]" = OrderedDict()
_registry_lock = threading.Lock()
_user_locks: "defaultdict[int, threading.RLock]" = defaultdict(threading.RLock)


def _lock(user_id: int) -> threading.RLock:
    with _registry_lock:
        return _user_locks[user_id]


def _collection_name(user_id: int) -> str:
    return f"user_{int(user_id)}"


def _new_store(user_id: int) -> Chroma:
    embeddings = get_models()[0]
    vs = Chroma(collection_name=_collection_name(user_id), embedding_function=embeddings)
    vs.delete_collection()  # guarantee an empty collection, then recreate it
    return Chroma(collection_name=_collection_name(user_id), embedding_function=embeddings)


def _add_to_store(vs: Chroma, doc: dict) -> int:
    text = Path(doc["text_path"]).read_text(encoding="utf-8")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents(
        [text], metadatas=[{"doc_id": doc["id"], "source": doc["filename"]}]
    )
    if chunks:
        vs.add_documents(chunks)
    return len(chunks)


def _evict_stale() -> None:
    now = time.time()
    with _registry_lock:
        stale = [uid for uid, e in _stores.items() if now - e["last_used"] > STORE_TTL_SECONDS]
        while len(_stores) - len(stale) > MAX_USER_STORES:
            oldest = next(uid for uid in _stores if uid not in stale)
            stale.append(oldest)
        for uid in stale:
            entry = _stores.pop(uid, None)
            if entry:
                try:
                    entry["vs"].delete_collection()
                except Exception:
                    pass


def _ensure_store(user_id: int, ready_docs: list[dict]) -> dict:
    """Caller must hold the user's lock. Rebuilds from disk if not in memory."""
    entry = _stores.get(user_id)
    if entry is None:
        _evict_stale()
        vs = _new_store(user_id)
        for d in ready_docs:
            _add_to_store(vs, d)
        entry = {"vs": vs, "doc_ids": {d["id"] for d in ready_docs}, "last_used": time.time()}
        with _registry_lock:
            _stores[user_id] = entry
    entry["last_used"] = time.time()
    with _registry_lock:
        _stores.move_to_end(user_id)
    return entry


def ingest_user_document(user_id: int, doc: dict, other_ready_docs: list[dict]) -> int:
    """Adds one extracted document to the user's collection. Returns chunk count."""
    with _lock(user_id):
        entry = _ensure_store(user_id, [d for d in other_ready_docs if d["id"] != doc["id"]])
        if doc["id"] in entry["doc_ids"]:
            return 0
        count = _add_to_store(entry["vs"], doc)
        entry["doc_ids"].add(doc["id"])
        return count


def remove_user_document(user_id: int, doc_id: str) -> None:
    with _lock(user_id):
        entry = _stores.get(user_id)
        if not entry:
            return  # nothing in memory; the next rebuild reads from the DB
        ids = entry["vs"].get(where={"doc_id": doc_id}).get("ids", [])
        if ids:
            entry["vs"].delete(ids=ids)
        entry["doc_ids"].discard(doc_id)


def drop_user_store(user_id: int) -> None:
    with _lock(user_id):
        entry = _stores.pop(user_id, None)
        if entry:
            try:
                entry["vs"].delete_collection()
            except Exception:
                pass


# ── Answering ───────────────────────────────────────────────────────────────
def _generate(question: str, context: str) -> str:
    llm = get_models()[1]
    raw = llm.invoke(build_safe_prompt(question, context))
    return str(getattr(raw, "content", raw)).strip()


def _hits(results) -> list:
    return [(doc, score) for doc, score in results if score >= CONFIDENCE_THRESHOLD]


def route_question(user_id: int, question: str, ready_docs: list[dict]) -> dict:
    """
    Returns {answer, source, files, confidence, answered, latency_ms}
      source: "uploaded_document" | "rag_pipeline" | "none"
    """
    t0 = time.perf_counter()
    if contains_injection_attempt(question):
        logger.warning("[route][user %s] Possible prompt injection attempt: %r", user_id, question)

    question_embedding = _embed_question(question)
    best = 0.0

    # Path A — the user's own documents
    if ready_docs:
        with _lock(user_id):
            vs = _ensure_store(user_id, ready_docs)["vs"]
        results = vs.similarity_search_by_vector_with_relevance_scores(question_embedding, k=TOP_K)
        if results:
            best = max(best, max(s for _, s in results))
        hits = _hits(results)
        if hits:
            files = list(dict.fromkeys(d.metadata.get("source", "") for d, _ in hits))
            answer = _generate(question, "\n\n".join(d.page_content for d, _ in hits))
            return _result(answer, "uploaded_document", files, best, True, t0)

    # Path B — the shared NoobSync knowledge base (Anushka's pipeline)
    retriever = getattr(_rag_pipeline, "retriever", None) if _rag_pipeline else None
    if retriever is not None:
        results = retriever.vectorstore.similarity_search_by_vector_with_relevance_scores(
            question_embedding, k=TOP_K
        )
        if results:
            best = max(best, max(s for _, s in results))
        hits = _hits(results)
        if hits:
            answer = _generate(question, "\n\n".join(d.page_content for d, _ in hits))
            return _result(answer, "rag_pipeline", [], best, True, t0)

    # Path C — nothing relevant: say so instead of guessing
    return _result(NOT_FOUND_ANSWER, "none", [], best, False, t0)


def _result(answer, source, files, confidence, answered, t0) -> dict:
    return {
        "answer": answer,
        "source": source,
        "files": files,
        "confidence": round(float(confidence), 4),
        "answered": answered,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
