from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def get_booking(pnr):
    return client.get(f"/bookings/{pnr}")


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_unknown_pnr_returns_404():
    assert get_booking("ZZZZZZ").status_code == 404


def test_pnr_is_case_insensitive():
    assert get_booking("demo01").status_code == 200


def test_cancelled_flight():
    data = get_booking("DEMO01").json()
    flight = data["segments"][0]["flight"]
    assert flight["status"] == "cancelled"
    assert flight["disruption_reason"] == "technical"
    assert data["segments"][0]["status"] == "cancelled"


def test_missed_connection_is_detected():
    data = get_booking("DEMO02").json()
    assert len(data["segments"]) == 2
    connection = data["connections"][0]
    assert connection["airport"] == "DXB"
    assert connection["feasible"] is False
    assert connection["layover_minutes"] < connection["minimum_required_minutes"]


def test_special_cases_are_visible():
    assert get_booking("DEMO04").json()["passenger"]["is_unaccompanied_minor"] is True
    assert get_booking("DEMO05").json()["passenger"]["needs_assistance"] is True


def test_email_is_not_exposed():
    assert "email" not in get_booking("DEMO01").json()["passenger"]


def test_injection_text_is_returned_as_plain_data():
    # The API must not change or hide it. Defending against it is the agent's job (later stage).
    remarks = get_booking("DEMO06").json()["passenger"]["remarks"]
    assert "SYSTEM NOTE" in remarks


def test_flight_status_by_number_and_date():
    flight = get_booking("DEMO01").json()["segments"][0]["flight"]
    response = client.get(f"/flights/{flight['flight_number']}", params={"date": flight["flight_date"]})
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_unknown_flight_returns_404():
    assert client.get("/flights/SD999", params={"date": "2030-01-01"}).status_code == 404


def test_search_flights_on_route():
    flight = get_booking("DEMO01").json()["segments"][0]["flight"]
    response = client.get(
        "/flights",
        params={"origin": flight["origin"], "destination": flight["destination"], "date": flight["flight_date"]},
    )
    assert response.status_code == 200
    assert flight["flight_number"] in [f["flight_number"] for f in response.json()]


def test_bad_airport_code_is_rejected():
    assert client.get("/flights", params={"origin": "KOCHI", "destination": "DXB", "date": "2030-01-01"}).status_code == 422