"""
crm.py
Best-effort hand-off of a new visitor to Akshada's shared Zoho module
(security/zoho_crm.py). Does nothing unless the Zoho environment variables
are configured, and can never block or break sign-in.
"""

import logging
import os
import threading

logger = logging.getLogger("noobsync.knowledgebot")

_REQUIRED = (
    "ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN",
    "ZOHO_ACCOUNTS_DOMAIN", "ZOHO_API_DOMAIN",
)


def zoho_configured() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED)


def capture_lead_in_background(name: str, phone: str) -> None:
    if not zoho_configured():
        return

    def _run() -> None:
        try:
            from security.zoho_crm import create_lead

            result = create_lead(
                name=name,
                phone=phone,
                conversation_summary="Visitor signed in to the web chat.",
                service_interest_tag="",
                intent_score="Browsing",
                source_url="",
                channel="web",
            )
            logger.info("[crm] Zoho lead created: %s", result)
        except Exception as exc:  # never surface CRM problems to the visitor
            logger.warning("[crm] Zoho lead creation failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
