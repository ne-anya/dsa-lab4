import os
import time
from datetime import date, datetime, timedelta

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import (BigInteger, Column, DateTime, MetaData, Numeric,
                        String, Table, create_engine, select)

from routes import build_routes

DB_URL = os.getenv("DB_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/flights")
SUPPLIER_URLS = os.getenv(
    "SUPPLIER_URLS",
    "http://localhost:8101,http://localhost:8102,http://localhost:8103",
).split(",")
SUPPLIER_NAMES = [f"supplier{i}" for i in range(1, len(SUPPLIER_URLS) + 1)]
SUPPLIER_BUDGET_S = 2.0   
RETRY_PAUSE_S = 0.2      

engine = create_engine(DB_URL)
metadata = MetaData()
flights_table = Table(
    "flights", metadata,
    Column("id", BigInteger, primary_key=True),
    Column("carrier", String),
    Column("flight_number", String),
    Column("origin", String(3)),
    Column("destination", String(3)),
    Column("departure_at", DateTime),
    Column("arrival_at", DateTime),
    Column("price", Numeric(10, 2)),
)

app = FastAPI(title="Поиск авиаперелётов (синхронный)")


def load_db_flights(day: date) -> list[dict]:
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    stmt = select(
        flights_table.c.carrier, flights_table.c.flight_number,
        flights_table.c.origin, flights_table.c.destination,
        flights_table.c.departure_at, flights_table.c.arrival_at,
        flights_table.c.price,
    ).where(
        flights_table.c.departure_at >= start,   
        flights_table.c.departure_at < end,      
    )
    
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    return [
        {
            "carrier": r.carrier, "flight_number": r.flight_number,
            "origin": r.origin, "destination": r.destination,
            "departure_at": r.departure_at, "arrival_at": r.arrival_at,
            "price": float(r.price),
        }
        for r in rows
    ]


def fetch_supplier(base_url: str, day: date):
    deadline = time.monotonic() + SUPPLIER_BUDGET_S
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            r = requests.get(f"{base_url}/flights",
                             params={"date": day.isoformat()}, timeout=remaining)
            r.raise_for_status()   
            return [
                {
                    "carrier": f["carrier"], "flight_number": f["flight_number"],
                    "origin": f["origin"], "destination": f["destination"],
                    "departure_at": datetime.fromisoformat(f["departure_at"]),
                    "arrival_at": datetime.fromisoformat(f["arrival_at"]),
                    "price": float(f["price"]),
                }
                for f in r.json()
            ]
        except requests.Timeout:
            return None            
        except requests.RequestException:
            if attempt == 2 or deadline - time.monotonic() <= RETRY_PAUSE_S:
                return None
            time.sleep(RETRY_PAUSE_S)
    return None


def route_to_json(route: dict) -> dict:
    return {
        "total_price": route["total_price"],
        "transfers": route["transfers"],
        "flights": [
            {**f, "departure_at": f["departure_at"].isoformat(),
             "arrival_at": f["arrival_at"].isoformat()}
            for f in route["flights"]
        ],
    }


@app.get("/search")
async def search(
    origin: str = Query(min_length=3, max_length=3),
    destination: str = Query(min_length=3, max_length=3),
    search_date: date = Query(alias="date"),
):
    origin, destination = origin.upper(), destination.upper()
    if origin == destination:
        raise HTTPException(status_code=422, detail="origin и destination совпадают")

    t_start = time.perf_counter()

    db_flights = load_db_flights(search_date)
    t_db = time.perf_counter()

    all_flights = list(db_flights)
    failed = []
    for name, url in zip(SUPPLIER_NAMES, SUPPLIER_URLS):
        result = fetch_supplier(url, search_date)
        if result is None:
            failed.append(name)
        else:
            all_flights.extend(result)
    t_suppliers = time.perf_counter()

    if len(failed) == len(SUPPLIER_URLS) and not db_flights:
        return JSONResponse(
            status_code=503,
            content={"detail": "Поиск временно недоступен", "failed_suppliers": failed},
        )

    routes = build_routes(all_flights, origin, destination)
    t_end = time.perf_counter()

    return {
        "routes": [route_to_json(r) for r in routes],
        "failed_suppliers": failed,
        "processing_time_ms": round((t_end - t_start) * 1000, 1),
        "timings_ms": { 
            "db": round((t_db - t_start) * 1000, 1),
            "suppliers": round((t_suppliers - t_db) * 1000, 1),
            "routes": round((t_end - t_suppliers) * 1000, 1),
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}