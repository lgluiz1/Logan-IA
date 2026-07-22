# Logan AI — Seed DTC Database

"""
Script para popular o banco SQLite com códigos de erro DTC (Renault/Genéricos).
"""

import json
import sqlite3
from pathlib import Path

# Lista de alguns erros comuns (genéricos e Renault)
DTC_CODES = [
    {
        "code": "P0300",
        "description_pt": "Falha de ignição em múltiplos cilindros",
        "description_en": "Random/Multiple Cylinder Misfire Detected",
        "system": "Motor",
        "severity": "critical",
        "causes": json.dumps(["Velas gastas", "Bobina de ignição defeituosa", "Bicos injetores entupidos", "Combustível adulterado"]),
        "solutions": json.dumps(["Trocar velas", "Checar bobina", "Limpar bicos"]),
        "category": "engine"
    },
    {
        "code": "P0301",
        "description_pt": "Falha de ignição no cilindro 1",
        "description_en": "Cylinder 1 Misfire Detected",
        "system": "Motor",
        "severity": "critical",
        "causes": json.dumps(["Vela do cilindro 1", "Cabo de vela", "Injetor"]),
        "solutions": json.dumps(["Trocar vela", "Verificar compressão"]),
        "category": "engine"
    },
    {
        "code": "P0130",
        "description_pt": "Mau funcionamento no circuito da Sonda Lambda (Sensor O2)",
        "description_en": "O2 Sensor Circuit Malfunction",
        "system": "Exaustão",
        "severity": "warning",
        "causes": json.dumps(["Sensor de oxigênio sujo ou pifado", "Fiação rompida", "Fuga no escapamento"]),
        "solutions": json.dumps(["Substituir sonda lambda", "Inspecionar fiação"]),
        "category": "emissions"
    },
    {
        "code": "P0171",
        "description_pt": "Mistura muito pobre (Banco 1)",
        "description_en": "System Too Lean (Bank 1)",
        "system": "Injeção",
        "severity": "warning",
        "causes": json.dumps(["Falta de pressão de combustível", "Entrada falsa de ar", "Bico entupido"]),
        "solutions": json.dumps(["Checar bomba de combustível", "Procurar vazamentos de vácuo"]),
        "category": "fuel"
    },
    {
        "code": "P0113",
        "description_pt": "Tensão alta no sensor de temperatura do ar de admissão (IAT)",
        "description_en": "Intake Air Temperature Sensor 1 Circuit High",
        "system": "Sensores",
        "severity": "warning",
        "causes": json.dumps(["Sensor IAT com defeito", "Conector solto"]),
        "solutions": json.dumps(["Conectar ou trocar sensor IAT"]),
        "category": "sensors"
    },
    {
        "code": "P0420",
        "description_pt": "Eficiência do catalisador abaixo do limite",
        "description_en": "Catalyst System Efficiency Below Threshold",
        "system": "Exaustão",
        "severity": "warning",
        "causes": json.dumps(["Catalisador degradado", "Combustível de má qualidade crônica"]),
        "solutions": json.dumps(["Trocar catalisador"]),
        "category": "emissions"
    }
]

def seed_db():
    db_path = Path("/app/db/logan.db")
    if not db_path.parent.exists():
        # Para rodar localmente no PC sem o docker
        db_path = Path("db/logan.db")
        db_path.parent.mkdir(exist_ok=True)
        
    print(f"Conectando ao banco em {db_path}...")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    print("Garantindo que a tabela existe...")
    # Executa a migration inicial (se ainda não existir)
    migration_path = Path("data/migrations/001_initial.sql")
    if migration_path.exists():
        cursor.executescript(migration_path.read_text(encoding="utf-8"))
    
    print("Limpando DTCs antigos...")
    cursor.execute("DELETE FROM dtc_codes")
    
    print(f"Inserindo {len(DTC_CODES)} códigos de erro DTC...")
    for dtc in DTC_CODES:
        cursor.execute(
            """
            INSERT INTO dtc_codes (code, description_pt, description_en, system, severity, causes, solutions, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dtc["code"], dtc["description_pt"], dtc["description_en"], dtc["system"],
                dtc["severity"], dtc["causes"], dtc["solutions"], dtc["category"]
            )
        )
    
    conn.commit()
    conn.close()
    print("Seed concluído com sucesso!")

if __name__ == "__main__":
    seed_db()
