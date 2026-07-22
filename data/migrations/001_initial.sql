-- Logan AI — Migração Inicial do Banco de Dados
-- SQLite Schema v1

-- Perfil do veículo
CREATE TABLE IF NOT EXISTS vehicle_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Meu Veículo',
    make TEXT,
    model TEXT,
    year INTEGER,
    vin TEXT UNIQUE,
    obd_protocol TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Códigos DTC (pré-carregados)
CREATE TABLE IF NOT EXISTS dtc_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    description_pt TEXT NOT NULL,
    description_en TEXT,
    system TEXT,
    severity TEXT DEFAULT 'warning',
    causes TEXT,  -- JSON array
    solutions TEXT,  -- JSON array
    category TEXT
);

-- Histórico de DTCs detectados
CREATE TABLE IF NOT EXISTS dtc_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER REFERENCES vehicle_profile(id),
    dtc_code TEXT NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cleared_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    notes TEXT,
    FOREIGN KEY (dtc_code) REFERENCES dtc_codes(code)
);

-- Viagens
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER REFERENCES vehicle_profile(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    distance_km REAL DEFAULT 0,
    fuel_consumed_l REAL DEFAULT 0,
    avg_speed_kmh REAL DEFAULT 0,
    max_speed_kmh REAL DEFAULT 0,
    avg_rpm REAL DEFAULT 0,
    driving_score TEXT,
    summary TEXT
);

-- Snapshots de telemetria
CREATE TABLE IF NOT EXISTS telemetry_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER REFERENCES trips(id),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    coolant_temp REAL,
    intake_temp REAL,
    rpm REAL,
    speed REAL,
    throttle REAL,
    fuel_level REAL,
    battery_voltage REAL,
    map_pressure REAL,
    maf_rate REAL,
    lambda_value REAL,
    engine_load REAL
);

-- Cache de respostas de IA
CREATE TABLE IF NOT EXISTS ai_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    model_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    use_count INTEGER DEFAULT 1
);

-- Base de conhecimento
CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_verified INTEGER DEFAULT 0
);

-- Log do sistema
CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT  -- JSON
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_dtc_history_vehicle ON dtc_history(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_dtc_history_code ON dtc_history(dtc_code);
CREATE INDEX IF NOT EXISTS idx_trips_vehicle ON trips(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_trips_start ON trips(start_time);
CREATE INDEX IF NOT EXISTS idx_telemetry_trip ON telemetry_snapshots(trip_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_cache_hash ON ai_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_base(category);
CREATE INDEX IF NOT EXISTS idx_system_log_level ON system_log(level);
CREATE INDEX IF NOT EXISTS idx_system_log_timestamp ON system_log(timestamp);
