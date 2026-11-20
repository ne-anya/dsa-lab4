from datetime import datetime, timedelta

from routes import build_routes

BASE = datetime(2026, 11, 10)


def fl(origin, dest, dep_h, dur_min, price):
    dep = BASE + timedelta(hours=dep_h)
    return {"carrier": "T", "flight_number": f"T{origin}{dest}{dep_h}",
            "origin": origin, "destination": dest,
            "departure_at": dep, "arrival_at": dep + timedelta(minutes=dur_min),
            "price": price}


def test_direct():
    r = build_routes([fl("A", "C", 8, 120, 100)], "A", "C")
    assert len(r) == 1 and r[0]["transfers"] == 0 and r[0]["total_price"] == 100


def test_transfer_window():
    # A->B прилетает в 10:00; пересадка 30 мин, 1 ч, 6 ч, 6 ч 1 мин
    first = fl("A", "B", 8, 120, 100)
    for gap_min, ok in [(30, False), (60, True), (360, True), (361, False)]:
        dep_h = 10 + gap_min / 60
        second = fl("B", "C", dep_h, 60, 50)
        r = build_routes([first, second], "A", "C")
        assert (len(r) == 1) == ok, gap_min
        if ok:
            assert r[0]["total_price"] == 150 and r[0]["transfers"] == 1


def test_no_repeated_airports():
    # A->B, B->A, A->C: маршрут A->B->A->C запрещён (A повторяется)
    flights = [fl("A", "B", 8, 60, 10), fl("B", "A", 10, 60, 10), fl("A", "C", 13, 60, 10)]
    r = build_routes(flights, "A", "C")
    assert all(x["transfers"] == 0 for x in r) or r == []
    assert not any(x["transfers"] > 0 for x in r)


def test_max_two_transfers():
    # A->B->C->D->E: это 3 пересадки, маршрута быть не должно
    flights = [fl("A", "B", 0, 60, 1), fl("B", "C", 2, 60, 1),
               fl("C", "D", 4, 60, 1), fl("D", "E", 6, 60, 1)]
    assert build_routes(flights, "A", "E") == []
    # а A->D (2 пересадки) находится
    assert len(build_routes(flights, "A", "D")) == 1


def test_top_n_cheapest_sorted():
    flights = [fl("A", "C", h % 24, 60, 1000 - h) for h in range(30)]
    r = build_routes(flights, "A", "C", limit=20)
    prices = [x["total_price"] for x in r]
    assert len(r) == 20 and prices == sorted(prices)


def test_empty():
    assert build_routes([], "A", "C") == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)