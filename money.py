"""Exact rupee input, shared by catalogue and billing forms."""

import re
from decimal import Decimal

DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")


def parse_price(value):
    if not isinstance(value, str):
        return None
    text = value.strip().translate(DIGITS)
    if len(text) > 12 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        return None
    amount = int(Decimal(text) * 100)
    return amount if 0 < amount <= 999999999 else None
