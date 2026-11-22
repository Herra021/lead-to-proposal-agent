import streamlit as st
import requests
import json
import os

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI Sales Engineer Control Centre", layout="wide")
st.title("Autonomous Lead-to-Proposal & CRM Engine")

tab1, tab2, tab3 = st.tabs(["1. Simulate Inbound Webhook", "2. Human-in-the-Loop Approval Gate", "3. CRM Audit Log"])

# --- TAB 1: SIMULATE INBOUND LEAD ---
with tab1:
    st.subheader("Simulate Incoming Enterprise Inquiry")
    preset = st.selectbox("Load Sample Scenario:", [
        "High-Value Healthcare Enterprise (HIPAA + SOC2)",
        "LOW-Budget Student / Spam Inquiry (Auto-Filter Test)"
    ])

    if "Healthcare" in preset:
        default_name, default_email, default_co = "Sarah Jenkins", "s.jenkins@medvaulthealth.io", "MedVault Health"
        default_subj = "Enterprise API Pricing & HIPAA BAA Inquiry"
        default_body = (
            "Hi CloudScale team,\n\nWe are a 650-employee digital health platform processing 2M patient "
            "record monthly. We need an AI automation pipeline with strict HIPAA BAA compliance, single-tenant "
            "VPC deployment, and SOC2 Type II documentation. Our target budget is $15,000/month and we want to "
            "launch in Q1. Can you send technical specs and pricing?"
        )
    else:
        default_name, default_email, default_co = "Alex Student", "alex99@gmail.com", "Personal Project"
        default_subj = "Free API credits for college hackathon?"
        default_body = "Hey, I am building a college project and have $0 budget. Can I get unlimited API access?"

    with st.form("webhook_form"):
        col1, col2, col3 = st.columns(3)
        sender_name = col1.text_input("Sender Name", default_name)
        sender_email = col2.text_input("Sender Email", default_email)
        company_name = col3.text_input("Company Name", default_co)
        subject = st.text_input("Subject", default_subj)
        email_body = st.text_area("Email Body", default_body, height=150)

        submitted = st.form_submit_button("Trigger Webhook -> Run LangGraph Agent")
        if submitted:
            with st.spinner("Running Extraction -> Tavily Enrichment -> Qdrant Hybrid RAG -> Proposal Draft..."):
                res = requests.post(f"{API_URL}/webhooks/inbound-lead", json={
                    "sender_name": sender_name,
                    "sender_email": sender_email,
                    "company_name": company_name,
                    "subject": subject,
                    "email_body": email_body
                })
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"Workflow processed! Thread ID: '{data['thread_id']}' | Status: **{data['status']}**")
                    st.json(data["extracted_data"])
                else:
                    st.error(f"Error: {res.text}")

# --- TAB 2: HUMAN-IN-THE-LOOP APPROVAL ---
with tab2:
    st.subheader("Pending Sales Engineer Approvals")
    if st.button("Refresh Queue"):
        st.rerun()

    try:
        leads = requests.get(f"{API_URL}/leads").json()
    except Exception:
        leads = []
        st.warning("Make sure FastAPI backend is running on port 8000.")

    pending = [l for l in leads if l.get("status") == "awaiting_human_approval"]

    if not pending:
        st.info("No leads currently paused at the Human-in-the-Loop gate.")
    else:
        for lead in pending:
            tid = lead["thread_id"]
            ext = lead["extracted_data"]
            draft = lead["proposal_draft"]

            with st.expander(f"{ext['company_name']} - Recommended: {draft['recommended_tier']} (${draft['quoted_monthly_price_usd']}/mo) [{tid}]", expanded=True):
                left, right = st.columns([1, 1.3])

                with left:
                    st.markdown("**1. Pydantic Extracted Intelligence**")
                    st.json(ext)
                    st.markdown("**2. Live Web Enrichment (Tavily)**")
                    st.caption(lead.get("company_research", ""))
                    st.markdown("**3. Retrieved Qdrant RAG Sources**")
                    for doc in lead.get("retrieved_docs", []):
                        st.info(f"**{doc['source']}** (Score: {doc['score']})\n\n{doc['text']}")

                with right:
                    st.markdown("**4. AI-Drafted Proposal (Editable Before Send)**")
                    edited_text = st.text_area(
                        "Edit Markdown Proposal:",
                        value=draft["proposal_markdown"],
                        height=380,
                        key=f"edit_{tid}"
                    )
                    btn1, btn2 = st.columns(2)
                    if btn1.button("Approved! Update CRM & Send Email", key=f"app_{tid}", type="primary"):
                        r = requests.post(f"{API_URL}/lead/{tid}/review", json={
                            "decision": "approved",
                            "edited_proposal": edited_text
                        })
                        st.success("Approved! Graph resumed. CRM updated and email sent.")
                        st.rerun()

                    if btn2.button("Reject Draft", key=f"rej_{tid}"):
                        requests.post(f"{API_URL}/lead/{tid}/review", json={
                            "decision": "rejected",
                            "edited_proposal": edited_text
                        })
                        st.warning("Draft rejected and archived.")
                        st.rerun()

# --- TAB 3: CRM AUDIT LOG ---
with tab3:
    st.subheader("Executed CRM Updates & Dispatched Emails")
    if os.path.exists("./storage/crm_audit_log.json"):
        with open("./storage/crm_audit_log.json") as f:
            st.json(json.load(f))
    else:
        st.info("No approved CRM transactions executed yet.")
