import asyncio
import os
import random
from datetime import date, datetime, timedelta
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query

SUPPLIER_ID = os.getenv("SUPPLIER_ID", "1")
MEAN_DELAY_MS = float(os.getenv("MEAN_DELAY_MS", "300"))
DELAY_SPREAD = float(os.getenv("DELAY_SPREAD", "0.3"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.05"))
SLOW_RATE = float(os.getenv("SLOW_RATE", "0.0"))
SLOW_DELAY_S = float(os.getenv("SLOW_DELAY_S", "3"))
FLIGHTS_PER_DAY = int(os.getenv("FLIGHTS_PER_DAY", "500"))


AIRPORTS = [
    "OVB", "SVO", "DME", "VKO", "LED", "KZN", "SVX", "AER", "KRR", "ROV",
    "UFA", "KJA", "IKT", "VVO", "KHV", "GOJ", "KUF", "OMS", "TJM", "CEK",
    "PEE", "MRV", "MMK", "ARH", "YKS", "UUS", "PKC", "GDZ", "MCX", "KGD",
]

app = FastAPI(title=f"Поставщик {SUPPLIER_ID}")


@lru_cache(maxsize=256)
def build_flights(day: date) -> list[dict]:
    rnd = random.Random(f"flights-{SUPPLIER_ID}-{day.isoformat()}")
    carrier = f"P{SUPPLIER_ID}"
    midnight = datetime.combine(day, datetime.min.time())
    flights = []
    for _ in range(FLIGHTS_PER_DAY):
        origin, destination = rnd.sample(AIRPORTS, 2)
        departure = midnight + timedelta(minutes=rnd.randrange(24 * 60))
        duration = rnd.randint(60, 360)
        arrival = departure + timedelta(minutes=duration)
        price = round((2000 + duration * 15 + rnd.uniform(0, 3000)) / 10) * 10
        flights.append({
            "carrier": carrier,
            "flight_number": f"{carrier}{rnd.randint(100, 9999)}",
            "origin": origin,
            "destination": destination,
            "departure_at": departure.isoformat(),
            "arrival_at": arrival.isoformat(),
            "price": price,
        })
    return flights


@app.get("/flights")
async def get_flights(flight_date: date = Query(alias="date")):
    if random.random() < SLOW_RATE:
        delay = SLOW_DELAY_S
    else:
        delay = MEAN_DELAY_MS * random.uniform(1 - DELAY_SPREAD, 1 + DELAY_SPREAD) / 1000

    await asyncio.sleep(delay)

    if random.random() < ERROR_RATE:
        raise HTTPException(status_code=500, detail="supplier error")

    return build_flights(flight_date)


@app.get("/health")
async def health():
    return {"status": "ok"}