import os
import random
from datetime import date, datetime, timedelta

import psycopg

DSN = os.getenv("DB_DSN", "postgresql://postgres:postgres@localhost:5432/flights")
START_DATE = date.fromisoformat(os.getenv("START_DATE", "2026-11-01"))
DAYS = 120
FLIGHTS_PER_DAY = 1500
SEED = 42

AIRPORTS = [
    "OVB", "SVO", "DME", "VKO", "LED", "KZN", "SVX", "AER", "KRR", "ROV",
    "UFA", "KJA", "IKT", "VVO", "KHV", "GOJ", "KUF", "OMS", "TJM", "CEK",
    "PEE", "MRV", "MMK", "ARH", "YKS", "UUS", "PKC", "GDZ", "MCX", "KGD",
]
CARRIERS = ["N1", "N2", "N3", "N4", "N5"]  # условные перевозчики


def generate_flights():
    rnd = random.Random(SEED) 
    for day_offset in range(DAYS):
        day = START_DATE + timedelta(days=day_offset)
        midnight = datetime.combine(day, datetime.min.time())
        for _ in range(FLIGHTS_PER_DAY):
            origin, destination = rnd.sample(AIRPORTS, 2) 
            carrier = rnd.choice(CARRIERS)
            number = f"{carrier}{rnd.randint(100, 9999)}"
            departure = midnight + timedelta(minutes=rnd.randrange(24 * 60))
            duration = rnd.randint(60, 360)  # полёт от 1 до 6 часов
            arrival = departure + timedelta(minutes=duration)
            price = round((2000 + duration * 15 + rnd.uniform(0, 3000)) / 10) * 10
            yield (carrier, number, origin, destination, departure, arrival, price)


def main():
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE flights RESTART IDENTITY")
            with cur.copy(
                "COPY flights (carrier, flight_number, origin, destination, "
                "departure_at, arrival_at, price) FROM STDIN"
            ) as copy:
                for row in generate_flights():
                    copy.write_row(row)
            cur.execute("SELECT count(*), min(departure_at), max(departure_at) FROM flights")
            print("Загружено (всего, первый вылет, последний вылет):", cur.fetchone())


if __name__ == "__main__":
    main()