"""Auto-import every provider module so each one self-registers.

Importing this package is the *only* place we wire concrete providers
into the IntegrationRegistry. Service / router / tests import the
registry, never the provider modules directly — that way adding a
new provider is "drop a file in this directory + add one line below."
"""

from aicmo.modules.integrations.providers import (  # noqa: F401
    google_ads,
    hubspot,
    linkedin,
    meta_ads,
    organic,
    pinterest,
    salesforce,
    tiktok,
    youtube,
)
