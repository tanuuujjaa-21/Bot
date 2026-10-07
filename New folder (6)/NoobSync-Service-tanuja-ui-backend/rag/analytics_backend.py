"""
analytics_backend.py

NoobSync Knowledge Base AI — Week 5, Task 2 (real data layer)
Owner: Akshada

WHAT THIS DOES
--------------
Replaces the AdminDashboard.jsx mock data with real numbers. Two parts:

1. Logging — call log_query() every time the bot answers something (from
   the main RAG query path — likely Anushka's code, or wherever the
   FastAPI /ask endpoint lives). This is the same "every query logged
   with response time" requirement from the Performance SLA doc.

2. Serving — a FastAPI router exposing GET /admin/analytics/summary,
   which aggregates everything AdminDashboard.jsx needs, in the EXACT
   same shape as the mock data it currently ships with — so swapping
   the frontend from mock to real is a one-line fetch() change, not a
   rewrite.

HOW TO WIRE THIS INTO THE EXISTING FASTAPI APP
-------------------------------------------------
In backend/app.py (or wherever the main FastAPI app is created):

    from analytics_backend import analytics_router, log_query, log_lead_captured

    app.include_router(analytics_router)

Then in the main /ask endpoint, after generating a response:

    log_query(
        question=user_question,
        duration_ms=response_time_ms,
        model_used="groq-llama3.1-8b" or "ollama",
        confidence_score=confidence,       # from retrieval similarity
        answered=(confidence_score >= CONFIDENCE_THRESHOLD),
        source_url=top_matching_source,
        session_id=session_id,
    )

And wherever a lead gets created (after zoho_crm.create_lead() succeeds):

    log_lead_captured(session_id=session_id)

That's the entire integration surface.

NOTE ON UNANSWERED QUERIES: this module logs EVERY query (answered or
not) for the dashboard's overview stats. unanswered_query_tracker.py
(built earlier) specifically handles the "documentation gap" tracking —
call BOTH functions when a query is unanswered, they serve different
purposes (this one = dashboard stats, that one = weekly gap report).
"""

import sqlite3
import os
from datetime import datetime, timedelta, timezone
from collections import Counter
from fastapi import APIRouter

DB_PATH = os.environ.get("ANALYTICS_DB", "analytics.db")

analytics_router = APIRouter(prefix="/admin/analytics", tags=["analytics"])


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_analytics_db():
    """Creates tables if they don't exist. Safe to call every app startup."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            duration_ms REAL,
            model_used TEXT,
            confidence_score REAL,
            answered INTEGER,
            source_url TEXT,
            session_id TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def log_query(question, duration_ms, model_used=None, confidence_score=None,
              answered=True, source_url=None, session_id=None):
    """Call this on every single bot response — this is the SLA logging requirement."""
    conn = _get_connection()
    conn.execute(
        """INSERT INTO query_log
           (question, duration_ms, model_used, confidence_score, answered,
            source_url, session_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (question, duration_ms, model_used, confidence_score, int(answered),
         source_url, session_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def log_lead_captured(session_id=None):
    """Call this whenever zoho_crm.create_lead() succeeds."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO lead_log (session_id, timestamp) VALUES (?, ?)",
        (session_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    idx = min(int(len(sorted_values) * pct), len(sorted_values) - 1)
    return sorted_values[idx]


def get_summary(days=7):
    """
    Returns the exact shape AdminDashboard.jsx's mock data uses, so the
    frontend swap is a one-line change.
    """
    conn = _get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    query_rows = conn.execute(
        "SELECT * FROM query_log WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,)
    ).fetchall()
    lead_rows = conn.execute(
        "SELECT * FROM lead_log WHERE timestamp >= ?", (cutoff,)
    ).fetchall()
    conn.close()

    total = len(query_rows)
    answered = sum(1 for r in query_rows if r["answered"])
    unanswered = total - answered

    durations = sorted([r["duration_ms"] for r in query_rows if r["duration_ms"] is not None])
    avg_ms = round(sum(durations) / len(durations)) if durations else 0
    p95_ms = round(_percentile(durations, 0.95)) if durations else 0

    question_counts = Counter(r["question"] for r in query_rows)
    top_questions = [{"question": q, "count": c} for q, c in question_counts.most_common(10)]

    source_counts = Counter(r["source_url"] for r in query_rows if r["source_url"])
    top_sources = [{"name": s, "queries": c} for s, c in source_counts.most_common(10)]

    return {
        "summary": {
            "totalConversations": total,
            "answered": answered,
            "unanswered": unanswered,
            "avgResponseMs": avg_ms,
            "p95ResponseMs": p95_ms,
            "leadsCapture": len(lead_rows),
        },
        "topQuestions": top_questions,
        "topSources": top_sources,
    }


@analytics_router.get("/summary")
def analytics_summary(days: int = 7):
    """GET /admin/analytics/summary?days=7 — the endpoint the dashboard calls."""
    return get_summary(days=days)


# ==========================================================================
# SELF-TEST — proves logging + aggregation + the actual HTTP endpoint work
# ==========================================================================
if __name__ == "__main__":
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    DB_PATH = "test_analytics.db"
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_analytics_db()

    sample = [
        ("What's your pricing?", 1800, "groq-llama3.1-8b", 0.82, True, "noobsync.com/pricing"),
        ("What's your pricing?", 2100, "groq-llama3.1-8b", 0.79, True, "noobsync.com/pricing"),
        ("Do you support Shopify?", 1500, "groq-llama3.1-8b", 0.88, True, "noobsync.com/shopify-guide"),
        ("Do you integrate with Salesforce?", 2900, "groq-llama3.1-8b", 0.21, False, None),
        ("How long does setup take?", 1700, "groq-llama3.1-8b", 0.75, True, "Services_Overview.pdf"),
    ]
    for question, ms, model, conf, answered, source in sample:
        log_query(question, ms, model, conf, answered, source, session_id="test-session")

    log_lead_captured(session_id="test-session")
    log_lead_captured(session_id="test-session-2")

    app = FastAPI()
    app.include_router(analytics_router)
    client = TestClient(app)

    resp = client.get("/admin/analytics/summary")
    print("=" * 60)
    print("ANALYTICS BACKEND — SELF TEST")
    print("=" * 60)
    print("HTTP status:", resp.status_code)
    data = resp.json()
    print(data)
    print()

    assert resp.status_code == 200
    assert data["summary"]["totalConversations"] == 5
    assert data["summary"]["answered"] == 4
    assert data["summary"]["unanswered"] == 1
    assert data["summary"]["leadsCapture"] == 2
    assert data["topQuestions"][0]["question"] == "What's your pricing?"
    assert data["topQuestions"][0]["count"] == 2
    print("ALL ASSERTIONS PASSED")

    os.remove(DB_PATH)