"""Data schemas for FairSplit receipt extraction and bill splitting.

Uses Pydantic V2 models for structured Gemini multimodal generation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedItem(BaseModel):
    """Line item representation with per-field confidence."""

    name: str = Field(description="Description or name of the item purchased.")
    quantity: float = Field(
        default=1.0, description="Quantity of items purchased (e.g. 1, 2, 0.5)."
    )
    unit_price: Optional[float] = Field(
        default=None, description="Price per individual unit before item-level discount."
    )
    total_price: float = Field(
        description="Final line-item charge after quantity multiplier."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0.0 and 1.0 for this item extraction.",
    )


class ReceiptMetadata(BaseModel):
    """Aggregate totals and fees with confidence scores."""

    merchant_name: Optional[str] = Field(
        default="Unknown Merchant", description="Store or restaurant name."
    )
    subtotal: Optional[float] = Field(
        default=None, description="Pre-tax, pre-surcharge subtotal."
    )
    subtotal_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in subtotal."
    )

    tax: float = Field(
        default=0.0, description="Total sales tax, GST, or VAT amount."
    )
    tax_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in tax amount."
    )

    service_charge: float = Field(
        default=0.0, description="Gratuity, tip, or mandatory service fee."
    )
    service_charge_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in service fee."
    )

    discount: float = Field(
        default=0.0, description="Overall bill-level discount or voucher amount."
    )
    discount_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in discount amount."
    )

    printed_total: float = Field(
        description="Final grand total explicitly printed on receipt."
    )
    printed_total_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in printed total."
    )


class ReceiptData(BaseModel):
    """Complete structured output payload from Gemini 2.5 Flash."""

    metadata: ReceiptMetadata
    items: List[ExtractedItem] = Field(
        default_factory=list,
        description="List of all purchased goods, food, or services.",
    )