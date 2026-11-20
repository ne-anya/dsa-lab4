CREATE TABLE IF NOT EXISTS flights (
    id            BIGSERIAL PRIMARY KEY,
    carrier       TEXT         NOT NULL, 
    flight_number TEXT         NOT NULL, 
    origin        CHAR(3)      NOT NULL,  
    destination   CHAR(3)      NOT NULL, 
    departure_at  TIMESTAMP    NOT NULL, 
    arrival_at    TIMESTAMP    NOT NULL, 
    price         NUMERIC(10,2) NOT NULL 
);

CREATE INDEX IF NOT EXISTS idx_flights_departure_at ON flights (departure_at);