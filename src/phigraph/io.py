from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO, TextIO

import pandas as pd


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}


@dataclass(frozen=True)
class LoadedTable:
    frame: pd.DataFrame
    source_name: str
    sheet_name: str | None = None


def list_excel_sheets(source: str | Path | BinaryIO) -> list[str]:
    with pd.ExcelFile(source, engine="openpyxl") as workbook:
        return list(workbook.sheet_names)


def load_table(
    source: str | Path | BinaryIO | TextIO,
    *,
    filename: str | None = None,
    sheet_name: str | int | None = 0,
    csv_separator: str | None = None,
    encoding: str = "utf-8",
) -> LoadedTable:
    """Load CSV or Excel from disk or an uploaded file-like object."""
    name = filename or getattr(source, "name", None) or str(source)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported file type {suffix!r}. Supported: {sorted(SUPPORTED_SUFFIXES)}"
        )

    if suffix == ".csv":
        if hasattr(source, "seek"):
            source.seek(0)
        separator = csv_separator or ","
        frame = pd.read_csv(source, sep=separator, encoding=encoding)
        return LoadedTable(frame=frame, source_name=Path(name).name)

    if hasattr(source, "seek"):
        source.seek(0)
    frame = pd.read_excel(source, sheet_name=sheet_name, engine="openpyxl")
    resolved_sheet = str(sheet_name) if sheet_name is not None else None
    return LoadedTable(
        frame=frame,
        source_name=Path(name).name,
        sheet_name=resolved_sheet,
    )


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")
