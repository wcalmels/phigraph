from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import gzip
import hashlib
import json
from typing import Iterable

from .config import LANLReductionConfig
from .schemas import SOURCE_SCHEMAS


@dataclass(frozen=True)
class RedTeamEvent:
    time: int
    user: str
    source_computer: str
    destination_computer: str

    def to_dict(self) -> dict:
        return asdict(self)


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_redteam(path: Path) -> list[RedTeamEvent]:
    rows: list[RedTeamEvent] = []
    with _open_text(path) as handle:
        reader = csv.reader(handle)
        for raw in reader:
            if len(raw) != 4:
                continue
            rows.append(
                RedTeamEvent(
                    time=int(raw[0]),
                    user=raw[1],
                    source_computer=raw[2],
                    destination_computer=raw[3],
                )
            )
    rows.sort(key=lambda row: row.time)
    return rows


def _merge_intervals(
    intervals: Iterable[tuple[int, int]],
) -> list[tuple[int, int]]:
    ordered = sorted(intervals)
    merged: list[list[int]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def build_windows(
    events: list[RedTeamEvent],
    config: LANLReductionConfig,
) -> list[dict]:
    raw = [
        (
            max(1, event.time - config.pre_seconds),
            event.time + config.post_seconds,
        )
        for event in events
    ]
    intervals = (
        _merge_intervals(raw)
        if config.merge_overlapping_windows
        else raw
    )
    windows = []
    for index, (start, end) in enumerate(intervals, start=1):
        related = [
            event.to_dict()
            for event in events
            if start <= event.time <= end
        ]
        windows.append(
            {
                "window_id": f"attack-window-{index:04d}",
                "start": start,
                "end": end,
                "duration_seconds": end - start + 1,
                "redteam_events": related,
            }
        )
    return windows


def build_entity_set(events: list[RedTeamEvent]) -> set[str]:
    entities: set[str] = set()
    for event in events:
        entities.update(
            {
                event.user,
                event.source_computer,
                event.destination_computer,
            }
        )
    return entities


def _in_windows(timestamp: int, windows: list[dict]) -> bool:
    return any(
        window["start"] <= timestamp <= window["end"]
        for window in windows
    )


def _entity_match(
    source: str,
    row: list[str],
    entities: set[str],
) -> bool:
    schema = SOURCE_SCHEMAS[source]
    values = {
        schema[index]: value
        for index, value in enumerate(row)
        if index < len(schema)
    }
    entity_fields = {
        "auth": (
            "source_user",
            "destination_user",
            "source_computer",
            "destination_computer",
        ),
        "proc": ("user", "computer"),
        "flows": ("source_computer", "destination_computer"),
        "dns": ("source_computer", "resolved_computer"),
    }[source]
    return any(values.get(field) in entities for field in entity_fields)


def reduce_source(
    source: str,
    input_path: Path,
    output_path: Path,
    windows: list[dict],
    entities: set[str],
    config: LANLReductionConfig,
) -> dict:
    expected = len(SOURCE_SCHEMAS[source])
    written = malformed = scanned = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _open_text(input_path) as input_handle, output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output_handle:
        reader = csv.reader(input_handle)
        writer = csv.writer(output_handle)
        writer.writerow(SOURCE_SCHEMAS[source] + ["source_line_number"])

        for line_number, row in enumerate(reader, start=1):
            scanned += 1
            if len(row) != expected:
                malformed += 1
                continue
            try:
                timestamp = int(row[0])
            except ValueError:
                malformed += 1
                continue
            if not _in_windows(timestamp, windows):
                continue
            if (
                config.entity_filter
                and not _entity_match(source, row, entities)
            ):
                continue
            writer.writerow(row + [line_number])
            written += 1
            if (
                config.max_events_per_source is not None
                and written >= config.max_events_per_source
            ):
                break

    return {
        "source": source,
        "input_file": input_path.name,
        "output_file": output_path.name,
        "scanned_rows": scanned,
        "written_rows": written,
        "malformed_rows": malformed,
        "truncated": (
            config.max_events_per_source is not None
            and written >= config.max_events_per_source
        ),
    }


def write_labels(
    redteam: list[RedTeamEvent],
    output_path: Path,
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "time",
                "user",
                "source_computer",
                "destination_computer",
                "label",
            ],
        )
        writer.writeheader()
        for event in redteam:
            payload = event.to_dict()
            payload["label"] = "redteam"
            writer.writerow(payload)


def reduce_lanl_dataset(
    raw_dir: str | Path,
    output_dir: str | Path,
    config: LANLReductionConfig,
) -> dict:
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    redteam_path = next(
        (
            candidate
            for candidate in (
                raw_dir / "redteam.txt.gz",
                raw_dir / "redteam.txt",
            )
            if candidate.exists()
        ),
        None,
    )
    if redteam_path is None:
        raise FileNotFoundError("redteam.txt.gz or redteam.txt is required")

    redteam = load_redteam(redteam_path)
    windows = build_windows(redteam, config)
    entities = build_entity_set(redteam)

    (output_dir / "windows.json").write_text(
        json.dumps(windows, indent=2),
        encoding="utf-8",
    )
    write_labels(redteam, output_dir / "redteam_labels.csv")

    source_names = {
        "auth": ("auth.txt.gz", "auth.txt"),
        "proc": ("proc.txt.gz", "proc.txt"),
        "flows": ("flows.txt.gz", "flows.txt"),
        "dns": ("dns.txt.gz", "dns.txt"),
    }
    source_reports = []
    checksums = {
        "redteam": {
            "file": redteam_path.name,
            "sha256": _sha256(redteam_path),
        }
    }

    for source in config.include_sources:
        candidates = [
            raw_dir / name
            for name in source_names[source]
        ]
        input_path = next(
            (path for path in candidates if path.exists()),
            None,
        )
        if input_path is None:
            source_reports.append(
                {
                    "source": source,
                    "status": "missing",
                    "expected": list(source_names[source]),
                }
            )
            continue
        checksums[source] = {
            "file": input_path.name,
            "sha256": _sha256(input_path),
        }
        source_reports.append(
            reduce_source(
                source,
                input_path,
                output_dir / f"{source}_reduced.csv",
                windows,
                entities,
                config,
            )
        )

    manifest = {
        "dataset": "LANL Comprehensive Multi-Source Cyber-Security Events",
        "profile": config.profile_name,
        "config": config.to_dict(),
        "redteam_events": len(redteam),
        "attack_windows": len(windows),
        "redteam_entities": len(entities),
        "sources": source_reports,
        "checksums": checksums,
        "provenance": {
            "timestamp_resolution": "1 second",
            "epoch": "de-identified offset beginning at 1",
            "selection": "windows centered on official redteam events",
            "entity_filter": config.entity_filter,
            "lineage_column": "source_line_number",
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest
