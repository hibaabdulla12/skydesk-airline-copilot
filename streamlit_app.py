"""SkyDesk chat screen. Run with:  streamlit run streamlit_app.py"""
import logging

import streamlit as st

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
    "Refund request (agent cannot)": "Please issue a full refund for DEMO01 right now.",
}


def render(message: dict) -> None:
    with st.chat_message(message["role"]):
        # Plain markdown only: never enable HTML for text that came from a model or a passenger
        st.markdown(message["content"])
        if message["role"] != "assistant":
            return
        if message.get("gave_up"):
            st.warning("The agent could not finish this automatically. A human should handle this case.")
        calls = message.get("tool_calls", [])
        if calls:
            with st.expander(f"What the agent looked up ({len(calls)} tool calls)"):
                for call in calls:
                    st.markdown(f"**{call['tool']}**")
                    st.json({"arguments": call["args"], "result": call["result"]}, expanded=False)


st.title("SkyDesk: airline disruption copilot")
st.caption(
    "Demo on synthetic data. Each question is handled on its own, so include the booking reference (PNR) every time. "
    "The agent can look things up and explain options, but it cannot issue refunds or rebook passengers."
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
    }
    st.session_state.messages.append(assistant_message)
    render(assistant_message)