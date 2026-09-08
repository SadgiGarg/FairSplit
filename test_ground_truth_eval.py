"""Automated evaluation test suite verifying:

1. Proportional surcharge splitting mathematics.
2. 1-cent reconciliation with the largest spender.
3. Printed arithmetic discrepancy flags.
4. Schema validation and recall accuracy against simulated ground truths.
"""

import pytest
from schemas import ReceiptData, ExtractedItem, ReceiptMetadata
from split_engine import (
    evaluate_receipt_discrepancy,
    compute_proportional_split,
    quantize_currency,
)


def test_arithmetic_discrepancy_detection_match():
    """Verify clean receipts flag no discrepancy."""
    is_valid, computed, delta = evaluate_receipt_discrepancy(
        item_sum=50.00,
        tax=5.00,
        service_charge=2.50,
        discount=0.00,
        printed_total=57.50,
    )
    assert is_valid is True
    assert computed == 57.50
    assert delta == 0.0


def test_arithmetic_discrepancy_detection_mismatch():
    """Verify mismatched receipts flag discrepancies accurately."""
    is_valid, computed, delta = evaluate_receipt_discrepancy(
        item_sum=45.00,
        tax=4.50,
        service_charge=0.00,
        discount=5.00,
        printed_total=49.00,  # Real total should be 44.50
    )
    assert is_valid is False
    assert computed == 44.50
    assert round(delta, 2) == -4.50


def test_proportional_split_strict_math():
    """Verifies proportional tax allocation.

    Alice spends $30 (75%), Bob spends $10 (25%).
    Total base = $40. Tax = $4, Target Total = $44.
    Alice should pay $30 + $3 = $33.
    Bob should pay $10 + $1 = $11.
    """
    items = [
        {"name": "Steak", "total_price": 30.00},
        {"name": "Salad", "total_price": 10.00},
    ]
    assignments = [["Alice"], ["Bob"]]
    diners = ["Alice", "Bob"]

    res = compute_proportional_split(
        items=items,
        item_assignments=assignments,
        all_diners=diners,
        tax=4.00,
        service_charge=0.0,
        discount=0.0,
        target_total=44.00,
    )

    assert res["Alice"]["base_amount"] == 30.00
    assert res["Alice"]["allocated_tax_and_fees"] == 3.00
    assert res["Alice"]["final_payable"] == 33.00

    assert res["Bob"]["base_amount"] == 10.00
    assert res["Bob"]["allocated_tax_and_fees"] == 1.00
    assert res["Bob"]["final_payable"] == 11.00

    total_shares = sum(v["final_payable"] for v in res.values())
    assert quantize_currency(total_shares) == quantize_currency(44.00)


def test_penny_reconciliation_largest_spender():
    """Verifies that an odd 1-cent split reconciles to the largest spender.

    Alice: $10.00 (Base)
    Bob: $10.00 (Base)
    Charlie: $10.01 (Base - Highest Spender)
    Base sum = $30.01. Target total = $30.02 (1 cent surcharge).
    """
    items = [
        {"name": "Item A", "total_price": 10.00},
        {"name": "Item B", "total_price": 10.00},
        {"name": "Item C", "total_price": 10.01},
    ]
    assignments = [["Alice"], ["Bob"], ["Charlie"]]
    diners = ["Alice", "Bob", "Charlie"]

    res = compute_proportional_split(
        items=items,
        item_assignments=assignments,
        all_diners=diners,
        tax=0.01,
        service_charge=0.0,
        discount=0.0,
        target_total=30.02,
    )

    total_shares = sum(v["final_payable"] for v in res.values())
    assert quantize_currency(total_shares) == quantize_currency(30.02)
    # Charlie as largest spender absorbs rounding difference
    assert res["Charlie"]["final_payable"] == 10.02


def test_ground_truth_schema_evaluation():
    """Simulates grounding evaluation against ground truth JSON."""
    ground_truth_mock = {
        "metadata": {
            "merchant_name": "Cafe Mock",
            "subtotal": 20.0,
            "tax": 2.0,
            "service_charge": 1.0,
            "discount": 0.0,
            "printed_total": 23.0,
            "printed_total_confidence": 0.99,
        },
        "items": [
            {
                "name": "Latte",
                "quantity": 2.0,
                "unit_price": 5.0,
                "total_price": 10.0,
                "confidence": 0.95,
            },
            {
                "name": "Croissant",
                "quantity": 2.0,
                "unit_price": 5.0,
                "total_price": 10.0,
                "confidence": 0.75,  # Needs Review flag
            },
        ],
    }

    parsed = ReceiptData.model_validate(ground_truth_mock)
    assert len(parsed.items) == 2
    assert parsed.items[1].confidence < 0.80
    assert parsed.metadata.printed_total == 23.0


if __name__ == "__main__":
    pytest.main(["-v", __file__])