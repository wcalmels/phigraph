"""
tests/test_vps_v03_contract.py

Contract tests for VPS Private Staging v0.3 local Docker integration drill.

Validates:
- PHIGRAPH_API_KEY environment variable contract
- Docker Compose configuration for SQLite data persistence
- Read-only filesystem enforcement with writable data volume
- SHADOW_ONLY and connector disabled flags
- Volume preservation and naming conventions
- Documentation and production readiness statements
"""

import os
import yaml
import pytest


class TestVPSv03APIKeyContract:
    """PHIGRAPH_API_KEY environment variable contract."""

    def test_phigraph_api_key_in_vps_env_example(self):
        """PHIGRAPH_API_KEY must exist in deploy/vps.env.example."""
        vps_env_path = "deploy/vps.env.example"
        assert os.path.exists(vps_env_path), f"{vps_env_path} does not exist"

        with open(vps_env_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "PHIGRAPH_API_KEY" in content, (
            "PHIGRAPH_API_KEY not found in deploy/vps.env.example"
        )
        assert "replace-with-runtime-api-secret" in content, (
            "PHIGRAPH_API_KEY placeholder value not found"
        )

    def test_compose_injects_api_key_fail_fast(self):
        """Docker Compose must inject PHIGRAPH_API_KEY with fail-fast behavior."""
        compose_path = "docker-compose.vps-staging.yml"
        assert os.path.exists(compose_path), f"{compose_path} does not exist"

        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        env_vars = api_service.get("environment", {})

        # Check for fail-fast pattern: ${VAR:?error_msg}
        api_key_value = env_vars.get("PHIGRAPH_API_KEY")
        assert api_key_value is not None, (
            "PHIGRAPH_API_KEY not found in api service environment"
        )
        assert "${PHIGRAPH_API_KEY:?" in api_key_value, (
            f"PHIGRAPH_API_KEY must use fail-fast syntax; got: {api_key_value}"
        )


class TestVPSv03ComposeDatabaseContract:
    """Docker Compose database and data persistence contract."""

    def test_compose_sets_sqlite_database_url(self):
        """PHIGRAPH_DATABASE_URL must be explicitly set to SQLite path."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        env_vars = api_service.get("environment", {})

        db_url = env_vars.get("PHIGRAPH_DATABASE_URL")
        assert db_url is not None, "PHIGRAPH_DATABASE_URL not found in api service"
        assert "sqlite" in db_url.lower(), (
            f"PHIGRAPH_DATABASE_URL must point to SQLite; got: {db_url}"
        )
        assert "/app/data" in db_url, (
            f"PHIGRAPH_DATABASE_URL must reference /app/data; got: {db_url}"
        )

    def test_compose_mounts_api_data_volume(self):
        """API service must mount phigraph-api-data volume at /app/data."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        volumes = api_service.get("volumes", [])

        assert volumes, "API service has no volumes configured"
        assert any(
            "phigraph-api-data:/app/data" in str(v) for v in volumes
        ), (
            f"phigraph-api-data:/app/data not found in volumes; got: {volumes}"
        )

    def test_compose_declares_global_api_data_volume(self):
        """Global phigraph-api-data volume must be declared."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        volumes = compose.get("volumes", {})
        assert "phigraph-api-data" in volumes, (
            f"phigraph-api-data not found in global volumes; got: {list(volumes.keys())}"
        )

    def test_api_service_keeps_read_only_true(self):
        """API service must retain read_only: true enforcement."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        read_only = api_service.get("read_only")

        assert read_only is True, (
            f"API service read_only must be True; got: {read_only}"
        )


class TestVPSv03ShadowAndConnectorContract:
    """SHADOW_ONLY and real connectors disabled contract."""

    def test_compose_sets_shadow_only_true(self):
        """PHIGRAPH_SHADOW_ONLY must be explicitly set to 'true'."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        env_vars = api_service.get("environment", {})

        shadow_only = env_vars.get("PHIGRAPH_SHADOW_ONLY")
        assert shadow_only == "true", (
            f"PHIGRAPH_SHADOW_ONLY must be 'true'; got: {shadow_only}"
        )

    def test_compose_sets_real_connectors_disabled(self):
        """PHIGRAPH_REAL_CONNECTORS_ENABLED must be explicitly set to 'false'."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        env_vars = api_service.get("environment", {})

        connectors_enabled = env_vars.get("PHIGRAPH_REAL_CONNECTORS_ENABLED")
        assert connectors_enabled == "false", (
            f"PHIGRAPH_REAL_CONNECTORS_ENABLED must be 'false'; got: {connectors_enabled}"
        )


class TestVPSv03DocumentationContract:
    """Documentation and production readiness statements."""

    def test_drill_runbook_exists(self):
        """VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md must exist."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        assert os.path.exists(runbook_path), f"{runbook_path} does not exist"

    def test_runbook_states_not_production_ready(self):
        """Runbook must explicitly state this is not production ready."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for explicit production readiness disclaimer
        assert "does not constitute production readiness" in content.lower(), (
            "Runbook must state this does not constitute production readiness"
        )

    def test_runbook_records_shadow_only(self):
        """Runbook must document SHADOW_ONLY=true."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "SHADOW_ONLY" in content, (
            "Runbook must record SHADOW_ONLY=true"
        )
        assert "shadow_only=true" in content or "SHADOW_ONLY=true" in content, (
            "Runbook must explicitly mention shadow_only=true mode"
        )

    def test_runbook_records_real_connectors_disabled(self):
        """Runbook must document PHIGRAPH_REAL_CONNECTORS_ENABLED=false."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "PHIGRAPH_REAL_CONNECTORS_ENABLED" in content, (
            "Runbook must record PHIGRAPH_REAL_CONNECTORS_ENABLED"
        )
        assert "=false" in content or "disabled" in content.lower(), (
            "Runbook must state real connectors are disabled"
        )

    def test_runbook_records_g4_compatible(self):
        """Runbook must document G4 COMPATIBLE state."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "COMPATIBLE" in content, (
            "Runbook must record G4 COMPATIBLE state"
        )
        assert "catalog_valid" in content or "catalog valid" in content.lower(), (
            "Runbook must record catalog validity"
        )

    def test_runbook_records_preserved_volumes(self):
        """Runbook must document both preserved volumes."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "phigraph_phigraph-postgres-data" in content, (
            "Runbook must record postgres data volume preservation"
        )
        assert "phigraph_phigraph-api-data" in content, (
            "Runbook must record api data volume preservation"
        )

    def test_runbook_documents_shutdown_without_down_v(self):
        """Runbook must explicitly prohibit docker compose down -v."""
        runbook_path = "docs/operations/VPS_PRIVATE_STAGING_V03_LOCAL_DRILL.md"
        with open(runbook_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Requirement 1: Must mention literal "docker compose down"
        assert "docker compose down" in content, (
            "Runbook must mention literal 'docker compose down' command"
        )

        # Requirement 2: Must mention literal "docker compose down -v"
        assert "docker compose down -v" in content, (
            "Runbook must mention literal 'docker compose down -v' command"
        )

        # Requirement 3: Must clearly prohibit -v flag using semantic keywords
        # Look for negative prescriptive language in context of -v flag
        prohibition_keywords = (
            "must not",
            "do not",
            "never",
            "should not",
            "without -v",
            "explicitly prohibit",
            "avoid",
        )
        lower_content = content.lower()
        found_prohibition = any(keyword in lower_content for keyword in prohibition_keywords)

        assert found_prohibition, (
            f"Runbook must explicitly prohibit -v flag using semantic language "
            f"(e.g., 'must not', 'do not', 'never', 'without -v', etc.). "
            f"Found prohibition keywords: {prohibition_keywords}"
        )


class TestVPSv03VolumePreservationContract:
    """Volume preservation and naming contract."""

    def test_postgres_data_volume_declared(self):
        """PostgreSQL data volume must be declared."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        volumes = compose.get("volumes", {})
        assert "phigraph-postgres-data" in volumes, (
            "phigraph-postgres-data volume must be declared"
        )

    def test_both_data_volumes_in_compose(self):
        """Both phigraph-postgres-data and phigraph-api-data must be declared."""
        compose_path = "docker-compose.vps-staging.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        volumes = compose.get("volumes", {})
        expected_volumes = ["phigraph-postgres-data", "phigraph-api-data"]

        for vol in expected_volumes:
            assert vol in volumes, f"Volume {vol} not declared in compose"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
