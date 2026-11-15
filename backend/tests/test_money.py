import pytest

from app import money


@pytest.mark.parametrize(
    "paise, expected",
    [
        (0, "₹0"),
        (99, "₹0.99"),
        (100, "₹1"),
        (99999, "₹999.99"),
        (100000, "₹1,000"),
        (1234567, "₹12,345.67"),
        (10000000, "₹1,00,000"),
        # examples from the contract and DATA_AND_LOGIC section 2
        (482000, "₹4,820"),
        (12000000, "₹1,20,000"),
        (4550, "₹45.50"),
        (50000000, "₹5,00,000"),
        (1234567800, "₹1,23,45,678"),
        (-310000, "−₹3,100"),
    ],
)
def test_display(paise, expected):
    assert money.display(paise) == expected


def test_negative_uses_unicode_minus():
    assert money.display(-310000)[0] == "−"


@pytest.mark.parametrize("bad", [1.0, "100", True, None])
def test_rejects_non_integer(bad):
    with pytest.raises(TypeError):
        money.display(bad)


def test_amount_object():
    assert money.amount(172000) == {"amount_paise": 172000, "amount_display": "₹1,720"}
