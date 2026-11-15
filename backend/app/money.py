"""Money formatting. The only place rupee display strings are made (DATA_AND_LOGIC section 2).

Money is always integer paise. display(): "₹" + Indian digit grouping, no decimals when the
amount is whole rupees, else 2 decimals. Negative amounts use the minus sign U+2212: "−₹3,100".
"""
from __future__ import annotations

RUPEE = "₹"
MINUS = "−"


def _check(paise: int) -> None:
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError(f"amount must be integer paise, got {type(paise).__name__}")


def group_indian(n: int) -> str:
    """1234567 -> '12,34,567' (last three digits, then pairs)."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs + [tail])


def display(paise: int) -> str:
    _check(paise)
    sign = MINUS if paise < 0 else ""
    rupees, rem = divmod(abs(paise), 100)
    text = group_indian(rupees)
    if rem:
        text += f".{rem:02d}"
    return f"{sign}{RUPEE}{text}"


def amount(paise: int) -> dict:
    """The standard API money object: {"amount_paise": ..., "amount_display": ...}."""
    return {"amount_paise": paise, "amount_display": display(paise)}
