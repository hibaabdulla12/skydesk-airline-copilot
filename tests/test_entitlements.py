
from datetime import datetime, timedelta, timezone

from app import agent, entitlements, rag, tools
from app.schemas import BookingOut, ConnectionCheck, FlightStatus, PassengerOut, SegmentOut


def flight(status="scheduled", delay=0, reason=None, minutes=260, number="SD200", origin="COK", dest="DXB"):
    dep = datetime(2026, 12, 1, 4, 30, tzinfo=timezone.utc)
    arr = dep + timedelta(minutes=minutes)
    d = timedelta(minutes=delay)
    return FlightStatus(
        flight_number=number, origin=origin, destination=dest, flight_date=dep.date(), status=status,
        scheduled_departure=dep, scheduled_arrival=arr, delay_minutes=delay,
        estimated_departure=dep + d, estimated_arrival=arr + d, disruption_reason=reason,
    )


def booking(*flights, feasible=None, fare="Y", tier="none", assistance=False, minor=False):
    segments = [SegmentOut(order=i + 1, status="cancelled" if f.status == "cancelled" else "confirmed", flight=f)
                for i, f in enumerate(flights)]
    connections = [ConnectionCheck(airport="DXB", layover_minutes=-30 if not feasible else 150,
                                   minimum_required_minutes=75, feasible=feasible)] if feasible is not None else []
    passenger = PassengerOut(full_name="Test", loyalty_tier=tier, needs_assistance=assistance,
                             is_unaccompanied_minor=minor, remarks=None)
    return BookingOut(pnr="TEST01", fare_class=fare, ticket_price=1000.0, currency="INR", status="confirmed",
                      passenger=passenger, segments=segments, connections=connections)


def find(report, kind, section=None):
    matches = [e for e in report.entitlements if e.kind == kind and (section is None or e.citation.endswith("§" + section))]
    assert matches, f"no {kind} entitlement in {[(e.kind, e.citation) for e in report.entitlements]}"
    return matches[0]


def test_on_time_booking_has_nothing():
    report = entitlements.calculate(booking(flight()))
    assert report.situation == "none" and report.entitlements == []


def test_delay_under_the_policy_minimum_is_not_a_delay():
    assert entitlements.calculate(booking(flight("delayed", 29, "technical"))).situation == "none"


def test_short_delay_gets_nothing_but_the_information_duty():
    report = entitlements.calculate(booking(flight("delayed", 90, "technical")))
    assert report.situation == "delay"
    assert find(report, "meal_voucher").status == "does_not_apply"
    assert find(report, "cash_compensation").status == "does_not_apply"


def test_two_hour_delay_gets_a_meal_voucher():
    meal = find(entitlements.calculate(booking(flight("delayed", 120, "weather"))), "meal_voucher")
    assert meal.status == "applies" and meal.amount_inr == 600 and meal.citation.endswith("§2.2")


def test_controllable_delay_over_three_hours_gets_compensation_by_flight_time():
    long_flight = find(entitlements.calculate(booking(flight("delayed", 200, "technical", minutes=260))), "cash_compensation")
    short_flight = find(entitlements.calculate(booking(flight("delayed", 200, "crew", minutes=190))), "cash_compensation")
    assert (long_flight.status, long_flight.amount_inr) == ("applies", 10000)
    assert (short_flight.status, short_flight.amount_inr) == ("applies", 5000)


def test_four_hour_delay_gets_the_refund_option():
    report = entitlements.calculate(booking(flight("delayed", 240, "technical")))
    assert find(report, "refund_option").status == "applies"
    assert find(entitlements.calculate(booking(flight("delayed", 239, "technical"))), "refund_option").status == "does_not_apply"


def test_extraordinary_delay_gets_care_but_no_cash():
    report = entitlements.calculate(booking(flight("delayed", 300, "weather")))
    assert report.cause == "extraordinary"
    assert find(report, "meal_voucher").status == "applies"
    cash = find(report, "cash_compensation")
    assert cash.status == "does_not_apply" and cash.citation.endswith("§5.2") and cash.amount_inr is None


def test_unknown_reason_needs_a_human():
    report = entitlements.calculate(booking(flight("delayed", 200, None)))
    assert find(report, "cash_compensation").status == "needs_confirmation"
    assert report.notes


def test_cancellation_controllable_cause():
    report = entitlements.calculate(booking(flight("cancelled", 0, "technical", minutes=260)))
    assert report.situation == "cancellation"
    assert find(report, "rebooking_or_refund").status == "applies"
    assert find(report, "meal_voucher").amount_inr == 600
    assert find(report, "hotel").status == "needs_confirmation"
    cash = find(report, "cash_compensation")
    assert (cash.status, cash.amount_inr) == ("needs_confirmation", 10000)


def test_cancellation_weather_gets_no_cash():
    cash = find(entitlements.calculate(booking(flight("cancelled", 0, "weather"))), "cash_compensation")
    assert cash.status == "does_not_apply" and cash.citation.endswith("§5.2")


def test_missed_connection_uses_the_total_flight_time():
    first = flight("delayed", 190, "technical", minutes=260)
    second = flight(number="SD216", origin="DXB", dest="LHR", minutes=470)
    report = entitlements.calculate(booking(first, second, feasible=False))
    assert report.situation == "missed_connection"
    cash = find(report, "cash_compensation")
    assert (cash.status, cash.amount_inr) == ("needs_confirmation", 10000)
    assert cash.citation.endswith("§4.4")
    short = entitlements.calculate(booking(flight("delayed", 100, "crew", minutes=60),
                                           flight(number="SD1", minutes=70), feasible=False))
    assert find(short, "cash_compensation").amount_inr == 5000


def test_a_delay_absorbed_by_a_feasible_connection_gives_no_compensation():
    first = flight("delayed", 100, "technical")
    second = flight(number="SD216", origin="DXB", dest="LHR", minutes=470)
    report = entitlements.calculate(booking(first, second, feasible=True))
    assert report.situation == "delay"
    assert find(report, "cash_compensation").status == "does_not_apply"


def test_connection_too_short_without_any_disruption_goes_to_the_duty_manager():
    report = entitlements.calculate(booking(flight(), flight(number="SD216"), feasible=False))
    assert report.situation == "none" and "duty manager" in report.notes[0]


def test_priority_groups():
    def group(**kw):
        report = entitlements.calculate(booking(flight("cancelled", 0, "crew"), **kw))
        return int(find(report, "rebooking_priority").reason.split("group ")[1].split(" ")[0])

    assert group(minor=True, assistance=True, tier="gold") == 1
    assert group(assistance=True, tier="gold") == 2
    assert group(tier="platinum") == 3
    assert group(fare="J") == 4
    assert group() == 5


def test_special_passengers_get_their_sections():
    minor = entitlements.calculate(booking(flight("cancelled", 0, "crew"), minor=True))
    assist = entitlements.calculate(booking(flight("delayed", 150, "crew"), assistance=True))
    assert find(minor, "special_handling").citation.endswith("§6.1")
    assert find(assist, "special_handling").citation.endswith("§6.2")


def test_gold_member_gets_lounge_access_for_a_long_enough_delay():
    assert find(entitlements.calculate(booking(flight("delayed", 130, "crew"), tier="gold")), "lounge_access")
    silver = entitlements.calculate(booking(flight("delayed", 130, "crew"), tier="silver"))
    assert not [e for e in silver.entitlements if e.kind == "lounge_access"]


# ---- the code and the policy document must agree ----

def all_scenarios():
    return [
        booking(flight("delayed", 90, "technical")), booking(flight("delayed", 200, "crew")),
        booking(flight("delayed", 300, "weather")), booking(flight("delayed", 400, "technical"), tier="gold"),
        booking(flight("delayed", 200, None), assistance=True),
        booking(flight("cancelled", 0, "technical"), minor=True), booking(flight("cancelled", 0, "weather")),
        booking(flight("delayed", 190, "technical"), flight(number="SD216", minutes=470), feasible=False),
        booking(flight("delayed", 190, "weather"), flight(number="SD216", minutes=470), feasible=False),
    ]


def test_every_cited_section_exists_in_the_policy_document():
    policy_sections = {c.section for c in rag.load_policy_chunks()}
    cited = {e.citation.split("§")[1] for b in all_scenarios() for e in entitlements.calculate(b).entitlements}
    assert cited and cited <= policy_sections, f"not in the policy: {cited - policy_sections}"


def test_the_numbers_in_the_code_match_the_policy_text():
    text = {c.section: c.content for c in rag.load_policy_chunks()}
    assert f"INR {entitlements.MEAL_VOUCHER_INR}" in text["2.2"] and "2 hours" in text["2.2"]
    assert "4 hours" in text["2.3"] and "6 hours" in text["2.4"]
    assert "3 hours" in text["2.5"]
    assert "5,000" in text["2.5"] and "10,000" in text["2.5"]
    assert "30 minutes" in text["1.2"] and "2 hours" in text["6.3"]
    assert entitlements.MEAL_DELAY_MIN == 120 and entitlements.REFUND_DELAY_MIN == 240
    assert entitlements.HOTEL_DELAY_MIN == 360 and entitlements.COMPENSATION_DELAY_MIN == 180
    assert entitlements.COMPENSATION_SHORT_INR == 5000 and entitlements.COMPENSATION_LONG_INR == 10000


# ---- the tool and the citation check ----

def test_citations_from_the_calculator_count_as_verified():
    report = entitlements.calculate(booking(flight("cancelled", 0, "technical"))).model_dump(mode="json")
    trace = [{"tool": "calculate_entitlements", "args": {"pnr": "TEST01"}, "result": report}]
    assert agent.verify_citations("Meal voucher [SkyDesk Disruption Policy §3.2].", trace) == []
    assert agent.verify_citations("Free upgrade [SkyDesk Disruption Policy §9.9].", trace) == ["9.9"]


def test_tool_is_registered_and_validates_input():
    assert "calculate_entitlements" in tools.TOOL_MAP
    assert "error" in tools.calculate_entitlements("12")
    assert "No booking found" in tools.calculate_entitlements("ZZZZZZ")["error"]


def test_demo_bookings_through_the_tool():
    cancelled = tools.calculate_entitlements("DEMO01")
    assert cancelled["situation"] == "cancellation"
    assert cancelled["cause"] == "controllable"
    weather = tools.calculate_entitlements("DEMO03")
    assert [e for e in weather["entitlements"] if e["kind"] == "cash_compensation"][0]["status"] == "does_not_apply"
    missed = tools.calculate_entitlements("DEMO02")
    assert missed["situation"] == "missed_connection"
    assert tools.calculate_entitlements("DEMO07")["situation"] == "none"
    minor = tools.calculate_entitlements("DEMO04")
    assert any(e["citation"].endswith("§6.1") for e in minor["entitlements"])
