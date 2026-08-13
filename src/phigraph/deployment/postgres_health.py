from __future__ import annotations


def check_postgres_connectivity(dsn: str, *, connect_timeout: int = 3) -> dict[str, str]:
    """Return a non-sensitive PostgreSQL connectivity check result."""
    try:
        import psycopg
    except ImportError:
        return {"status": "error", "reason": "psycopg_not_installed"}

    try:
        with psycopg.connect(dsn, connect_timeout=connect_timeout) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        return {"status": "error", "reason": type(exc).__name__}
    return {"status": "ok"}
