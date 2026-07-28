import pytest

from phigraph.deployment.config import DeploymentSettings


def test_deployment_settings_enforce_shadow_only():
    settings = DeploymentSettings()
    settings.validate()

    with pytest.raises(ValueError):
        DeploymentSettings(shadow_only=False).validate()

    with pytest.raises(ValueError):
        DeploymentSettings(
            real_connectors_enabled=True
        ).validate()
