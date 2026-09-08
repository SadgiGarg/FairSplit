"""
Proportional Bill Splitting and Discrepancy Auditing Engine.
Uses Decimal arithmetic for exact cent calculations and penny reconciliation.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any
from pydantic import BaseModel, Field

from schemas import ReceiptData


class DinerShare(BaseModel):
    raw_items_total: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    tax_share: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    service_share: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    discount_share: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    final_total: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    proportion: Decimal = Field(default_factory=lambda: Decimal("0.0000"))


class SplitResult(BaseModel):
    diners: Dict[str, DinerShare]
    sum_of_diner_shares: Decimal
    grand_total_target: Decimal
    discrepancy: Decimal
    penny_balanced: bool


def _to_decimal(val: Any) -> Decimal:
    """Safely converts numeric or string float values to 2-decimal rounded Decimals."""
    if val is None:
        return Decimal("0.00")
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_receipt_totals(receipt_data: ReceiptData) -> Dict[str, Any]:
    """
    Verifies internal arithmetic:
    Calculated Total = sum(items) + tax + service_charge - discount.
    Detects any discrepancies against the printed receipt total.
    """
    calc_subtotal = sum(_to_decimal(item.total_price) for item in receipt_data.items)
    tax = _to_decimal(receipt_data.metadata.tax)
    service = _to_decimal(receipt_data.metadata.service_charge)
    discount = _to_decimal(receipt_data.metadata.discount)
    printed = _to_decimal(receipt_data.metadata.printed_total)

    calc_total = calc_subtotal + tax + service - discount
    discrepancy = (calc_total - printed).quantize(Decimal("0.01"))

    return {
        "calculated_subtotal": float(calc_subtotal),
        "calculated_total": float(calc_total),
        "printed_total": float(printed),
        "discrepancy": float(discrepancy),
        "is_discrepant": abs(discrepancy) > Decimal("0.01"),
    }


def calculate_split(
    receipt_data: ReceiptData,
    item_assignments: Dict[int, List[str]],
) -> SplitResult:
    """
    Calculates exact proportional allocations:
    1. Distributes each line item evenly among assigned diners.
    2. Determines each diner's proportion of net items consumed.
    3. Pro-rates tax, tip/service, and discount according to consumption ratio.
    4. Reconciles true rounding penny residuals (<= $0.05) to the largest consumer.
    """
    all_diners = set()
    for diner_list in item_assignments.values():
        all_diners.update(diner_list)

    if not all_diners:
        raise ValueError("At least one diner must be assigned to an item.")

    diner_raw_totals: Dict[str, Decimal] = {d: Decimal("0.00") for d in all_diners}

    # 1. Distribute item costs evenly among assigned diners
    for idx, item in enumerate(receipt_data.items):
        assigned = item_assignments.get(idx, [])
        if not assigned:
            continue

        item_price = _to_decimal(item.total_price)
        n_diners = Decimal(len(assigned))
        per_diner_price = (item_price / n_diners).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        distributed_sum = Decimal("0.00")
        for diner in assigned[:-1]:
            diner_raw_totals[diner] += per_diner_price
            distributed_sum += per_diner_price

        # The last diner absorbs the remainder of the item price to prevent loss
        last_diner = assigned[-1]
        diner_raw_totals[last_diner] += (item_price - distributed_sum)

    total_food_consumed = sum(diner_raw_totals.values())
    if total_food_consumed == Decimal("0.00"):
        total_food_consumed = Decimal("0.01")

    tax = _to_decimal(receipt_data.metadata.tax)
    service = _to_decimal(receipt_data.metadata.service_charge)
    discount = _to_decimal(receipt_data.metadata.discount)

    target_grand_total = _to_decimal(receipt_data.metadata.printed_total)
    if target_grand_total == Decimal("0.00"):
        target_grand_total = total_food_consumed + tax + service - discount

    # 2. Compute proportional surcharge and discount shares
    diner_shares: Dict[str, DinerShare] = {}
    for diner, raw_total in diner_raw_totals.items():
        ratio = raw_total / total_food_consumed
        t_share = (tax * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        s_share = (service * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        d_share = (discount * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sub_final = raw_total + t_share + s_share - d_share

        diner_shares[diner] = DinerShare(
            raw_items_total=raw_total,
            tax_share=t_share,
            service_share=s_share,
            discount_share=d_share,
            final_total=sub_final,
            proportion=ratio.quantize(Decimal("0.0001")),
        )

    # 3. Guarded Penny Reconciliation (only for minor round-off differences <= $0.05)
    current_sum = sum(ds.final_total for ds in diner_shares.values())
    discrepancy = (target_grand_total - current_sum).quantize(Decimal("0.01"))

    if Decimal("0.00") < abs(discrepancy) <= Decimal("0.05") and diner_shares:
        top_consumer = max(diner_shares.keys(), key=lambda d: diner_shares[d].raw_items_total)
        diner_shares[top_consumer].final_total += discrepancy

    final_reconciled_sum = sum(ds.final_total for ds in diner_shares.values())
    penny_balanced = (final_reconciled_sum == target_grand_total)

    return SplitResult(
        diners=diner_shares,
        sum_of_diner_shares=final_reconciled_sum,
        grand_total_target=target_grand_total,
        discrepancy=(target_grand_total - final_reconciled_sum).quantize(Decimal("0.01")),
        penny_balanced=penny_balanced,
    )