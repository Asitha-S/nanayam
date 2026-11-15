import pytest

from app.voice.utils import parse_amount


@pytest.mark.parametrize(
    "span, expected",
    [
        ("3,100", 3100),
        ("3100", 3100),
        ("3 100", 3100),
        ("₹3,100", 3100),
        ("3k", 3000),
        ("three thousand one hundred", 3100),
        ("five lakh", 500000),
        ("நூறு", 100),
        ("இருநூறு", 200),
        ("ஆயிரம்", 1000),
        ("ஆயிரத்து", 1000),
        ("லட்சம்", 100000),
        ("aayiram", 1000),
        ("ayirathu", 1000),
        ("nooru", 100),
        ("వంద", 100),
        ("వెయ్యి", 1000),
        ("లక్ష", 100000),
    ],
)
def test_parse_amount_accepts_supported_formats(span, expected):
    assert parse_amount(span) == expected


@pytest.mark.parametrize("span", ["0", "500001", "abc", "", "₹0"])
def test_parse_amount_rejects_invalid_or_out_of_range_values(span):
    with pytest.raises(ValueError):
        parse_amount(span)
