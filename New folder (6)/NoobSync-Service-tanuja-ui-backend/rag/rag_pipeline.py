import time
from analytics_backend import log_query, init_analytics_db
import os
import hashlib
import shutil
import logging
import sys
from pathlib import Path
from unanswered_query_tracker import init_db, log_unanswered_query

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_chroma import Chroma

# ``python rag_pipeline.py`` sets sys.path[0] to this ``rag`` directory.
# Add the service root so the shared model module can be imported in that
# direct-run mode as well as when this module is imported by the backend.
SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

# Shared, single-instance embedding model + LLM (see model_singletons.py).
# Do NOT instantiate HuggingFaceEmbeddings / OllamaLLM here again — that
# was loading the transformer weights and opening an Ollama client a
# second time on top of router.py's copies.
from model_singletons import embeddings, llm

# Global objects
retriever = None

CHROMA_DB = "chroma_db"
HASH_FILE = os.path.join(CHROMA_DB, "source_hash.txt")
logger = logging.getLogger(__name__)


def _file_hash(file_path: str) -> str:
    """SHA-256 of the file's contents, used to detect if the source
    document has changed since the last time it was ingested."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()

def ingest_document(file_path: str) -> None:
    global retriever

    new_hash = _file_hash(file_path)
    existing_hash = None
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            existing_hash = f.read().strip()

    # Reuse the persisted index ONLY if the source file is unchanged.
    if os.path.exists(CHROMA_DB) and existing_hash == new_hash:
        print("Source document unchanged — loading existing Chroma database...")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB,
            embedding_function=embeddings
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
        print("Existing vector database loaded.")
        return

    if os.path.exists(CHROMA_DB) and existing_hash != new_hash:
        print("Source document changed since last ingest — rebuilding index...")
        shutil.rmtree(CHROMA_DB)
    else:
        print("Creating embeddings for the first time...")

    loader = TextLoader(file_path, encoding="utf-8")
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(documents)

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    # Record the hash of what we just ingested so the next run can tell
    # whether the source file has changed.
    os.makedirs(CHROMA_DB, exist_ok=True)
    with open(HASH_FILE, "w") as f:
        f.write(new_hash)

    print("Document ingested successfully.")




def answer_question(question: str) -> str:
    global retriever

    start_time = time.time()

    if retriever is None:
        return "No document loaded."

    print("Retrieving documents...")
    docs = retriever.invoke(question)
    print(f"Found {len(docs)} document(s)")
    
    if not docs:
    log_unanswered_query(question)
    return (
        "I couldn't find the answer in the available documents. "
        "Please contact our team for more information."
    )

    context = "\n\n".join(
        doc.page_content
        for doc in docs[:3]
    )

    prompt = f"""
Use only the context below to answer.

Context:
{context}

Question:
{question}
"""

    answer = llm.invoke(prompt)

    response_time = time.time() - start_time

    log_query(question, answer, response_time)

    return answer


if __name__ == "__main__":

    ingest_document("NoobSync_Services.txt")

    while True:
        question = input("\nAsk: ")

        if question.lower() == "exit":
            break

        answer_question(question)