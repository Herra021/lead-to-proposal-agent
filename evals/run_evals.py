import time
import json
from app.graph.workflow import agent_graph

TEST_CASES = [
    {
        "name": "Enterprise Healthcare (HIPAA + SOC2 + $15k/mo)",
        "expected_qualified": True,
        "expected_tier": "Enterprise Tier",
        "min_price": 1500,
        "lead": {
            "sender_name": "Sarah Jenkins",
            "sender_email": "s.jenkins@medvaulthealth.io",
            "company_name": "MedVault Health",
            "subject": "Enterprise API Pricing & HIPAA BAA Inquiry",
            "email_body": "We are a 650-employee digital health platform processing 2M patient records monthly. We need an AI automation pipeline with strict HIPAA BAA compliance, single-tenant VPC deployment, and SOC2 Type II documentation. Target budget is $15,000/month and we want to launch in Q1."
        }
    },
    {
        "name": "Mid-Market Fintech (SOC2 + $4,500/mo)",
        "expected_qualified": True,
        "expected_tier": None,
        "min_price": 1500,
        "lead": {
            "sender_name": "Rohan Mehta",
            "sender_email": "rohan@paygrid.in",
            "company_name": "PayGrid Technologies",
            "subject": "Automated KYC Workflow & SOC2 Compliance",
            "email_body": "We are a Series A fintech with 90 employees looking to automate merchant onboarding. We require SOC2 Type II compliance and 99.9% uptime SLA. Budget is $4,500/month starting next month."
        }
    },
    {
        "name": "Student Hackathon ($0 Budget - Should Disqualify)",
        "expected_qualified": False,
        "expected_tier": None,
        "min_price": 0,
        "lead": {
            "sender_name": "Alex Student",
            "sender_email": "alex99@gmail.com",
            "company_name": "Personal Project",
            "subject": "Free API credits for college hackathon?",
            "email_body": "Hey, I am building a college project and have $0 budget. Can I get unlimited API access?"
        }
    },
    {
        "name": "Job Seeker Spam (Should Disqualify)",
        "expected_qualified": False,
        "expected_tier": None,
        "min_price": 0,
        "lead": {
            "sender_name": "John Doe",
            "sender_email": "john.jobs@yahoo.com",
            "company_name": "N/A",
            "subject": "Looking for internship opportunities",
            "email_body": "Hi HR team, please find my resume attached for software developer roles."
        }
    }
]

def run_benchmark():
    print("\n🚀 Running CloudScale AI Agent Production Evaluation Suite...\n" + "=" * 65)
    passed = 0
    latencies = []

    for idx, tc in enumerate(TEST_CASES, 1):
        tid = f"eval_{idx}_{int(time.time())}"
        t0 = time.perf_counter()
        result = agent_graph.invoke(
            {"thread_id": tid, "raw_lead": tc["lead"]},
            config={"configurable": {"thread_id": tid}}
        )
        elapsed = round(time.perf_counter() - t0, 2)
        latencies.append(elapsed)

        ext = result.get("extracted_data", {})
        is_qual = ext.get("is_qualified", False)
        draft = result.get("proposal_draft") or {}
        price = draft.get("quoted_monthly_price_usd", 0)
        tier = draft.get("recommended_tier")

        ok_qual = (is_qual == tc["expected_qualified"])
        ok_price = (not is_qual) or (price >= tc["min_price"])
        ok_tier = (tc["expected_tier"] is None) or (tier == tc["expected_tier"])
        ok_citations = (not is_qual) or (len(draft.get("citations_used", [])) > 0)

        case_pass = ok_qual and ok_price and ok_tier and ok_citations
        if case_pass:
            passed += 1

        status_icon = "✅ PASS" if case_pass else "❌ FAIL"
        print(f"{status_icon} | Case {idx}: {tc['name']} ({elapsed}s)")
        print(f"       Qualified={is_qual} (expected {tc['expected_qualified']}) | Tier={tier} | Quote=${price}/mo | Citations={draft.get('citations_used', [])}")

    print("=" * 65)
    print(f"📊 SUMMARY: {passed}/{len(TEST_CASES)} Passed ({round(passed/len(TEST_CASES)*100)}%) | Avg Latency: {round(sum(latencies)/len(latencies), 2)}s")

if __name__ == "__main__":
    run_benchmark()
