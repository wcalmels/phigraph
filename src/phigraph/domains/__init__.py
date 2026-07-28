"""Domain adapters for PhiGraph agent workflows."""

from .base import DomainProfile, get_domain_profile
from .profiles import DOMAIN_PROFILES

__all__ = ["DomainProfile", "get_domain_profile", "DOMAIN_PROFILES"]
