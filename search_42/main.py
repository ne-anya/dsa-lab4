import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import (BigInteger, Column, DateTime, MetaData, Numeric,
                        String, Table, select)
from sqlalchemy.ext.asyncio import create_async_engine

from routes import build_routes


DB_URL = os.getenv(
    "DB_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/flights"
).replace("+psycopg", "+asyncpg")
SUPPLIER_URLS = os.getenv(
    "SUPPLIER_URLS",
    "http://localhost:8101,http://localhost:8102,http://localhost:8103",
).split(",")
SUPPLIER_NAMES = [f"supplier{i}" for i in range(1, len(SUPPLIER_URLS) + 1)]
SUPPLIER_BUDGET_S = 2.0   
RETRY_PAUSE_S = 0.2      

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        timeout=None,   
        limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
    )
    app.state.engine = create_async_engine(DB_URL, pool_size=10, max_overflow=20)
    yield
    await app.state.client.aclose()
    await app.state.engine.dispose()


app = FastAPI(title="Поиск авиаперелётов (асинхронный)", lifespan=lifespan)


async def load_db_flights(engine, day: date) -> list[dict]:
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
    async with engine.connect() as conn:      
        rows = (await conn.execute(stmt)).all()
    return [
        {
            "carrier": r.carrier, "flight_number": r.flight_number,
            "origin": r.origin, "destination": r.destination,
            "departure_at": r.departure_at, "arrival_at": r.arrival_at,
            "price": float(r.price),
        }
        for r in rows
    ]


def parse_flights(data: list[dict]) -> list[dict]:
    return [
        {
            "carrier": f["carrier"], "flight_number": f["flight_number"],
            "origin": f["origin"], "destination": f["destination"],
            "departure_at": datetime.fromisoformat(f["departure_at"]),
            "arrival_at": datetime.fromisoformat(f["arrival_at"]),
            "price": float(f["price"]),
        }
        for f in data
    ]


async def fetch_supplier(client: httpx.AsyncClient, base_url: str, day: date):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SUPPLIER_BUDGET_S
    try:
        async with asyncio.timeout(SUPPLIER_BUDGET_S):
            for attempt in (1, 2):
                try:
                    r = await client.get(f"{base_url}/flights",
                                         params={"date": day.isoformat()})
                    r.raise_for_status()        
                    return parse_flights(r.json())
                except (httpx.HTTPError, ValueError, KeyError):
                    if attempt == 2 or deadline - loop.time() <= RETRY_PAUSE_S:
                        return None
                    await asyncio.sleep(RETRY_PAUSE_S)
    except TimeoutError:
        return None                                
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
    request: Request,
    origin: str = Query(min_length=3, max_length=3),
    destination: str = Query(min_length=3, max_length=3),
    search_date: date = Query(alias="date"),
):
    origin, destination = origin.upper(), destination.upper()
    if origin == destination:
        raise HTTPException(status_code=422, detail="origin и destination совпадают")

    client = request.app.state.client
    engine = request.app.state.engine
    t_start = time.perf_counter()

    results = await asyncio.gather(
        load_db_flights(engine, search_date),
        *[fetch_supplier(client, url, search_date) for url in SUPPLIER_URLS],
        return_exceptions=True,
    )
    t_io = time.perf_counter()

    db_flights, supplier_results = results[0], results[1:]
    if isinstance(db_flights, Exception):
        raise db_flights                 

    all_flights = list(db_flights)
    failed = []
    for name, result in zip(SUPPLIER_NAMES, supplier_results):
        if result is None or isinstance(result, Exception):
            failed.append(name)
        else:
            all_flights.extend(result)

    if len(failed) == len(SUPPLIER_URLS) and not db_flights:
        return JSONResponse(
            status_code=503,
            content={"detail": "Поиск временно недоступен", "failed_suppliers": failed},
        )

    routes = await asyncio.get_running_loop().run_in_executor(ROUTES_POOL, build_routes, all_flights, origin, destination)
    t_end = time.perf_counter()

    return {
        "routes": [route_to_json(r) for r in routes],
        "failed_suppliers": failed,
        "processing_time_ms": round((t_end - t_start) * 1000, 1),
        "timings_ms": {
            "io": round((t_io - t_start) * 1000, 1),       # БД + поставщики вместе
            "routes": round((t_end - t_io) * 1000, 1),
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}