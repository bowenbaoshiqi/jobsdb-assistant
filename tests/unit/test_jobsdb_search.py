import pytest

from src.jobsdb.search import build_search_url, normalize_keyword


def test_normalize_keyword_collapses_whitespace() -> None:
    assert normalize_keyword("  Product   Manager  ") == "Product Manager"


@pytest.mark.parametrize("keyword", ["", " ", "\n\t"])
def test_normalize_keyword_rejects_empty_input(keyword: str) -> None:
    with pytest.raises(ValueError, match="keyword must not be empty"):
        normalize_keyword(keyword)


def test_build_search_url_encodes_one_keyword_for_hong_kong() -> None:
    url = build_search_url("C++ Engineer")

    assert url == "https://hk.jobsdb.com/c%2B%2B-engineer-jobs"
    assert "Hong-Kong" not in url
