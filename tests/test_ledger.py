from decimal import Decimal
from app.services.ledger import simplify_debts, split_equal


def test_equal_split_keeps_total():
    result = split_equal(Decimal("100.00"), [1, 2, 3])
    assert sum(result.values()) == Decimal("100.00")
    assert set(result) == {1, 2, 3}


def test_simplify_debts():
    balances = {
        1: Decimal("60.00"),
        2: Decimal("40.00"),
        3: Decimal("-70.00"),
        4: Decimal("-30.00"),
    }
    transfers = simplify_debts(balances)
    assert sum(x["amount"] for x in transfers) == Decimal("100.00")
    assert all(x["from_user_id"] in {3, 4} for x in transfers)
    assert all(x["to_user_id"] in {1, 2} for x in transfers)
