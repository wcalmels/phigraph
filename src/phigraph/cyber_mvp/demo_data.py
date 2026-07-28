from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import pandas as pd


def generate_demo_events(
    *,
    normal_events: int = 180,
    seed: int = 47,
) -> pd.DataFrame:
    rng = random.Random(seed)
    start = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    users = [f"user-{index:02d}" for index in range(1, 13)]
    devices = [f"pc-{index:02d}" for index in range(1, 13)]
    rows = []

    for index in range(normal_events):
        user_index = index % len(users)
        user = users[user_index]
        device = devices[user_index]
        timestamp = start + timedelta(minutes=5 * index)
        event_type = rng.choices(
            ["login", "process_start", "data_access", "failed_login"],
            weights=[55, 22, 18, 5],
        )[0]
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "user_id": user,
                "device_id": device,
                "event_type": event_type,
                "source_ip": f"10.0.0.{20 + user_index}",
                "destination_ip": (
                    f"10.0.1.{10 + rng.randrange(4)}"
                    if event_type == "data_access"
                    else ""
                ),
                "process_name": (
                    rng.choice(["chrome.exe", "outlook.exe", "explorer.exe"])
                    if event_type == "process_start"
                    else ""
                ),
                "resource_id": (
                    rng.choice(["share-finance", "share-operations", "erp"])
                    if event_type == "data_access"
                    else ""
                ),
                "risk_score": round(
                    rng.uniform(0.04, 0.28)
                    + (0.15 if event_type == "failed_login" else 0),
                    3,
                ),
                "outcome": "normal",
            }
        )

    attack_start = start + timedelta(minutes=5 * normal_events)
    rows.extend(
        [
            {
                "timestamp": attack_start.isoformat(),
                "user_id": "user-03",
                "device_id": "pc-11",
                "event_type": "login",
                "source_ip": "10.0.0.87",
                "destination_ip": "",
                "process_name": "",
                "resource_id": "",
                "risk_score": 0.81,
                "outcome": "confirmed_attack",
            },
            {
                "timestamp": (
                    attack_start + timedelta(minutes=2)
                ).isoformat(),
                "user_id": "user-03",
                "device_id": "pc-11",
                "event_type": "privilege_change",
                "source_ip": "10.0.0.87",
                "destination_ip": "10.0.1.12",
                "process_name": "powershell.exe",
                "resource_id": "admin-console",
                "risk_score": 0.96,
                "outcome": "confirmed_attack",
            },
            {
                "timestamp": (
                    attack_start + timedelta(minutes=4)
                ).isoformat(),
                "user_id": "user-03",
                "device_id": "server-03",
                "event_type": "remote_access",
                "source_ip": "10.0.0.87",
                "destination_ip": "10.0.1.50",
                "process_name": "psexec.exe",
                "resource_id": "sensitive-share",
                "risk_score": 0.98,
                "outcome": "confirmed_attack",
            },
        ]
    )
    return pd.DataFrame(rows)
