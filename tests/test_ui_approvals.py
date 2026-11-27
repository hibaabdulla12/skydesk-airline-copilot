from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import actions

APP = str(Path(__file__).parent.parent / "streamlit_app.py")

PROPOSAL = {"id": 7, "pnr": "DEMO01", "action": "issue_meal_voucher", "amount_inr": 600,
            "required_approver": "agent", "citation": "SkyDesk Disruption Policy §3.2", "details": {}}
MANAGER_PROPOSAL = {**PROPOSAL, "id": 8, "action": "refund", "amount_inr": 12000, "required_approver": "duty_manager"}


def open_app(monkeypatch, pending, decide=None):
    monkeypatch.setattr(actions, "pending_now", lambda: pending)
    monkeypatch.setattr(actions, "recent_now", lambda limit=10: [])
    calls = []
    monkeypatch.setattr(actions, "decide_now",
                        decide or (lambda *args: calls.append(args) or {"status": args[1]}))
    return AppTest.from_file(APP, default_timeout=15).run(), calls


def test_pending_proposals_are_listed_with_buttons(monkeypatch):
    at, _ = open_app(monkeypatch, [PROPOSAL])
    assert not at.exception
    assert any("DEMO01" in e.label and "Meal voucher" in e.label for e in at.sidebar.expander)
    assert {b.key for b in at.sidebar.button if b.key} == {"approved_7", "rejected_7"}


def test_nothing_pending_shows_a_message(monkeypatch):
    at, _ = open_app(monkeypatch, [])
    assert not at.exception
    assert any("Nothing waiting" in c.value for c in at.sidebar.caption)


def test_approve_calls_the_service_with_the_chosen_role(monkeypatch):
    at, calls = open_app(monkeypatch, [PROPOSAL])
    at.sidebar.button(key="approved_7").click().run()
    assert not at.exception
    assert calls == [(7, "approved", "agent")]


def test_duty_manager_role_is_passed_on(monkeypatch):
    at, calls = open_app(monkeypatch, [MANAGER_PROPOSAL])
    at.sidebar.radio[0].set_value("Duty manager").run()
    at.sidebar.button(key="approved_8").click().run()
    assert calls == [(8, "approved", "duty_manager")]


def test_reject_calls_the_service(monkeypatch):
    at, calls = open_app(monkeypatch, [PROPOSAL])
    at.sidebar.button(key="rejected_7").click().run()
    assert calls == [(7, "rejected", "agent")]


def test_a_refused_approval_shows_the_reason(monkeypatch):
    refuse = lambda *args: {"error": "Proposal #8 needs the duty manager to approve it."}
    at, _ = open_app(monkeypatch, [MANAGER_PROPOSAL], decide=refuse)
    at.sidebar.button(key="approved_8").click().run()
    assert not at.exception
    assert any("duty manager" in e.value for e in at.error)
