"""JobsDB Hong Kong search input utilities."""

from urllib.parse import quote


def normalize_keyword(keyword: str) -> str:
    """Normalize one user-supplied search keyword."""
    normalized = " ".join(keyword.split())
    if not normalized:
        raise ValueError("keyword must not be empty")
    return normalized


def build_search_url(keyword: str) -> str:
    """Build the canonical JobsDB HK URL for one keyword."""
    slug = normalize_keyword(keyword).lower().replace(" ", "-")
    encoded = quote(slug, safe="-")
    return f"https://hk.jobsdb.com/{encoded}-jobs"
