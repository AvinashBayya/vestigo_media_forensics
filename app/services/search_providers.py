"""Reverse-image search provider registry (M5, D22).

Manual-first only: Vestigo opens a provider's plain landing page and the analyst uploads the image
there themselves. The landing URLs carry no query parameters and nothing derived from evidence; the
backend makes no request to any provider. Every provider is disabled until the analyst enables it
in Settings (05-SECURITY-PRIVACY.md §4). The registry is a static list by design — adding a
provider is a code change, and paid or official API integrations each need their own approval.
"""

from pydantic import BaseModel

# Shown before any provider page is opened, and with the providers listing.
SHARING_WARNING = (
    "Opening a provider page sends nothing: it is the provider's plain landing page with no "
    "information about your evidence. If you then upload the image there yourself, you are "
    "sharing that media with the external service under its own terms, outside Vestigo's "
    "control - Vestigo cannot observe, record, or undo anything that happens on the provider's "
    "site."
)


class SearchProvider(BaseModel):
    key: str
    name: str
    landing_url: str
    terms_url: str
    # How to run a manual search on the provider's page, written for the analyst.
    instructions: str


PROVIDERS: tuple[SearchProvider, ...] = (
    SearchProvider(
        key="google_lens",
        name="Google Lens",
        landing_url="https://lens.google.com/",
        terms_url="https://policies.google.com/terms",
        instructions=(
            "On the Google Lens page, drag the downloaded image in (or click 'upload a file') "
            "and review the visually similar results."
        ),
    ),
    SearchProvider(
        key="bing_visual",
        name="Bing Visual Search",
        landing_url="https://www.bing.com/visualsearch",
        terms_url="https://www.microsoft.com/servicesagreement",
        instructions=(
            "On the Bing Visual Search page, drag the downloaded image into the search box or "
            "use 'browse' to upload it."
        ),
    ),
    SearchProvider(
        key="tineye",
        name="TinEye",
        landing_url="https://tineye.com/",
        terms_url="https://tineye.com/terms",
        instructions=(
            "On the TinEye page, click the upload arrow and choose the downloaded image. TinEye "
            "lists where the image appears and can sort by oldest crawl date - an earlier result "
            "is a lead, not proof of the original source."
        ),
    ),
    SearchProvider(
        key="yandex_images",
        name="Yandex Images",
        landing_url="https://yandex.com/images/",
        terms_url="https://yandex.com/legal/rules/",
        instructions=("On the Yandex Images page, click the camera icon and upload the downloaded image."),
    ),
)

PROVIDER_KEYS = frozenset(provider.key for provider in PROVIDERS)
