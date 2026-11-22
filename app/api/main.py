import uuid 
import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langgraph.types import Command

from app.schemas.models import InboundLead
from app.graph.workflow import agent_graph

app = FastAPI(title="CloudScale Autonomous Lead-to-Proposal Engine")

class ApprovalRequest(BaseModel):
    decision: str # "approved" or "rejected"
    edited_proposal: str

@app.post("/webhooks/inbound-lead")
def ingest_inbound_lead(lead: InboundLead):
    thread_id = f"lead_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "thread_id": thread_id,
        "raw_lead": lead.model_dump(),
        "status": "received"
    }

    # Runs until END (if disqualified) or pauses at human_gate interrupt()
    result = agent_graph.invoke(initial_state, config=config)

    return {
        "thread_id": thread_id,
        "status": result.get("status"),
        "extracted_data": result.get("extracted_data"),
        "proposal_draft": result.get("proposal_draft"),
    }

@app.get("/leads")
def list_all_threads():
    """Fetches all unique thread states from SQLite checkpoints."""
    conn = sqlite3.connect("./storage/checkpoints.sqlite")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT thread_id FROM checkpoints")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    threads = []
    for (tid,) in rows:
        config = {"configurable": {"thread_id": tid}}
        state_snapshot = agent_graph.get_state(config)
        if state_snapshot and state_snapshot.values:
            threads.append(state_snapshot.values)
    return threads

@app.post("/lead/{thread_id}/review")
def review_lead(thread_id: str, review: ApprovalRequest):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = agent_graph.get_state(config)

    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Lead thread not found")

    # Resume the interrupted LangGraph workflow
    result = agent_graph.invoke(
        Command(resume={
            "decision": review.decision,
            "edited_proposal": review.edited_proposal
        }),
        config=config
    )

    return {
        "thread_id": thread_id,
        "status": result.get("status"),
        "execution_result": result.get("execution_result")
    }
