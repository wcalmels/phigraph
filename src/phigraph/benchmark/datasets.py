from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BenchmarkDataset:
    name: str
    domain: str
    tables: dict[str, pd.DataFrame]
    entity_features: pd.DataFrame
    labels: np.ndarray
    entity_ids: tuple[str, ...]
    causal_entities: tuple[str, ...]
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "domain": self.domain,
            "rows": len(self.entity_features),
            "positive_labels": int(np.sum(self.labels)),
            "causal_entities": list(self.causal_entities),
            "metadata": self.metadata,
        }


def make_synthetic_fleet(
    *,
    n_trucks: int = 80,
    anomaly_fraction: float = 0.10,
    seed: int = 47,
) -> BenchmarkDataset:
    if n_trucks < 20:
        raise ValueError("n_trucks must be >= 20")
    rng = np.random.default_rng(seed)
    trucks = np.array([f"KLG-{1000+i}" for i in range(n_trucks)])
    n_anomalous = max(2, int(round(n_trucks * anomaly_fraction)))
    anomalous_idx = rng.choice(n_trucks, size=n_anomalous, replace=False)
    labels = np.zeros(n_trucks, dtype=int)
    labels[anomalous_idx] = 1

    distance = rng.normal(420, 35, n_trucks).clip(250, 600)
    tonnage = rng.normal(2800, 240, n_trucks).clip(1800, 3800)
    idle_hours = rng.normal(22, 5, n_trucks).clip(5, 50)
    fuel = 0.34 * distance + 0.045 * tonnage + 2.1 * idle_hours
    fuel += rng.normal(0, 12, n_trucks)

    # Coordinated anomaly: elevated fuel, idle, and maintenance recurrence.
    fuel[anomalous_idx] += rng.normal(90, 8, n_anomalous)
    idle_hours[anomalous_idx] += rng.normal(12, 2, n_anomalous)
    failures = rng.poisson(1.2, n_trucks).astype(float)
    failures[anomalous_idx] += rng.integers(2, 5, n_anomalous)

    drivers = np.array([f"D-{i%24:02d}" for i in range(n_trucks)])
    routes = np.array([f"R-{i%8:02d}" for i in range(n_trucks)])
    shifts = np.where(np.arange(n_trucks) % 2 == 0, "day", "night")
    stations = np.array([f"S-{i%4:02d}" for i in range(n_trucks)])

    # Make anomalies structurally coordinated.
    drivers[anomalous_idx] = "D-ANOM"
    shifts[anomalous_idx] = "night"
    stations[anomalous_idx] = "S-ANOM"

    features = pd.DataFrame(
        {
            "entity_id": trucks,
            "distance_km": distance,
            "tonnage": tonnage,
            "idle_hours": idle_hours,
            "fuel_liters": fuel,
            "failures": failures,
            "fuel_per_ton": fuel / tonnage,
            "label": labels,
        }
    )

    fuel_table = pd.DataFrame(
        {
            "camion": trucks,
            "conductor": drivers,
            "turno": shifts,
            "surtidor": stations,
            "litros": fuel,
            "distancia_km": distance,
        }
    )
    trips_table = pd.DataFrame(
        {
            "equipo": [truck.replace("KLG-", "") for truck in trucks],
            "ruta": routes,
            "toneladas": tonnage,
            "tiempo_ralenti": idle_hours,
        }
    )
    maintenance_table = pd.DataFrame(
        {
            "numero_interno": trucks,
            "fallas_30d": failures,
            "taller": np.where(np.arange(n_trucks) % 3 == 0, "T-A", "T-B"),
        }
    )

    causal = tuple(trucks[anomalous_idx].tolist())
    return BenchmarkDataset(
        name="synthetic_fleet_v1",
        domain="fleet",
        tables={
            "fuel": fuel_table,
            "trips": trips_table,
            "maintenance": maintenance_table,
        },
        entity_features=features,
        labels=labels,
        entity_ids=tuple(trucks.tolist()),
        causal_entities=causal,
        metadata={
            "seed": seed,
            "n_trucks": n_trucks,
            "anomaly_fraction": anomaly_fraction,
            "generation": "coordinated fuel-idle-maintenance anomaly",
        },
    )


def make_synthetic_fraud(
    *,
    n_accounts: int = 100,
    anomaly_fraction: float = 0.08,
    seed: int = 47,
) -> BenchmarkDataset:
    if n_accounts < 30:
        raise ValueError("n_accounts must be >= 30")
    rng = np.random.default_rng(seed)
    accounts = np.array([f"ACC-{i:04d}" for i in range(n_accounts)])
    n_anomalous = max(3, int(round(n_accounts * anomaly_fraction)))
    anomalous_idx = rng.choice(n_accounts, size=n_anomalous, replace=False)
    labels = np.zeros(n_accounts, dtype=int)
    labels[anomalous_idx] = 1

    amount = rng.lognormal(mean=6.2, sigma=0.55, size=n_accounts)
    velocity = rng.poisson(7, n_accounts).astype(float)
    devices = np.array([f"DEV-{i%45:03d}" for i in range(n_accounts)])
    merchants = np.array([f"M-{i%20:02d}" for i in range(n_accounts)])
    beneficiaries = np.array([f"B-{i%60:03d}" for i in range(n_accounts)])

    amount[anomalous_idx] *= rng.uniform(3.0, 5.0, n_anomalous)
    velocity[anomalous_idx] += rng.integers(12, 25, n_anomalous)
    devices[anomalous_idx] = "DEV-RING"
    merchants[anomalous_idx] = "M-RING"
    beneficiaries[anomalous_idx] = "B-RING"

    features = pd.DataFrame(
        {
            "entity_id": accounts,
            "amount": amount,
            "velocity": velocity,
            "amount_per_event": amount / np.maximum(velocity, 1),
            "label": labels,
        }
    )
    transactions = pd.DataFrame(
        {
            "account": accounts,
            "device": devices,
            "merchant": merchants,
            "beneficiary": beneficiaries,
            "amount": amount,
            "velocity": velocity,
        }
    )

    return BenchmarkDataset(
        name="synthetic_fraud_v1",
        domain="fraud",
        tables={"transactions": transactions},
        entity_features=features,
        labels=labels,
        entity_ids=tuple(accounts.tolist()),
        causal_entities=tuple(accounts[anomalous_idx].tolist()),
        metadata={
            "seed": seed,
            "n_accounts": n_accounts,
            "anomaly_fraction": anomaly_fraction,
            "generation": "coordinated device-merchant-beneficiary ring",
        },
    )
