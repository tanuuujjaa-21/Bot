"""
zoho_crm.py

NoobSync Knowledge Base AI + ConnectOps — Shared Zoho CRM Module
Owner: Akshada (built in personal sandbox account, per Week 3/4 task spec)
Shared with: Hansika (ConnectOps), Tanuja (WhatsApp integration, Week 5)

WHAT THIS IS
------------
ONE function any channel calls to create a lead in Zoho CRM, so every lead
— whether from the Knowledge Base bot (web or WhatsApp) or from ConnectOps
— lands in Zoho with the exact same field structure. No duplicate Zoho
integrations, no inconsistent lead records.

SECURITY — READ THIS FIRST
----------------------------
This file contains NO credentials. Credentials are read from environment
variables, so each person/environment configures their own safely:

    export ZOHO_CLIENT_ID="your_client_id"
    export ZOHO_CLIENT_SECRET="your_client_secret"
    export ZOHO_REFRESH_TOKEN="your_refresh_token"
    export ZOHO_ACCOUNTS_DOMAIN="https://accounts.zoho.in"   # match your region
    export ZOHO_API_DOMAIN="https://www.zohoapis.in"          # match your region
    export ZOHO_SALES_TEAM_USER_ID="the zoho user id to assign follow-up tasks to"

Or put them in a local .env file (never commit this to git) and load with
python-dotenv. Never hardcode real credentials into this file or any
script that imports it — this file gets shared/reused across channels and
people, so it must stay credential-free.

DURING DEVELOPMENT: everyone should point their own env vars at their OWN
personal Zoho sandbox account (not NoobSync's production account) until
the Director approves moving to production credentials.

HOW TO USE THIS MODULE
------------------------
    from zoho_crm import create_lead

    result = create_lead(
        name="Akshada Test",
        phone="9876543210",
        conversation_summary="Visitor asked about Shopify integration and pricing.",
        service_interest_tag="Shopify Integration",
        intent_score="High Intent",
        source_url="https://noobsync.com",
        channel="web",   # or "whatsapp"
    )
    print(result)  # {"lead_id": "...", "task_id": "...", "status": "created"}

That's the entire integration surface — one function call, same shape,
regardless of which channel or bot instance is calling it.
"""

import os
import time
import requests


class ZohoConfigError(Exception):
    """Raised when required environment variables are missing."""
    pass


class ZohoAPIError(Exception):
    """Raised when a Zoho API call fails."""
    pass


def _get_config():
    required = [
        "ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN",
        "ZOHO_ACCOUNTS_DOMAIN", "ZOHO_API_DOMAIN",
    ]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ZohoConfigError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"See the module docstring for setup instructions."
        )
    return {
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
        "accounts_domain": os.environ["ZOHO_ACCOUNTS_DOMAIN"],
        "api_domain": os.environ["ZOHO_API_DOMAIN"],
        "sales_team_user_id": os.environ.get("ZOHO_SALES_TEAM_USER_ID"),  # optional
    }


# Simple in-process cache so we don't refresh the access token on every
# single call — access tokens last ~1 hour.
_token_cache = {"access_token": None, "expires_at": 0}


def _get_access_token():
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    config = _get_config()
    url = f"{config['accounts_domain']}/oauth/v2/token"
    data = {
        "refresh_token": config["refresh_token"],
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "grant_type": "refresh_token",
    }
    resp = requests.post(url, data=data, timeout=10)
    result = resp.json()

    if "access_token" not in result:
        raise ZohoAPIError(f"Failed to refresh access token: {result}")

    _token_cache["access_token"] = result["access_token"]
    # Refresh a bit early (5 min buffer) rather than cutting it exactly at expiry
    _token_cache["expires_at"] = time.time() + result.get("expires_in", 3600) - 300
    return _token_cache["access_token"]


def create_lead(
    name: str,
    phone: str,
    conversation_summary: str = "",
    service_interest_tag: str = "",
    intent_score: str = "",
    source_url: str = "",
    channel: str = "web",
) -> dict:
    """
    Creates a lead in Zoho CRM and an auto-assigned follow-up task.

    Args:
        name: Visitor's name (required — mapped to Zoho's Last_Name field)
        phone: Visitor's phone number (required)
        conversation_summary: Auto-generated summary of the chat, for the sales
            team's context (mapped to Description)
        service_interest_tag: What the visitor seemed interested in, e.g.
            "Shopify Integration", "SME Plan" (mapped to a custom field —
            must be created in Zoho's Leads layout first, see note below)
        intent_score: e.g. "Browsing" / "Interested" / "High Intent" / "Ready"
            (mapped to Rating, or a custom field — see note below)
        source_url: Which page/URL the conversation started from
        channel: "web" or "whatsapp" — feeds Lead_Source

    Returns:
        dict with lead_id, task_id (if created), and status.

    Raises:
        ZohoConfigError if environment variables aren't set.
        ZohoAPIError if the Zoho API call itself fails.

    NOTE ON CUSTOM FIELDS: service_interest_tag and intent_score currently
    ride along in the Description text so this works out of the box with
    zero Zoho configuration. Once NoobSync's production Zoho account has
    custom fields created for these (Service_Interest, Intent_Score), swap
    the commented-out lines below to use them as real structured fields
    instead of free text.
    """
    if not name or not phone:
        raise ValueError("name and phone are both required to create a lead")

    config = _get_config()
    access_token = _get_access_token()

    channel_label = "Knowledge Base Bot - Web" if channel == "web" else "Knowledge Base Bot - WhatsApp"

    description_parts = []
    if conversation_summary:
        description_parts.append(f"Summary: {conversation_summary}")
    if service_interest_tag:
        description_parts.append(f"Interest: {service_interest_tag}")
    if intent_score:
        description_parts.append(f"Intent: {intent_score}")
    if source_url:
        description_parts.append(f"Source: {source_url}")
    description = " | ".join(description_parts)

    lead_payload = {
        "data": [
            {
                "Last_Name": name,
                "Phone": phone,
                "Description": description,
                "Lead_Source": channel_label,
                # Once custom fields exist in production Zoho, prefer these:
                # "Service_Interest": service_interest_tag,
                # "Intent_Score": intent_score,
                # "Source_URL": source_url,
            }
        ]
    }

    url = f"{config['api_domain']}/crm/v8/Leads"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=lead_payload, timeout=10)
    result = resp.json()

    if resp.status_code != 201:
        raise ZohoAPIError(f"Failed to create lead: {result}")

    lead_id = result["data"][0]["details"]["id"]

    task_id = None
    if config["sales_team_user_id"]:
        task_id = _create_followup_task(config, access_token, lead_id, name)

    return {"lead_id": lead_id, "task_id": task_id, "status": "created"}


def _create_followup_task(config, access_token, lead_id, lead_name):
    """Creates a follow-up task on the lead, assigned to the sales team."""
    url = f"{config['api_domain']}/crm/v8/Leads/{lead_id}/Tasks"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "data": [
            {
                "Subject": f"Follow up with {lead_name} (new bot lead)",
                "Status": "Not Started",
                "Priority": "High",
                "Owner": {"id": config["sales_team_user_id"]},
            }
        ]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    result = resp.json()
    if resp.status_code != 201:
        # Don't fail the whole lead creation just because the task failed —
        # log it, but the lead itself is already saved.
        print(f"[zoho_crm] WARNING: lead {lead_id} created, but follow-up "
              f"task failed: {result}")
        return None
    return result["data"][0]["details"]["id"]


# ==========================================================================
# SELF-TEST — run with your own env vars set, against YOUR sandbox account
# ==========================================================================
if __name__ == "__main__":
    print("Testing create_lead() against your configured Zoho sandbox...")
    try:
        result = create_lead(
            name="Test Lead - zoho_crm module",
            phone="9876543210",
            conversation_summary="Testing the shared zoho_crm.py module.",
            service_interest_tag="Module Test",
            intent_score="High Intent",
            source_url="https://noobsync.com/test",
            channel="web",
        )
        print("SUCCESS:", result)
    except (ZohoConfigError, ZohoAPIError, ValueError) as e:
        print("FAILED:", e)
