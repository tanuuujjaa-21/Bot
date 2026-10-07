"""
error_handling.py
Security layer — Akshada / akshada-security-docs branch

Wraps calls to the LLM / RAG pipeline so failures (Ollama not running,
Groq API down, timeout, empty index, etc.) return a friendly message
instead of leaking a stack trace to the user.

Usage in Tanuja's FastAPI endpoint, once /ask exists:

    from error_handling import safe_call, FriendlyError

    @app.post("/ask")
    def ask(payload: dict):
        try:
            clean_question = validate_question(payload.get("question", ""))
            answer = safe_call(answer_question, clean_question)
            return {"answer": answer}
        except FriendlyError as e:
            return {"error": str(e)}, e.status_code
"""

import logging

logger = logging.getLogger("noobsync.knowledgebot")


class FriendlyError(Exception):
    """A user-safe error message, paired with an HTTP-style status code."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


# Map internal failure types to friendly, non-technical messages.
# Extend this as new failure modes show up during testing.
_FRIENDLY_MESSAGES = {
    "connection": "The assistant is temporarily unavailable. Please try again in a moment.",
    "timeout": "That question took too long to answer. Try rephrasing it more simply.",
    "empty_index": "No documents have been loaded yet — please upload a document first.",
    "unknown": "Something went wrong while answering your question. Please try again.",
}


def _classify_error(exc: Exception) -> str:
    """Best-effort classification of an exception into a known failure type."""
    text = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    if "connect" in text or "refused" in text or "connection" in exc_type:
        return "connection"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "empty" in text or "no documents" in text or "no such collection" in text:
        return "empty_index"
    return "unknown"


def safe_call(func, *args, **kwargs):
    """
    Calls func(*args, **kwargs) and converts any exception into a
    FriendlyError with a safe message. Logs the real exception internally
    for debugging (never shown to the user).
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        logger.exception("Error during %s: %s", getattr(func, "__name__", "call"), exc)
        failure_type = _classify_error(exc)
        raise FriendlyError(_FRIENDLY_MESSAGES[failure_type]) from exc


if __name__ == "__main__":
    # Quick manual smoke test — run: python error_handling.py
    def flaky_llm_call(question):
        raise ConnectionError("Failed to connect to Ollama on localhost:11434")

    try:
        safe_call(flaky_llm_call, "What is ConnectOps?")
    except FriendlyError as e:
        print(f"User sees: {e}  (status {e.status_code})")
