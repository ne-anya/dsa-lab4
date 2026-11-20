import argparse
import asyncio
import math
import random
import time
from datetime import date, timedelta

import httpx

AIRPORTS = [
    "OVB", "SVO", "DME", "VKO", "LED", "KZN", "SVX", "AER", "KRR", "ROV",
    "UFA", "KJA", "IKT", "VVO", "KHV", "GOJ", "KUF", "OMS", "TJM", "CEK",
    "PEE", "MRV", "MMK", "ARH", "YKS", "UUS", "PKC", "GDZ", "MCX", "KGD",
]
FIRST_DATE = date(2026, 11, 1)
DAYS = 120


def next_params(rnd: random.Random) -> dict:
    origin, destination = rnd.sample(AIRPORTS, 2)
    day = FIRST_DATE + timedelta(days=rnd.randrange(DAYS))
    return {"origin": origin, "destination": destination, "date": day.isoformat()}


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = max(1, math.ceil(p / 100 * len(sorted_vals)))
    return sorted_vals[k - 1]


async def timed_get(client, path, params, sink, measure_start):
    t0 = time.perf_counter()
    try:
        r = await client.get(path, params=params)
        ok = r.status_code < 400           
    except httpx.HTTPError:                  
        ok = False
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if t0 >= measure_start:
        sink.append((elapsed_ms, ok))


async def closed_client(client, rnd, sink, measure_start, t_end):
    while time.perf_counter() < t_end:
        await timed_get(client, "/search", next_params(rnd), sink, measure_start)


async def open_generator(client, rnd, sink, measure_start, t_begin, t_end, rate, seed):
    gaps = random.Random(seed + 1)
    tasks = set()
    next_time = t_begin
    while True:
        next_time += gaps.expovariate(rate)
        if next_time >= t_end:
            break
        delay = next_time - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        task = asyncio.create_task(
            timed_get(client, "/search", next_params(rnd), sink, measure_start))
        tasks.add(task)                      
        task.add_done_callback(tasks.discard)
    await asyncio.gather(*tasks)             


async def health_poller(client, sink, measure_start, t_begin, t_end, interval):
    tasks = set()
    next_time = t_begin
    while True:
        next_time += interval
        if next_time >= t_end:
            break
        delay = next_time - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        task = asyncio.create_task(timed_get(client, "/health", None, sink, measure_start))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    await asyncio.gather(*tasks)


def summarize(name, samples, duration):
    times = sorted(t for t, _ in samples)
    errors = sum(1 for _, ok in samples if not ok)
    n = len(samples)
    row = {
        "n": n,
        "rps": n / duration,
        "p50": percentile(times, 50),
        "p95": percentile(times, 95),
        "p99": percentile(times, 99),
        "max": times[-1] if times else float("nan"),
        "err": 100 * errors / n if n else float("nan"),
    }
    print(f"\n{name}")
    print(f"  запросов:        {row['n']}")
    print(f"  запросов в с:    {row['rps']:.2f}")
    print(f"  p50, мс:         {row['p50']:.0f}")
    print(f"  p95, мс:         {row['p95']:.0f}")
    print(f"  p99, мс:         {row['p99']:.0f}")
    print(f"  максимум, мс:    {row['max']:.0f}")
    print(f"  ошибки, %:       {row['err']:.1f}")
    return row


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--mode", choices=["closed", "open"], required=True)
    ap.add_argument("--clients", type=int, default=10, help="C для замкнутого режима")
    ap.add_argument("--rate", type=float, default=5.0, help="запросов в с для открытого режима")
    ap.add_argument("--duration", type=float, default=60, help="длительность замера, с")
    ap.add_argument("--warmup", type=float, default=10, help="прогрев, с (не учитывается)")
    ap.add_argument("--timeout", type=float, default=30, help="тайм-аут клиента, с")
    ap.add_argument("--health-interval", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    search_samples, health_samples = [], []

    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=200)
    async with httpx.AsyncClient(base_url=args.url, timeout=args.timeout, limits=limits) as client, \
               httpx.AsyncClient(base_url=args.url, timeout=args.timeout,
                                 limits=httpx.Limits(max_connections=500)) as hclient:
        t_begin = time.perf_counter()
        measure_start = t_begin + args.warmup
        t_end = measure_start + args.duration

        if args.mode == "closed":
            load = [closed_client(client, rnd, search_samples, measure_start, t_end)
                    for _ in range(args.clients)]
            title = f"ЗАМКНУТЫЙ режим, C = {args.clients}"
        else:
            load = [open_generator(client, rnd, search_samples, measure_start,
                                   t_begin, t_end, args.rate, args.seed)]
            title = f"ОТКРЫТЫЙ режим, {args.rate} запросов/с"

        print(f"{title}; прогрев {args.warmup:.0f} с, замер {args.duration:.0f} с, "
              f"тайм-аут {args.timeout:.0f} с")
        await asyncio.gather(
            *load,
            health_poller(hclient, health_samples, measure_start, t_begin, t_end,
                          args.health_interval),
        )

    s = summarize("/search", search_samples, args.duration)
    h = summarize("/health", health_samples, args.duration)

if __name__ == "__main__":
    asyncio.run(main())