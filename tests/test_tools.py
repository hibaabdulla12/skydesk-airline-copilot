import json

from app import tools


def test_get_booking_returns_json_safe_data():
    result = tools.get_booking("DEMO01")
    json.dumps(result)  # must not raise: the model receives this as JSON
    assert result["segments"][0]["flight"]["status"] == "cancelled"


def test_get_booking_accepts_lowercase():
    assert "error" not in tools.get_booking("demo01")


def test_get_booking_rejects_bad_pnr():
    assert "error" in tools.get_booking("12")
    assert "error" in tools.get_booking("DEMO01; DROP TABLE bookings")


def test_get_booking_unknown_pnr():
    assert "No booking found" in tools.get_booking("ZZZZZZ")["error"]


def test_missed_connection_visible_to_the_model():
    result = tools.get_booking("DEMO02")
    assert result["connections"][0]["feasible"] is False


def test_get_flight_status_validation():
    assert "error" in tools.get_flight_status("not a flight", "2030-01-01")
    assert "error" in tools.get_flight_status("SD200", "tomorrow")
    assert "No flight" in tools.get_flight_status("SD200", "2030-01-01")["error"]


def test_get_flight_status_works():
    flight = tools.get_booking("DEMO01")["segments"][0]["flight"]
    result = tools.get_flight_status(flight["flight_number"], flight["flight_date"])
    assert result["status"] == "cancelled"


def test_search_alternatives():
    flight = tools.get_booking("DEMO01")["segments"][0]["flight"]
    result = tools.search_alternative_flights(flight["origin"], flight["destination"], flight["flight_date"])
    assert flight["flight_number"] in [f["flight_number"] for f in result["flights"]]


def test_search_alternatives_validation():
    assert "error" in tools.search_alternative_flights("KOCHI", "DXB", "2030-01-01")
    assert "error" in tools.search_alternative_flights("COK", "DXB", "31/12/2030")


def test_run_tool_unknown_tool():
    assert "Unknown tool" in tools.run_tool("delete_everything", {})["error"]


def test_run_tool_wrong_arguments():
    assert "arguments" in tools.run_tool("get_booking", {"wrong_name": "x"})["error"]


def test_run_tool_never_raises(monkeypatch):
    def broken(pnr):
        raise RuntimeError("database exploded")

    monkeypatch.setitem(tools.TOOL_MAP, "get_booking", broken)
    assert "failed" in tools.run_tool("get_booking", {"pnr": "DEMO01"})["error"]