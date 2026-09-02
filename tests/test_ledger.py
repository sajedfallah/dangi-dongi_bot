from decimal import Decimal

import pytest

from app.services.ledger import calculate_split, simplify_debts, split_equal


def test_equal_split_keeps_total():
    result = split_equal(Decimal("100.00"), [1, 2, 3])
    assert sum(result.values()) == Decimal("100.00")
    assert set(result) == {1, 2, 3}


def test_percentage_split_keeps_total_and_ratio():
    result = calculate_split(
        Decimal("1000.00"),
        [1, 2, 3],
        "percentage",
        {1: Decimal("50"), 2: Decimal("30"), 3: Decimal("20")},
    )
    assert result == {1: Decimal("500.00"), 2: Decimal("300.00"), 3: Decimal("200.00")}


def test_weighted_split_handles_rounding_exactly():
    result = calculate_split(
        Decimal("100.00"),
        [1, 2, 3],
        "shares",
        {1: Decimal("1"), 2: Decimal("1"), 3: Decimal("1")},
    )
    assert sum(result.values()) == Decimal("100.00")
    assert sorted(result.values()) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_exact_split_must_equal_total():
    result = calculate_split(
        Decimal("100.00"),
        [1, 2],
        "exact",
        {1: Decimal("70"), 2: Decimal("30")},
    )
    assert result == {1: Decimal("70.00"), 2: Decimal("30.00")}
    with pytest.raises(ValueError, match="equal expense total"):
        calculate_split(
            Decimal("100.00"),
            [1, 2],
            "exact",
            {1: Decimal("60"), 2: Decimal("30")},
        )


def test_percentage_must_total_100():
    with pytest.raises(ValueError, match="total 100"):
        calculate_split(
            Decimal("100.00"),
            [1, 2],
            "percentage",
            {1: Decimal("60"), 2: Decimal("30")},
        )


def test_split_values_must_cover_all_participants():
    with pytest.raises(ValueError, match="every participant"):
        calculate_split(
            Decimal("100.00"),
            [1, 2],
            "shares",
            {1: Decimal("1")},
        )


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
