# FairSplit 🍛

> **Proportional Bill Splitting from Real-World Receipts**  
> Built with Streamlit, Offline Recognition Engine, Pydantic, and Decimal exact-cent reconciliation.

---

## 📌 Problem Context
Seven diners eat dinner: two share a biryani, one only has a Coke, and somebody leaves early. Service charge and GST sit on top. 

Dividing taxes and surcharges equally by $N$ penalizes light eaters. **FairSplit** digitizes the bill, lets users map dishes to individuals or sub-groups, pro-rates GST and service fees strictly by net food consumed, and reconciles every rounding residual to zero leakage.

---

## 🚀 Key Architectural Highlights

1. **Structured Schema Validation**
   - Extracts merchant name, line items, itemized quantities, unit prices, GST, service charge, discounts, and printed totals into a strictly typed `Pydantic` schema (`ReceiptData`).

2. **Human-in-the-Loop Audit (`st.data_editor`)**
   - Line items with confidence scores below 80% are flagged (`⚠️ Review`).
   - Users can correct item names, quantities, or prices in real time before arithmetic execution.

3. **Real-Time Arithmetic Discrepancy Engine**
   - Automatically cross-audits:
     $$\text{Calculated Total} = \sum \text{Dishes} + \text{GST} + \text{Service Charge} - \text{Discount}$$
   - Flags deliberate or accidental restaurant billing errors against the printed receipt total.

4. **Proportional Surcharge Engine & Penny Reconciliation**
   - Surcharges (GST, tips) are allocated strictly proportional to each diner's net food consumption ratio:
     $$R_i = \frac{\text{Food}_i}{\sum \text{Food}}$$
   - Uses `Decimal` arithmetic to avoid floating-point drift.
   - Guarded residual reconciliation absorbs true round-off paise ($\le ₹0.05$) to the largest consumer, guaranteeing zero leakage.

5. **Consumer-Grade Interface**
   - 3-step wizard workflow inspired by modern food-delivery platforms (Swiggy/Zomato design language).
   - Instant WhatsApp settlement export with ready-to-pay breakdown.

---

## 🧪 Benchmark & Hard-Condition Evaluation Set

The repository includes a dedicated test harness (`benchmark.py`) and a ground-truth dataset (`tests_dataset/ground_truth.json`) covering real-world stress conditions:

| ID | Condition | Status |
| :--- | :--- | :--- |
| `bill_05` | Handwritten Cash Memo (*Laziz Restaurant*) | Hand-labeled & Verified |
| `bill_08` | Deliberate Arithmetic Error (*Wrong Printed Total*) | Discrepancy Caught |
| `bill_01`–`12` | Dim light, crumpled, steep angle, faded print, etc. | Evaluation harness defined |

Run the automated evaluation suite:
```bash
python benchmark.py