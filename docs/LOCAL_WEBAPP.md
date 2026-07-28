# PhiGraph Local Analyst

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[app,dev]"
```

## Start

```powershell
phigraph-web
```

The application opens at:

```text
http://localhost:8501
```

## Supported input

- CSV
- XLSX
- XLSM

The user chooses:

- source node column;
- target node column;
- optional edge weight;
- optional node identifier and numeric signal;
- number of spectral modes;
- hotspot fraction;
- number of matched controls.

## Privacy

The app reads files in local memory and does not upload them to an external service.
The optional Ollama adapter is not required for the web interface.
