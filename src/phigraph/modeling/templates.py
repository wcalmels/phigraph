from __future__ import annotations

DOMAIN_TEMPLATES = {
    "fleet": {
        "entity_aliases": {
            "truck": ("truck", "camion", "equipo", "patente", "vehiculo"),
            "driver": ("driver", "conductor"),
            "route": ("route", "ruta", "trayecto"),
            "shift": ("shift", "turno"),
            "fuel_station": ("fuel_station", "estacion", "surtidor", "punto_carga"),
        },
        "signal_aliases": (
            "fuel", "combustible", "litros", "fuel_per_ton", "consumo",
            "cycle_time", "tiempo_ciclo", "idle", "ralenti", "toneladas",
        ),
    },
    "mining": {
        "entity_aliases": {
            "equipment": ("equipment", "equipo", "maquina", "machine"),
            "sensor": ("sensor",),
            "process_stage": ("stage", "etapa", "proceso"),
            "material_stream": ("stream", "flujo", "material"),
        },
        "signal_aliases": (
            "vibration", "vibracion", "temperature", "temperatura",
            "current", "corriente", "throughput", "tonelaje", "granulometria",
        ),
    },
    "supply_chain": {
        "entity_aliases": {
            "supplier": ("supplier", "proveedor"),
            "plant": ("plant", "planta"),
            "warehouse": ("warehouse", "bodega"),
            "carrier": ("carrier", "transportista"),
            "port": ("port", "puerto"),
        },
        "signal_aliases": (
            "lead_time", "delay", "retraso", "inventory", "inventario",
            "failure_rate", "quiebre",
        ),
    },
    "cybersecurity": {
        "entity_aliases": {
            "user": ("user", "usuario"),
            "credential": ("credential", "credencial"),
            "device": ("device", "dispositivo", "host"),
            "server": ("server", "servidor"),
            "process": ("process", "proceso"),
        },
        "signal_aliases": (
            "login", "risk", "riesgo", "traffic", "trafico",
            "privilege", "privilegio", "bytes",
        ),
    },
    "fraud": {
        "entity_aliases": {
            "account": ("account", "cuenta"),
            "person": ("person", "persona", "cliente"),
            "device": ("device", "dispositivo"),
            "merchant": ("merchant", "comercio"),
            "beneficiary": ("beneficiary", "beneficiario"),
        },
        "signal_aliases": (
            "amount", "monto", "transaction", "transaccion",
            "velocity", "risk_score", "riesgo",
        ),
    },
    "energy": {
        "entity_aliases": {
            "generator": ("generator", "generador"),
            "substation": ("substation", "subestacion"),
            "transformer": ("transformer", "transformador"),
            "feeder": ("feeder", "alimentador"),
            "load": ("load", "carga"),
        },
        "signal_aliases": (
            "voltage", "voltaje", "current", "corriente",
            "frequency", "frecuencia", "loss", "perdida",
        ),
    },
    "telecom": {
        "entity_aliases": {
            "cell": ("cell", "celda", "antena"),
            "router": ("router",),
            "link": ("link", "enlace"),
            "customer_segment": ("segment", "segmento"),
            "service": ("service", "servicio"),
        },
        "signal_aliases": (
            "latency", "latencia", "packet_loss", "perdida_paquetes",
            "traffic", "trafico", "drop_rate",
        ),
    },
}
