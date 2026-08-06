"""Central registry for ATS provider implementations."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from ai_job_market.config import GREENHOUSE_COMPANIES
from ai_job_market.providers.base import ATSProvider
from ai_job_market.providers.greenhouse import GreenhouseProvider


ProviderFactory = Callable[[], ATSProvider]


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    """Factory and organization configuration for one registered ATS."""

    factory: ProviderFactory
    companies: tuple[str, ...]


# Add a new ATS by implementing providers/<name>.py and adding one registration
# here. The pipeline and downstream ETL consume the shared JobPosting contract.
PROVIDER_REGISTRY: Final[dict[str, ProviderRegistration]] = {
    GreenhouseProvider.name: ProviderRegistration(
        factory=GreenhouseProvider,
        companies=GREENHOUSE_COMPANIES,
    ),
}


def available_providers() -> tuple[str, ...]:
    """Return registered provider names in deterministic order."""
    return tuple(sorted(PROVIDER_REGISTRY))


def create_provider(name: str) -> ATSProvider:
    """Instantiate one registered provider by name."""
    try:
        return PROVIDER_REGISTRY[name].factory()
    except KeyError as error:
        available = ", ".join(available_providers())
        raise ValueError(
            f"Unknown provider '{name}'. Registered providers: {available}"
        ) from error


def companies_for_provider(name: str) -> tuple[str, ...]:
    """Return configured organization identifiers for one registered provider."""
    try:
        return PROVIDER_REGISTRY[name].companies
    except KeyError as error:
        available = ", ".join(available_providers())
        raise ValueError(
            f"Unknown provider '{name}'. Registered providers: {available}"
        ) from error
