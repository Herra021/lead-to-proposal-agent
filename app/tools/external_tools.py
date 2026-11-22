import os
import json
from datetime import datetime, timezone
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

CRM_LOG_PATH = "./storage/crm_audit_log.json"


def enrich_company_with_tavily(company_name: str, use_case: str) -> str:
    """Runs live web intelligence search on the prospect company via Tavily."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Tavily API key not configured; skipping live web enrichment."

    try:
        tavily = TavilyClient(api_key=api_key)
        query = f"{company_name} company overview industry technology stack news"
        response = tavily.search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if not results:
            return f"No public web intelligence found for {company_name}."

        snippets = [
            f"- {r.get('title', 'Source')}: {r.get('content', '')[:300]} ({r.get('url', '')})"
            for r in results
        ]
        return "\n".join(snippets)
    except Exception as e:
        return f"Tavily enrichment fallback (non-blocking): {str(e)}"


def execute_crm_and_email_actions(
    thread_id: str,
    extracted_data: dict,
    proposal_markdown: str,
    recipient_email: str,
) -> dict:
    """Idempotently logs approved deal to local CRM JSON store and records email dispatch."""
    os.makedirs("./storage", exist_ok=True)

    if os.path.exists(CRM_LOG_PATH):
        with open(CRM_LOG_PATH, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    # Idempotency guard: prevent duplicate CRM entries for the same thread_id
    for existing in logs:
        if existing.get("thread_id") == thread_id:
            return existing

    record = {
        "thread_id": thread_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "company_name": extracted_data.get("company_name", "Unknown"),
        "recipient_email": recipient_email,
        "recommended_tier": extracted_data.get("recommended_tier", "Enterprise"),
        "estimated_mrr_usd": extracted_data.get("estimated_mrr_usd", 0),
        "required_compliance": extracted_data.get("required_compliance", []),
        "crm_status": "Qualified - Proposal Sent",
        "email_sent": True,
        "proposal_preview": proposal_markdown[:250] + "...",
    }

    logs.append(record)
    with open(CRM_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    return record