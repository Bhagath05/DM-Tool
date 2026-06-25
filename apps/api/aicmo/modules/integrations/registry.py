"""Process-wide registry of `IntegrationProvider` instances.

Concrete providers self-register on import by calling
`IntegrationRegistry.register(MyProvider())`. The `providers/__init__.py`
imports every provider module, so a single
`import aicmo.modules.integrations.providers`  # noqa
fully populates the registry.

The service layer never instantiates a provider directly — it goes
through `IntegrationRegistry.get(slug)`. That means swapping a stub
provider for the real implementation in Phase 11 is a one-line change.

Re-registration of the same slug is rejected loudly (raises) so a
naming collision can't silently shadow another provider during test
discovery.
"""

from __future__ import annotations

from aicmo.modules.integrations.providers.base import IntegrationProvider


class UnknownProvider(KeyError):
    """No provider is registered with this slug. Surfaces as 404."""


class DuplicateProvider(RuntimeError):
    """Two providers claim the same slug — programmer error."""


class IntegrationRegistry:
    """Class-level singleton. The state is class-attribute scoped so
    a single import is enough; tests that need an empty registry call
    `_reset_for_tests()`."""

    _providers: dict[str, IntegrationProvider] = {}

    # ---- Mutating API ----

    @classmethod
    def register(cls, provider: IntegrationProvider) -> None:
        if not provider.slug:
            raise ValueError(
                f"Provider {type(provider).__name__} has empty slug — "
                "every provider must set a non-empty `slug` class attr."
            )
        existing = cls._providers.get(provider.slug)
        if existing is not None and existing is not provider:
            raise DuplicateProvider(
                f"Slug {provider.slug!r} is already registered by "
                f"{type(existing).__name__}; cannot register "
                f"{type(provider).__name__}."
            )
        cls._providers[provider.slug] = provider

    # ---- Read API ----

    @classmethod
    def get(cls, slug: str) -> IntegrationProvider:
        try:
            return cls._providers[slug]
        except KeyError as exc:
            raise UnknownProvider(
                f"No integration provider registered for slug {slug!r}."
            ) from exc

    @classmethod
    def has(cls, slug: str) -> bool:
        return slug in cls._providers

    @classmethod
    def all(cls) -> list[IntegrationProvider]:
        """Stable order — alphabetic by (category, display_name).
        Catalogues read the same way every call."""
        return sorted(
            cls._providers.values(),
            key=lambda p: (p.category, p.display_name.lower()),
        )

    # ---- Test-only ----

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Empty the registry. Production code never calls this; tests
        that exercise registration semantics use it to start from a
        known-empty state."""
        cls._providers = {}
