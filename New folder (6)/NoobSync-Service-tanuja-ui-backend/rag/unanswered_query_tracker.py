"""
unanswered_query_tracker.py

NoobSync Knowledge Base AI — Week 5, Task 2 (part 1 of 2)
Owner: Akshada

WHAT THIS DOES
--------------
Tracks every question the bot couldn't answer confidently — either it said
"I don't know" outright, or the retrieval confidence came back below
threshold. Stores each occurrence, then generates a weekly summary of
documentation gaps: "these questions were asked but not answered, consider
adding this content."

This feeds directly into the analytics dashboard (Sources/Unanswered tab)
and gives NoobSync's clients a concrete, actionable list of what's missing
from their knowledge base -- turning "the bot doesn't know everything" into
"here's exactly what to add next."

HOW THIS PLUGS INTO THE REST OF THE PIPELINE
----------------------------------------------
Whoever owns the RAG query path (Anushka) calls log_unanswered_query()
every time a response falls below the confidence threshold or the bot
explicitly says it doesn't know:

    from unanswered_query_tracker import log_unanswered_query

    if confidence_score < CONFIDENCE_THRESHOLD:
        log_unanswered_query(
            query=user_question,
            confidence_score=confidence_score,
            session_id=session_id,
            channel="web",  # or "whatsapp"
            source_url=current_source_context,
        )
        # ... then proceed with the "I don't know" response to the user ...

STORAGE
-------
Uses SQLite for simplicity (file-based, zero setup, fine for this volume
of data). If/when this needs to scale beyond a single-server deployment,
swap for Postgres — the schema and queries below are simple enough to
port directly.
"""

import sqlite3
import os
from datetime import datetime, timedelta, timezone
from collections import Counter

DB_PATH = os.environ.get("UNANSWERED_QUERY_DB", "unanswered_queries.db")


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates the table if it doesn't exist yet. Safe to call every startup."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS unanswered_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            confidence_score REAL,
            session_id TEXT,
            channel TEXT,
            source_url TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def log_unanswered_query(query, confidence_score=None, session_id=None,
                          channel="web", source_url=None):
    """
    Records one unanswered/low-confidence query. Call this every time the
    bot can't answer confidently — do NOT wait to batch these, log
    immediately so nothing gets lost if the process restarts.
    """
    conn = _get_connection()
    conn.execute(
        """INSERT INTO unanswered_queries
           (query, confidence_score, session_id, channel, source_url, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (query, confidence_score, session_id, channel, source_url,
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def generate_weekly_summary(days=7):
    """
    Returns a summary of the past N days: total unanswered queries, and
    the most frequently asked ones grouped together (simple exact-text
    grouping for now — see note below on similarity grouping).

    Returns:
        {
            "period_days": 7,
            "total_unanswered": 23,
            "top_gaps": [
                {"query": "Do you integrate with Salesforce?", "count": 5},
                ...
            ],
            "raw_queries": [...]  # full list, for the admin dashboard table
        }
    """
    conn = _get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM unanswered_queries WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,)
    ).fetchall()
    conn.close()

    queries = [row["query"] for row in rows]
    # Simple exact-match grouping. NOTE: a smarter version would cluster
    # near-duplicate phrasings ("do you support Shopify" vs "does this work
    # with Shopify") using embedding similarity — worth revisiting once
    # volume is high enough to justify it. Exact-match is a reasonable v1.
    counts = Counter(queries)
    top_gaps = [{"query": q, "count": c} for q, c in counts.most_common(10)]

    return {
        "period_days": days,
        "total_unanswered": len(rows),
        "top_gaps": top_gaps,
        "raw_queries": [dict(row) for row in rows],
    }


def format_summary_as_text(summary):
    """Human-readable version for a Slack post / email digest."""
    lines = [
        f"Unanswered Query Summary — last {summary['period_days']} days",
        f"Total unanswered queries: {summary['total_unanswered']}",
        "",
        "Top documentation gaps:",
    ]
    if not summary["top_gaps"]:
        lines.append("  (none this period)")
    for gap in summary["top_gaps"]:
        lines.append(f"  - \"{gap['query']}\" — asked {gap['count']}x, not in current docs")
    return "\n".join(lines)


# ==========================================================================
# SELF-TEST
# ==========================================================================
if __name__ == "__main__":
    # Use a throwaway test DB so this doesn't pollute a real one
    DB_PATH = "test_unanswered_queries.db"
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    init_db()

    sample_queries = [
        ("Do you integrate with Salesforce?", 0.31, "web"),
        ("Do you integrate with Salesforce?", 0.28, "web"),
        ("Do you integrate with Salesforce?", 0.33, "whatsapp"),
        ("What's your refund policy?", 0.40, "web"),
        ("Can I export my data as CSV?", 0.25, "web"),
        ("What's your refund policy?", 0.38, "web"),
        ("Do you support multi-language chat?", 0.22, "whatsapp"),
    ]
    for query, score, channel in sample_queries:
        log_unanswered_query(query, confidence_score=score, session_id="test-session",
                              channel=channel, source_url="https://noobsync.com/test")

    summary = generate_weekly_summary(days=7)

    print("=" * 60)
    print("UNANSWERED QUERY DETECTION — SELF TEST")
    print("=" * 60)
    print(format_summary_as_text(summary))
    print()
    assert summary["total_unanswered"] == 7, "Expected 7 logged queries"
    assert summary["top_gaps"][0]["query"] == "Do you integrate with Salesforce?"
    assert summary["top_gaps"][0]["count"] == 3
    print("ALL ASSERTIONS PASSED")

    os.remove(DB_PATH)
