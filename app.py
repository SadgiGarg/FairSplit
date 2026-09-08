"""
FairSplit: Consumer-Grade Bill Splitting Application
Offline Recognition Engine • INR (₹) • GST & Service Charge • Human Audit
"""

import os
from decimal import Decimal
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image

from schemas import ExtractedItem, ReceiptData, ReceiptMetadata
from ocr_engine import parse_receipt_images
from split_engine import calculate_split, validate_receipt_totals

# --- Streamlit Setup ---
st.set_page_config(
    page_title="FairSplit • Split & Settle",
    page_icon="🍕",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- Design Tokens (Stitch AI Custom Theme) ---
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet" />

    <style>
    /* Canvas Base */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background-color: #fcf8ff !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: #1a1a26 !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }

    /* Surface Card */
    .stitch-card {
        background-color: #ffffff;
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 4px 20px -2px rgba(28,28,40,0.06), 0 2px 6px -1px rgba(28,28,40,0.03);
        margin-bottom: 14px;
        position: relative;
    }

    /* 3-Step Wizard Navigation Indicators */
    .nav-btn-active {
        color: #fc8019 !important;
        font-weight: 800 !important;
        border-bottom: 3px solid #fc8019 !important;
        padding-bottom: 6px;
        text-align: center;
        font-size: 13px;
    }
    .nav-btn-inactive {
        color: #8b7264 !important;
        font-weight: 600 !important;
        padding-bottom: 6px;
        text-align: center;
        font-size: 13px;
    }

    /* Primary Orange Action Buttons */
    div.stButton > button[kind="primary"] {
        background-color: #fc8019 !important;
        color: #ffffff !important;
        border-radius: 14px !important;
        height: 52px !important;
        font-size: 16px !important;
        font-weight: 700 !important;
        border: none !important;
        box-shadow: 0 10px 25px -4px rgba(252, 128, 25, 0.4) !important;
        transition: all 0.15s ease !important;
    }
    div.stButton > button[kind="primary"]:hover {
        transform: scale(0.99) !important;
    }

    /* Secondary Controls */
    div.stButton > button:not([kind="primary"]) {
        border-radius: 12px !important;
        background-color: #efecfd !important;
        color: #1a1a26 !important;
        font-weight: 600 !important;
        border: none !important;
    }

    /* Metric Boxes */
    div[data-testid="stMetric"] {
        background-color: #f5f2ff !important;
        border-radius: 12px !important;
        padding: 10px 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Default Group State ---
DEFAULT_DINERS = ["Aarav", "Diya", "Ishaan", "Kabir", "Meera", "Rohan", "Sanya"]

if "current_page" not in st.session_state:
    st.session_state.current_page = "scan"
if "receipt_data" not in st.session_state:
    st.session_state.receipt_data = None
if "diners" not in st.session_state:
    st.session_state.diners = DEFAULT_DINERS.copy()
if "payer" not in st.session_state:
    st.session_state.payer = "Aarav"
if "assignments" not in st.session_state:
    st.session_state.assignments = {}
if "demo_scenario" not in st.session_state:
    st.session_state.demo_scenario = "auto"

# --- Top App Bar ---
st.markdown(
    f"""
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; padding: 4px 0;">
        <div style="display:flex; align-items:center; gap:10px;">
            <div style="width:38px; height:38px; background:#fc8019; border-radius:12px; display:flex; align-items:center; justify-content:center; color:white; font-size:18px; font-weight:800;">
                FS
            </div>
            <div>
                <div style="font-size:19px; font-weight:800; color:#1a1a26; line-height:1.1;">FairSplit</div>
                <div style="font-size:11px; font-weight:700; color:#fc8019; display:flex; align-items:center; gap:4px;">
                    <span style="width:6px; height:6px; border-radius:50%; background:#fc8019; display:inline-block;"></span>
                    Table of {len(st.session_state.diners)} • Proportional GST & Tip
                </div>
            </div>
        </div>
        <div style="background:#ffdbc8; color:#733500; font-size:11px; font-weight:800; padding:4px 12px; border-radius:999px;">
            OFFLINE READY
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Navigation Step Indicator
nav_cols = st.columns(3)
pages = [("scan", "1. Scan Bill"), ("orders", "2. Orders & Cart"), ("split", "3. Split & Settle")]
for idx, (p_code, p_title) in enumerate(pages):
    with nav_cols[idx]:
        is_active = (st.session_state.current_page == p_code)
        cls = "nav-btn-active" if is_active else "nav-btn-inactive"
        st.markdown(f'<div class="{cls}">{p_title}</div>', unsafe_allow_html=True)
st.write("")

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("### 👥 Manage Table")
    diner_input = st.text_area(
        "Who is dining? (one per line):",
        value="\n".join(st.session_state.diners),
        height=140,
    )
    parsed = [d.strip() for d in diner_input.split("\n") if d.strip()]
    if parsed and parsed != st.session_state.diners:
        st.session_state.diners = parsed
        if st.session_state.payer not in parsed:
            st.session_state.payer = parsed[0]

    st.markdown("### 💳 Primary Payer")
    p_idx = st.session_state.diners.index(st.session_state.payer) if st.session_state.payer in st.session_state.diners else 0
    st.session_state.payer = st.selectbox("Who paid the restaurant?", options=st.session_state.diners, index=p_idx)

    st.divider()
    st.markdown("### 🧾 Detection Profile Override")
    scenario_choice = st.selectbox(
        "Template / OCR Mode:",
        options=["auto", "laziz_handwritten", "biryani_dinner", "printed_math_error"],
        format_func=lambda x: {
            "auto": "⚡ Auto-Detect from Photo / Name",
            "laziz_handwritten": "✍️ Laziz Restaurant (Handwritten Memo)",
            "biryani_dinner": "🍛 7-Person Biryani & Coke (Standard)",
            "printed_math_error": "🚨 Bill with Math Error (Discrepancy Demo)",
        }[x],
    )
    st.session_state.demo_scenario = scenario_choice

# ==========================================
# PAGE 1: SCAN BILL
# ==========================================
if st.session_state.current_page == "scan":
    st.markdown(
        """
        <div class="stitch-card" style="border-left: 4px solid #fc8019;">
            <div style="font-size:16px; font-weight:700; color:#1a1a26;">
                Seven of you ate dinner. Two shared biryani, one had Coke... 🍛
            </div>
            <div style="font-size:12px; color:#686b78; margin-top:4px;">
                Proportionally distribute GST and Service Charge based on actual consumption, not equal flat division.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="stitch-card" style="text-align:center; padding: 26px 16px;">
            <div style="width:64px; height:64px; background:#fff7ed; border-radius:18px; margin:0 auto 12px; display:flex; align-items:center; justify-content:center; font-size:30px; box-shadow:0 4px 14px rgba(252,128,25,0.15);">
                📸
            </div>
            <div style="font-size:17px; font-weight:700; color:#1a1a26;">Drop restaurant receipt image here or snap</div>
            <div style="font-size:12px; color:#8b7264; margin-top:3px;">Auto-recognizes printed, handwritten, or thermal bills</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload bill photo(s)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        p_cols = st.columns(min(len(uploaded_files), 2))
        for i, f in enumerate(uploaded_files):
            with p_cols[i]:
                st.image(Image.open(f), use_container_width=True, caption=f.name)

    # Active Diners List
    pills_html = "".join(
        [
            f'<span style="background:#ffdbc8; color:#311300; font-size:12px; font-weight:700; padding:4px 12px; border-radius:999px; margin-right:4px;">👤 {d}</span>'
            for d in st.session_state.diners
        ]
    )
    st.markdown(
        f"""
        <div class="stitch-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:15px; font-weight:700;">Party Members ({len(st.session_state.diners)})</span>
                <span style="font-size:11px; color:#fc8019; font-weight:700;">Edit in sidebar</span>
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                {pills_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("✨ Scan Bill & Extract Items ➔", type="primary", use_container_width=True):
        with st.spinner("Processing bill items, rates, and surcharges..."):
            pil_imgs = [Image.open(f) for f in uploaded_files] if uploaded_files else []
            f_names = [f.name for f in uploaded_files] if uploaded_files else []

            parsed = parse_receipt_images(
                images=pil_imgs,
                file_names=f_names,
                override_profile=st.session_state.demo_scenario,
            )
            st.session_state.receipt_data = parsed
            st.session_state.assignments = {}  # Reset assignments on new bill
            st.session_state.current_page = "orders"
            st.rerun()

# ==========================================
# PAGE 2: ORDERS & CART
# ==========================================
elif st.session_state.current_page == "orders":
    if st.session_state.receipt_data is None:
        st.session_state.current_page = "scan"
        st.rerun()

    receipt: ReceiptData = st.session_state.receipt_data

    st.markdown(
        f"""
        <div class="stitch-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:18px; font-weight:800; color:#1a1a26;">{receipt.metadata.merchant_name}</div>
                    <div style="font-size:12px; color:#8b7264;">Check item prices and tax below before assigning diners</div>
                </div>
                <span style="background:#8cf4c1; color:#005236; font-size:11px; font-weight:700; padding:4px 10px; border-radius:999px;">
                    Parsed & Verified
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        gst_val = st.number_input("GST / S.T. (₹)", min_value=0.0, value=float(receipt.metadata.tax), step=0.50)
    with m2:
        svc_val = st.number_input("Service Charge (₹)", min_value=0.0, value=float(receipt.metadata.service_charge), step=0.50)
    with m3:
        printed_val = st.number_input("Printed Total (₹)", min_value=0.0, value=float(receipt.metadata.printed_total), step=0.50)

    st.markdown("#### Line Items")
    st.caption("Rows with confidence < 80% show '⚠️ Review'. Double click any cell to edit.")

    t_rows = []
    for i, it in enumerate(receipt.items):
        flag = "⚠️ Review" if it.confidence < 0.80 else "✓ High"
        t_rows.append({
            "Dish Name": it.name,
            "Qty": float(it.quantity),
            "Price (₹)": float(it.total_price),
            "Audit": flag,
        })

    df = pd.DataFrame(t_rows)
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Dish Name": st.column_config.TextColumn(required=True),
            "Qty": st.column_config.NumberColumn(min_value=0.1, step=1.0),
            "Price (₹)": st.column_config.NumberColumn(min_value=0.0, step=0.1, required=True),
            "Audit": st.column_config.TextColumn(disabled=True),
        },
        hide_index=True,
        key="cart_editor",
    )

    if st.button("💾 Apply & Recalculate", use_container_width=True):
        new_items = []
        for _, r in edited_df.iterrows():
            q = float(r["Qty"])
            p = float(r["Price (₹)"])
            new_items.append(
                ExtractedItem(
                    name=str(r["Dish Name"]),
                    quantity=q,
                    unit_price=p / q if q > 0 else 0.0,
                    total_price=p,
                    confidence=0.99,
                )
            )
        receipt.items = new_items
        receipt.metadata.tax = gst_val
        receipt.metadata.service_charge = svc_val
        receipt.metadata.printed_total = printed_val
        st.session_state.receipt_data = receipt
        st.success("Changes saved!")
        st.rerun()

    # Discrepancy validation
    val_res = validate_receipt_totals(st.session_state.receipt_data)
    if val_res["is_discrepant"]:
        st.error(
            f"🚨 **Discrepancy Detected:** Sum of dishes (₹{val_res['calculated_subtotal']:.2f}) + GST + Service = "
            f"**₹{val_res['calculated_total']:.2f}**, but printed total is **₹{val_res['printed_total']:.2f}** "
            f"(Difference: ₹{abs(val_res['discrepancy']):.2f})."
        )
    else:
        st.success("✅ **Math Verified:** Item subtotals and surcharges match the printed total.")

    st.write("")
    c_back, c_next = st.columns([1, 2])
    with c_back:
        if st.button("← Rescan", use_container_width=True):
            st.session_state.current_page = "scan"
            st.rerun()
    with c_next:
        if st.button("Assign Diners ➔", type="primary", use_container_width=True):
            st.session_state.current_page = "split"
            st.rerun()

# ==========================================
# PAGE 3: SPLIT & SETTLE
# ==========================================
elif st.session_state.current_page == "split":
    if st.session_state.receipt_data is None:
        st.session_state.current_page = "scan"
        st.rerun()

    receipt: ReceiptData = st.session_state.receipt_data
    diners = st.session_state.diners
    payer = st.session_state.payer

    st.markdown(
        """
        <div class="stitch-card" style="border-left: 4px solid #006c49;">
            <div style="font-size:16px; font-weight:800; color:#1a1a26;">Who Ate What?</div>
            <div style="font-size:12px; color:#8b7264; margin-top:2px;">
                Assign each item to one person, several people, or everyone. Taxes and tips pro-rate automatically based on actual consumption.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    assignments = {}
    for idx, item in enumerate(receipt.items):
        with st.container():
            col_l, col_r = st.columns([3, 4])
            with col_l:
                st.markdown(f"**{item.name}**  \n`₹{item.total_price:.2f}` • `{item.quantity:g}x`")
            with col_r:
                prev_assigned = st.session_state.assignments.get(idx, diners)
                valid_defaults = [d for d in prev_assigned if d in diners] or diners
                chosen = st.multiselect(
                    f"Assign {item.name}",
                    options=diners,
                    default=valid_defaults,
                    key=f"dish_alloc_{idx}",
                    label_visibility="collapsed",
                )
                assignments[idx] = chosen

    st.session_state.assignments = assignments
    unassigned = [receipt.items[i].name for i, d_list in assignments.items() if not d_list]

    if unassigned:
        st.warning(f"⚠️ Assign at least one person to: {', '.join(unassigned)}")
    else:
        split_res = calculate_split(receipt, assignments)

        st.markdown("---")
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:12px;">
                <div>
                    <h2 style="font-size:22px; font-weight:800; margin:0;">Settlement Breakdown</h2>
                    <span style="font-size:12px; color:#8b7264;">Proportional Surcharges • Zero Rupee Leakage</span>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:11px; color:#8b7264; text-transform:uppercase; font-weight:700;">Total Bill</span>
                    <div style="font-size:26px; font-weight:800; color:#fc8019;">₹{split_res.grand_total_target:.2f}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        payer_refund = sum(share.final_total for d_name, share in split_res.diners.items() if d_name != payer)

        for d_name, share in split_res.diners.items():
            is_payer = (d_name == payer)
            badge_html = (
                '<span style="background:#8cf4c1; color:#005236; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px;">Paid Bill Upfront</span>'
                if is_payer
                else '<span style="background:#e3e0f2; color:#574236; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px;">Pending UPI</span>'
            )

            st.markdown(
                f"""
                <div class="stitch-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <div style="font-size:18px; font-weight:800; color:#1a1a26;">{d_name}</div>
                            <div style="margin-top:2px;">{badge_html}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:11px; font-weight:700; color:#006c49; text-transform:uppercase;">
                                {"Net Share" if is_payer else "Owes"}
                            </div>
                            <div style="font-size:26px; font-weight:800; color:{'#1a1a26' if is_payer else '#006c49'};">
                                ₹{share.final_total:.2f}
                            </div>
                        </div>
                    </div>
                    <div style="background:#f5f2ff; border-radius:10px; padding:8px 12px; margin-top:10px; font-size:12px; color:#574236;">
                        Food: ₹{share.raw_items_total:.2f} • GST & Service: ₹{(share.tax_share + share.service_share):.2f} ({(share.proportion * 100):.1f}% share)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if payer in split_res.diners:
            st.markdown(
                f"""
                <div style="background:rgba(140,244,193,0.3); border-radius:12px; padding:12px 16px; display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
                    <div style="font-size:13px; font-weight:700; color:#005236;">
                        ✓ {payer} receives reimbursement
                    </div>
                    <div style="font-size:18px; font-weight:800; color:#006c49;">
                        +₹{payer_refund:.2f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Direct WhatsApp Settlement Link
        wa_text = f"🧾 *FairSplit Bill Breakdown — {receipt.metadata.merchant_name}*\n"
        wa_text += f"Total Bill: ₹{split_res.grand_total_target:.2f}\n"
        wa_text += f"Paid by: {payer}\n\n"
        for name, share in split_res.diners.items():
            if name == payer:
                wa_text += f"• *{name}* (Payer): Net ₹{share.final_total:.2f} (Receives +₹{payer_refund:.2f})\n"
            else:
                wa_text += f"• *{name}*: Owes ₹{share.final_total:.2f} via UPI\n"
        wa_text += "\n_Calculated with FairSplit Proportional AI._"

        wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_text)}"

        st.markdown(
            f"""
            <a href="{wa_url}" target="_blank" style="text-decoration:none;">
                <div style="width:100%; height:50px; background:#25D366; border-radius:14px; display:flex; align-items:center; justify-content:center; gap:8px; color:white; font-size:16px; font-weight:700; box-shadow:0 4px 12px rgba(37,211,102,0.3);">
                    Share Breakdown via WhatsApp 📲
                </div>
            </a>
            """,
            unsafe_allow_html=True,
        )

        st.write("")

        summary_rows = [
            {
                "Diner": name,
                "Role": "Payer" if name == payer else "Debtor",
                "Food Consumed (₹)": f"{s.raw_items_total:.2f}",
                "GST + Service Share (₹)": f"{(s.tax_share + s.service_share):.2f}",
                "Final Due (₹)": f"{s.final_total:.2f}",
            }
            for name, s in split_res.diners.items()
        ]
        csv_bytes = pd.DataFrame(summary_rows).to_csv(index=False).encode("utf-8")

        col_dl, col_reset = st.columns(2)
        with col_dl:
            st.download_button(
                "📥 Export CSV Breakdown",
                data=csv_bytes,
                file_name="fairsplit_settlement.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_reset:
            if st.button("🔄 Split Another Bill", use_container_width=True):
                st.session_state.current_page = "scan"
                st.session_state.receipt_data = None
                st.session_state.assignments = {}
                st.rerun()

    st.write("")
    if st.button("← Back to Orders"):
        st.session_state.current_page = "orders"
        st.rerun()