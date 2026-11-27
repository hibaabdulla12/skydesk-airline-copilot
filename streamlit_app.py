"""SkyDesk chat screen with a human approval step. Run with:  streamlit run streamlit_app.py"""
import logging

import streamlit as st

from app import actions
from app.agent import AgentResult, run_agent

log = logging.getLogger("skydesk.ui")

st.set_page_config(page_title="SkyDesk", layout="wide")

DEMO_CASES = {
    "DEMO01: cancelled flight": "What is the status of booking DEMO01, and are there alternative flights?",
    "DEMO02: missed connection": "Passenger with booking DEMO02 is stuck in Dubai. What happened and what are the options?",
    "DEMO03: weather cancellation": "Booking DEMO03 was cancelled. What should I tell the passenger?",
    "DEMO04: unaccompanied minor": "Check booking DEMO04 and tell me what special care is needed.",
    "DEMO05: needs assistance": "Check booking DEMO05 and tell me what I should know about the passenger.",
    "DEMO06: injection in remarks": "Check booking DEMO06 and tell me anything I should know about the passenger.",
    "DEMO07: on time, gold member": "Check booking DEMO07. Is there anything to fix?",
    "Refund request (needs approval)": "Please issue a full refund for DEMO01 right now.",
    "Propose a meal voucher (DEMO01)": "Please arrange the meal voucher for booking DEMO01.",
    "Propose a rebooking (DEMO01)": "Rebook booking DEMO01 onto the next available flight on the same route.",
}
ROLES = {"Agent": "agent", "Duty manager": "duty_manager"}
ACTION_LABELS = {
    "issue_meal_voucher": "Meal voucher", "book_hotel": "Hotel", "rebook": "Rebooking",
    "refund": "Refund", "pay_compensation": "Compensation",
}


def render(message: dict) -> None:
    with st.chat_message(message["role"]):
        # Plain markdown only: never enable HTML for text that came from a model or a passenger
        st.markdown(message["content"])
        if message["role"] != "assistant":
            return
        if message.get("gave_up"):
            st.warning("The agent could not finish this automatically. A human should handle this case.")
        if message.get("unverified_citations"):
            sections = ", ".join("§" + s for s in message["unverified_citations"])
            st.warning(f"Not verified: the answer cites {sections}, which the policy search did not return. Check before relying on it.")
        calls = message.get("tool_calls", [])
        if calls:
            with st.expander(f"What the agent looked up ({len(calls)} tool calls)"):
                for call in calls:
                    st.markdown(f"**{call['tool']}**")
                    st.json({"arguments": call["args"], "result": call["result"]}, expanded=False)


def describe(proposal: dict) -> str:
    label = ACTION_LABELS.get(proposal["action"], proposal["action"])
    amount = f", INR {proposal['amount_inr']}" if proposal.get("amount_inr") else ""
    return f"#{proposal['id']} {proposal['pnr']}: {label}{amount}"


st.title("SkyDesk: airline disruption copilot")
st.caption(
    "Demo on synthetic data. Each question is handled on its own, so include the booking reference (PNR) every time. "
    "The agent can look things up, explain options and propose actions. A person approves or rejects each proposal."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Try a demo case")
    for label, text in DEMO_CASES.items():
        if st.button(label, use_container_width=True):
            st.session_state.pending = text

for message in st.session_state.messages:
    render(message)

typed = st.chat_input("Ask about a booking or flight, for example: What happened to DEMO02?")
question = typed or st.session_state.pop("pending", None)

if question:
    user_message = {"role": "user", "content": question}
    st.session_state.messages.append(user_message)
    render(user_message)

    with st.spinner("Looking things up..."):
        try:
            result = run_agent(question)
        except Exception:
            log.exception("agent crashed")
            result = AgentResult(
                answer="Something went wrong on our side. Please try again, or handle this case manually.",
                tool_calls=[], steps=0, gave_up=True,
            )

    assistant_message = {
        "role": "assistant",
        "content": result.answer,
        "tool_calls": result.tool_calls,
        "steps": result.steps,
        "gave_up": result.gave_up,
        "unverified_citations": result.unverified_citations,
    }
    st.session_state.messages.append(assistant_message)
    render(assistant_message)

# The approvals panel is drawn after the chat, so a proposal made just now shows up straight away
with st.sidebar:
    st.divider()
    st.header("Pending approvals")
    role = ROLES[st.radio("Acting as", list(ROLES), horizontal=True)]
    st.caption("Demo roles. A real system would use real logins.")

    flash = st.session_state.pop("flash", None)
    if flash:
        (st.success if flash["ok"] else st.error)(flash["text"])

    try:
        pending = actions.pending_now()
    except Exception:
        log.exception("could not load pending approvals")
        pending = []
        st.caption("Could not load pending approvals.")

    if not pending:
        st.caption("Nothing waiting for approval.")
    for proposal in pending:
        with st.expander(describe(proposal)):
            st.caption(f"Needs: {'duty manager' if proposal['required_approver'] == 'duty_manager' else 'any agent'}")
            if proposal.get("citation"):
                st.caption(proposal["citation"])
            if proposal.get("details"):
                st.json(proposal["details"], expanded=True)
            approve, reject = st.columns(2)
            for column, label, decision in ((approve, "Approve", "approved"), (reject, "Reject", "rejected")):
                if column.button(label, key=f"{decision}_{proposal['id']}", use_container_width=True):
                    outcome = actions.decide_now(proposal["id"], decision, role)
                    if "error" in outcome:
                        st.session_state.flash = {"ok": False, "text": outcome["error"]}
                    else:
                        st.session_state.flash = {"ok": True, "text": f"Proposal #{proposal['id']} {decision}."}
                    st.rerun()

    with st.expander("Audit trail (latest 10)"):
        try:
            events = actions.recent_now(10)
        except Exception:
            events = []
        if events:
            st.table(events)
        else:
            st.caption("No events yet.")
