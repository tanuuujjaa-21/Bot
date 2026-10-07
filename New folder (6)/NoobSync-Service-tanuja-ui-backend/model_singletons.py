"""
model_singletons.py
Shared, single-instance embedding model and LLM client.

Why this file exists:
Previously rag_pipeline.py and router.py each created their own
HuggingFaceEmbeddings and OllamaLLM instances. That means the ~90MB
MiniLM transformer was loaded into memory twice, and two separate
Ollama HTTP clients were opened, at startup. Import from here instead
so the whole app shares one of each.

Also centralizes the LLM model choice and an optional Groq fallback,
so swapping models for a demo is a one-line env var change instead of
a code change in two files.
"""

import os
import logging

logger = logging.getLogger("noobsync.knowledgebot")

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM

# ── Config (env-overridable) ──────────────────────────────────────────────
# Set OLLAMA_MODEL in your .env to try a smaller/quantized tag, e.g.:
#   OLLAMA_MODEL=llama3.1:8b-instruct-q4_K_M
# Run `ollama list` after `ollama pull <tag>` to confirm the exact tag name
# available for your platform before setting this.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# ── Singleton embedding model — loaded once for the whole process ─────────
logger.info("Loading shared embedding model: %s", EMBEDDING_MODEL)
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

# ── Singleton primary LLM (Ollama, local) ──────────────────────────────────
from langchain_groq import ChatGroq

logger.info("Loading shared Groq LLM: %s", GROQ_MODEL)

llm = ChatGroq(
    model=GROQ_MODEL,
    api_key=GROQ_API_KEY,
    streaming=True
)

# ── Optional Groq fallback ─────────────────────────────────────────────────
# Only activates if GROQ_API_KEY is set in the environment (.env / Streamlit
# secret). If Ollama is unreachable or times out, calls fall back to Groq
# automatically instead of the request failing.
_groq_llm = None
if GROQ_API_KEY:
    try:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY)
        logger.info("Groq fallback enabled (model: %s)", GROQ_MODEL)
        print("Groq client initialized")
    except ImportError:
        logger.warning(
            "GROQ_API_KEY is set but langchain-groq is not installed. "
            "Run: pip install langchain-groq"
        )
else:
    logger.info("No GROQ_API_KEY set — Groq fallback disabled, Ollama-only.")


class _LLMWithFallback:
    """Drop-in replacement for llm.invoke() that falls back to Groq
    if the local Ollama call fails (connection error, timeout, etc.)."""

    def invoke(self, prompt: str) -> str:
        try:
            return llm.invoke(prompt)
        except Exception as exc:
            if _groq_llm is None:
                raise
            logger.warning("Ollama call failed (%s) — falling back to Groq", exc)
            result = _groq_llm.invoke(prompt)
            # ChatGroq returns a message object; OllamaLLM returns a str.
            # Normalize so callers always get a plain string.
            return getattr(result, "content", result)


# Use this everywhere instead of calling `llm.invoke()` directly.
llm_with_fallback = _LLMWithFallback()