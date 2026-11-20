from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta

MIN_TRANSFER = timedelta(hours=1)
MAX_TRANSFER = timedelta(hours=6)
MAX_FLIGHTS = 3
TOP_N = 20


def build_routes(flights, origin, destination, limit=TOP_N):
    by_origin = defaultdict(list)
    for f in flights:
        by_origin[f["origin"]].append(f)
    departures = {}
    for airport, items in by_origin.items():
        items.sort(key=lambda f: f["departure_at"])
        departures[airport] = [f["departure_at"] for f in items]

    found = []

    def extend(path, visited):
        last = path[-1]
        if last["destination"] == destination:
            found.append(list(path))  
            return
        if len(path) == MAX_FLIGHTS:  
            return
        airport = last["destination"]
        items = by_origin.get(airport)
        if not items:
            return
        times = departures[airport]
        lo = bisect_left(times, last["arrival_at"] + MIN_TRANSFER)
        hi = bisect_right(times, last["arrival_at"] + MAX_TRANSFER)
        for nxt in items[lo:hi]:
            if nxt["destination"] in visited:  
                continue
            path.append(nxt)
            visited.add(nxt["destination"])
            extend(path, visited)
            visited.discard(nxt["destination"])
            path.pop()

    for first in by_origin.get(origin, []):
        extend([first], {origin, first["destination"]})

    scored = [(sum(f["price"] for f in r), r) for r in found]
    scored.sort(key=lambda t: (t[0], t[1][0]["departure_at"]))
    return [
        {"total_price": total, "transfers": len(r) - 1, "flights": r}
        for total, r in scored[:limit]
    ]