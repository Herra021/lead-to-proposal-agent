import os
import sqlite3
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from app.schemas.models import ExtractedLeadData, ProposalDraft
from app.rag.vector_store import search_knowledge_base
from app.tools.external_tools import enrich_company_with_tavily, execute_crm_and_email_actions

load_dotenv(".env")

primary_llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    max_retries=1,
    timeout=45,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

fallback_llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    max_retries=1,
    timeout=45,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

fast_fallback_llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    max_retries=1,
    timeout=30,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

structured_extract_llm = primary_llm.with_structured_output(ExtractedLeadData).with_fallbacks(
    [
        fallback_llm.with_structured_output(ExtractedLeadData),
        fast_fallback_llm.with_structured_output(ExtractedLeadData),
    ]
)

structured_proposal_llm = primary_llm.with_structured_output(ProposalDraft).with_fallbacks(
    [
        fallback_llm.with_structured_output(ProposalDraft),
        fast_fallback_llm.with_structured_output(ProposalDraft),
    ]
)

class LeadGraphState(TypedDict, total=False):
    thread_id: str
    raw_lead: Dict[str, Any]
    extracted_data: Dict[str, Any]
    company_research: str
    retrieved_docs: List[Dict[str, Any]]
    proposal_draft: Dict[str, Any]
    edited_proposal: str
    decision: str
    status: str
    execution_result: Dict[str, Any]

def _get_lead_fields(state: LeadGraphState) -> Dict[str, str]:
    lead = state.get("raw_lead") if isinstance(state.get("raw_lead"), dict) else {}
    return {
        "sender_name": str(lead.get("sender_name") or "Prospective Client"),
        "sender_email": str(lead.get("sender_email") or "unknown@company.com"),
        "company_name": str(lead.get("company_name") or "Unknown Company"),
        "subject": str(lead.get("subject") or "Enterprise Inquiry"),
        "body": str(lead.get("email_body") or lead.get("raw_email_body") or lead.get("body") or ""),
    }

def extract_lead_node(state: LeadGraphState) -> dict:
    print("⏳ [1/3] Extracting lead data with Gemini...", flush=True)
    fields = _get_lead_fields(state)
    prompt = f"""Extract structured enterprise sales data from this inbound inquiry.
Sender: {fields['sender_name']} ({fields['sender_email']})
Company: {fields['company_name']}
Subject: {fields['subject']}
Body:
{fields['body']}
"""
    result: ExtractedLeadData = structured_extract_llm.invoke(prompt)
    print("✅ [1/3] Extraction complete!", flush=True)
    return {"extracted_data": result.model_dump()}

def route_after_extraction(state: LeadGraphState) -> str:
    data = state.get("extracted_data", {})
    if not data.get("is_qualified", False) or data.get("urgency_score", 0) < 5:
        return "disqualify"
    return "enrich_and_rag"

def disqualify_node(state: LeadGraphState) -> dict:
    return {"status": "disqualified_auto_archived"}

def enrich_and_rag_node(state: LeadGraphState) -> dict:
    print("⏳ [2/3] Running Tavily research & Qdrant RAG...", flush=True)
    fields = _get_lead_fields(state)
    data = state.get("extracted_data", {})
    company = data.get("company_name") or fields["company_name"]
    compliance = ", ".join(data.get("required_compliance", []))
    use_case = data.get("use_case_summary") or fields["subject"]

    research = enrich_company_with_tavily(company, use_case)
    rag_query = f"{use_case} {compliance} enterprise pricing SLA architecture"
    docs = search_knowledge_base(rag_query, top_k=4)
    print("✅ [2/3] Enrichment & RAG complete!", flush=True)

    return {
        "company_research": research,
        "retrieved_docs": docs,
    }

def draft_proposal_node(state: LeadGraphState) -> dict:
    print("⏳ [3/3] Drafting structured enterprise proposal...", flush=True)
    fields = _get_lead_fields(state)
    data = state.get("extracted_data", {})
    docs = state.get("retrieved_docs", [])
    company_name = data.get("company_name") or fields["company_name"]

    context_str = "\n\n".join(
        [f"[{d.get('source', 'Doc')} - {d.get('section', 'Info')}]\n{d.get('text', '')}" for d in docs]
    )

    prompt = f"""You are a Principal AI Solutions Architect at CloudScale AI.
Generate a structured B2B technical proposal for {fields['sender_name']} at {company_name}.

--- EXTRACTED REQUIREMENTS ---
{data}

--- LIVE COMPANY INTELLIGENCE (TAVILY) ---
{state.get('company_research', 'N/A')}

--- INTERNAL PRICING, SLA & SECURITY DOCS (QDRANT RAG) ---
{context_str}

Rules:
- recommended_tier MUST be exactly one of: "Starter Tier", "Growth Tier", "Enterprise Tier".
- quoted_monthly_price_usd MUST be >= 1500 and grounded in the internal pricing docs.
- proposal_markdown MUST be a complete, executive-ready Markdown proposal covering Executive Summary, Recommended Tier & Pricing, Security/Compliance ({', '.join(data.get('required_compliance', [])) or 'Standard'}), and Implementation Timeline.
- citations_used MUST list the source filenames referenced.
"""
    draft: ProposalDraft = structured_proposal_llm.invoke(prompt)
    print("✅ [3/3] Structured proposal draft ready for human review!", flush=True)
    return {
        "proposal_draft": draft.model_dump(),
        "status": "awaiting_human_approval",
    }

def execute_actions_node(state: LeadGraphState) -> dict:
    if state.get("decision") == "rejected":
        return {"status": "rejected_by_human"}

    fields = _get_lead_fields(state)
    draft = state.get("proposal_draft") or {}
    final_md = state.get("edited_proposal") or draft.get("proposal_markdown", "")
    result = execute_crm_and_email_actions(
        thread_id=state.get("thread_id", "unknown_thread"),
        extracted_data=state.get("extracted_data", {}),
        proposal_markdown=final_md,
        recipient_email=fields["sender_email"],
    )
    return {
        "status": "approved_and_sent",
        "execution_result": result,
    }

os.makedirs("./storage", exist_ok=True)
conn = sqlite3.connect("./storage/checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)

workflow = StateGraph(LeadGraphState)
workflow.add_node("extract", extract_lead_node)
workflow.add_node("disqualify", disqualify_node)
workflow.add_node("enrich_and_rag", enrich_and_rag_node)
workflow.add_node("draft_proposal", draft_proposal_node)
workflow.add_node("execute_actions", execute_actions_node)

workflow.set_entry_point("extract")
workflow.add_conditional_edges(
    "extract",
    route_after_extraction,
    {
        "disqualify": "disqualify",
        "enrich_and_rag": "enrich_and_rag",
    },
)
workflow.add_edge("disqualify", END)
workflow.add_edge("enrich_and_rag", "draft_proposal")
workflow.add_edge("draft_proposal", "execute_actions")
workflow.add_edge("execute_actions", END)

agent_graph = workflow.compile(
    checkpointer=memory,
    interrupt_before=["execute_actions"],
)
