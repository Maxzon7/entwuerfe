"""
========================================================================================
Multi-Period & Comparison PDF Invoice Generator (contract/invoice_pdf_exporter.py)
========================================================================================

Generates clean, formatted A4 PDF documents for:
  1. Single Active Period PDF (Annual Statement 2025 or Single Month)
  2. Custom Multi-Month Selection PDF (User-selected months, each on its own A4 page)
  3. Full 13-Page Annual + 12-Month Invoice Book PDF
  4. Side-by-Side Baseline vs. BESS Peak-Shaving Comparison Report PDF:
     - Section 1: Explicit Simulation Assumptions Register
     - Section 2: Physical Peak-Shaving & Battery Dispatch Summary
     - Section 3: Side-by-Side Itemized 4-Pillar Electricity Bill Comparison

Implementation:
---------------
Includes a pure-Python zero-dependency PDF 1.4 vector page writer (using standard
Helvetica / Helvetica-Bold Type1 fonts and vector table lines/boxes) so PDF bytes
are 100% guaranteed to generate cleanly in any Python environment without requiring
external C/binary libraries.
========================================================================================
"""

from typing import List, Dict, Any, Optional
import datetime


def _pdf_escape(text: str) -> str:
    """Sanitizes and escapes text for standard PDF Type1 WinAnsi encoding."""
    if not text:
        return ""
    replacements = {
        "×": "x",
        "→": "->",
        "—": "-",
        "–": "-",
        "•": "*",
        "€": "EUR ",
        "²": "2",
        "√": "sqrt",
        "≥": ">=",
        "≤": "<=",
        "Δ": "Delta ",
    }
    clean = str(text)
    for k, v in replacements.items():
        clean = clean.replace(k, v)
    clean = clean.encode("latin-1", errors="replace").decode("latin-1")
    clean = clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return clean


class SimpleA4PDFBuilder:
    """
    Pure-Python A4 PDF 1.4 document builder (595 x 842 pt) supporting multi-page
    vector rectangles, lines, and standard Type1 Helvetica (F1) / Helvetica-Bold (F2).
    """

    PAGE_W = 595.0
    PAGE_H = 842.0

    def __init__(self) -> None:
        self.pages: List[List[str]] = []
        self._current_cmds: List[str] = []
        self.y = 800.0

    def add_page(self) -> None:
        if self._current_cmds:
            self.pages.append(self._current_cmds)
        self._current_cmds = []
        self.y = 802.0

    def ensure_space(self, needed_pt: float) -> None:
        if not self._current_cmds:
            self.add_page()
        elif self.y - needed_pt < 42.0:
            self.add_page()

    def draw_rect(
        self,
        x: float,
        y_top: float,
        w: float,
        h: float,
        fill_rgb: Optional[tuple] = None,
        stroke_rgb: Optional[tuple] = None,
        line_w: float = 0.6,
    ) -> None:
        cmds = ["q", f"{line_w:.2f} w"]
        if fill_rgb:
            cmds.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg")
        if stroke_rgb:
            cmds.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG")
        y_bot = y_top - h
        op = "B" if (fill_rgb and stroke_rgb) else ("f" if fill_rgb else "S")
        cmds.append(f"{x:.2f} {y_bot:.2f} {w:.2f} {h:.2f} re {op}")
        cmds.append("Q")
        self._current_cmds.append("\n".join(cmds))

    def draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        rgb: tuple = (0.75, 0.78, 0.82),
        line_w: float = 0.5,
    ) -> None:
        self._current_cmds.append(
            f"q {line_w:.2f} w {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q"
        )

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        size: float = 9.0,
        bold: bool = False,
        rgb: tuple = (0.10, 0.14, 0.20),
        align: str = "left",
        max_chars: int = 110,
    ) -> None:
        raw = str(text)
        if len(raw) > max_chars:
            raw = raw[: max_chars - 3] + "..."
        esc = _pdf_escape(raw)
        font_tag = "/F2" if bold else "/F1"
        char_w = size * (0.53 if bold else 0.50)
        est_w = len(raw) * char_w
        draw_x = x
        if align == "right":
            draw_x = x - est_w
        elif align == "center":
            draw_x = x - (est_w / 2.0)

        self._current_cmds.append(
            f"q BT {font_tag} {size:.1f} Tf {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg "
            f"1 0 0 1 {draw_x:.2f} {y:.2f} Tm ({esc}) Tj ET Q"
        )

    def build_bytes(self) -> bytes:
        if self._current_cmds:
            self.pages.append(self._current_cmds)
            self._current_cmds = []
        if not self.pages:
            self.add_page()
            self.pages.append(self._current_cmds)
            self._current_cmds = []

        # Object layout:
        # 1: Catalog
        # 2: Pages
        # 3: Font F1 (Helvetica)
        # 4: Font F2 (Helvetica-Bold)
        # For each page i (0..N-1):
        #   page_obj_id = 5 + 2*i
        #   content_obj_id = 6 + 2*i
        objects: List[bytes] = []

        num_pages = len(self.pages)
        kids_refs = " ".join(f"{5 + 2 * i} 0 R" for i in range(num_pages))

        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(f"<< /Type /Pages /Kids [{kids_refs}] /Count {num_pages} >>".encode("latin-1"))
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        for i, cmds in enumerate(self.pages):
            page_id = 5 + 2 * i
            content_id = 6 + 2 * i
            footer_cmd = (
                f"q BT /F1 7.5 Tf 0.45 0.50 0.58 rg 1 0 0 1 36.0 22.0 Tm "
                f"(Generated by Commercial Electricity Bill & BESS Peak-Shaving Engine | Page {i + 1} of {num_pages}) Tj ET Q"
            )
            stream_str = "\n".join(cmds + [footer_cmd])
            stream_bytes = stream_str.encode("latin-1", errors="replace")

            page_dict = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("latin-1")
            content_dict = (
                f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
                + stream_bytes
                + b"\nendstream"
            )
            objects.append(page_dict)
            objects.append(content_dict)

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: List[int] = [0]
        for idx, obj_bytes in enumerate(objects, start=1):
            offsets.append(len(out))
            out.extend(f"{idx} 0 obj\n".encode("latin-1"))
            out.extend(obj_bytes)
            out.extend(b"\nendobj\n")

        xref_pos = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
        )
        return bytes(out)


def _render_single_invoice_page(
    pdf: SimpleA4PDFBuilder,
    inv_data: Dict[str, Any],
    active_config: Any,
    site_name: str,
    assumptions_dict: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> None:
    """Renders one complete A4 commercial electricity bill statement page into the PDF builder."""
    pdf.add_page()
    curr = getattr(active_config, "currency_code", "EUR")
    en_p1 = getattr(active_config, "enable_pillar_1_supplier", True)
    en_p2 = getattr(active_config, "enable_pillar_2_dso", True)
    en_p3 = getattr(active_config, "enable_pillar_3_metering", True)
    en_p4 = getattr(active_config, "enable_pillar_4_taxes", True)
    vat_pct = active_config.levies.vat_rate_pct

    # Top Header Banner
    pdf.draw_rect(36, 810, 523, 44, fill_rgb=(0.06, 0.09, 0.16))
    pdf.draw_text(48, 792, "COMMERCIAL ELECTRICITY BILL & 4-PILLAR STATEMENT", size=11.5, bold=True, rgb=(0.97, 0.98, 1.0))
    pdf.draw_text(
        48,
        776,
        f"Invoice No: {inv_data['inv_number']}  |  Period: {inv_data['period_label']} ({inv_data['period_days']} days)  |  Currency: {curr}",
        size=8.5,
        rgb=(0.56, 0.64, 0.72),
    )
    pdf.y = 754.0

    # Master Data & Physical KPI Box (64pt height, 4 lines per column, strict non-overlapping x boundaries)
    pdf.draw_rect(36, pdf.y, 523, 64, fill_rgb=(0.95, 0.97, 0.99), stroke_rgb=(0.80, 0.84, 0.88))
    pdf.draw_text(44, pdf.y - 13, f"Facility / Site: {site_name}", size=8.0, bold=True, max_chars=52)
    pdf.draw_text(44, pdf.y - 26, f"Grid / Utility (P2): {active_config.dso.dso_name}", size=7.8, max_chars=52)
    pdf.draw_text(44, pdf.y - 39, f"Tariff Tier: {active_config.dso.grid_tier}", size=7.8, max_chars=52)
    supp_lbl = f"{active_config.supplier.supplier_name} ({active_config.supplier.pricing_mode.value.upper()})" if en_p1 else "Bundled in Utility [BYPASSED]"
    pdf.draw_text(44, pdf.y - 52, f"Energy Retailer (P1): {supp_lbl}", size=7.8, max_chars=52)

    billed_peak_val = float(inv_data.get("billed_peak_kw", inv_data["p_max"]))
    tou_split_lbl = inv_data.get("tou_split_summary") or f"HT {inv_data['ht_pct']:.1f}% / NT {inv_data['nt_pct']:.1f}%"
    pdf.draw_text(315, pdf.y - 13, f"Active Energy: {inv_data['kwh_total']:,.0f} kWh ({tou_split_lbl})", size=7.8, bold=True, max_chars=54)
    pdf.draw_text(315, pdf.y - 26, f"Registered Peak: {inv_data['p_max']:,.1f} kW | Billed Peak: {billed_peak_val:,.1f} kW", size=7.8, max_chars=54)
    breach_txt = f"BREACH (+{inv_data['excess_kw']:,.1f} kW)" if inv_data["is_breached"] else "WITHIN CONTRACT LIMIT"
    pdf.draw_text(315, pdf.y - 39, f"Contracted Limit: {inv_data['contracted_kw']:,.1f} kW | Status: {breach_txt}", size=7.8, max_chars=54)
    pdf.draw_text(315, pdf.y - 52, f"Utilization: {inv_data['utilization_hours']:,.0f} hrs | Effective Net: {curr} {inv_data['effective_rate_net']:.4f}/kWh", size=7.8, max_chars=54)
    pdf.y -= 72.0

    # Compact Assumptions Summary Bar (if provided)
    if assumptions_dict:
        pdf.draw_rect(36, pdf.y, 523, 28, fill_rgb=(0.92, 0.95, 0.98), stroke_rgb=(0.75, 0.82, 0.90))
        pdf.draw_text(44, pdf.y - 11, "ACTIVE ASSUMPTIONS REGISTER:", size=7.5, bold=True, rgb=(0.08, 0.35, 0.58))
        mode_val = next((x["value"] for x in assumptions_dict.get("grid_and_tariff", []) if "Market" in x["parameter"]), "Standard")
        res_val = next((x["value"] for x in assumptions_dict.get("load_and_period", []) if "Resolution" in x["parameter"]), "15-min intervals")
        pdf.draw_text(44, pdf.y - 22, f"Mode: {mode_val}  |  Data: {res_val}", size=7.2, rgb=(0.20, 0.25, 0.33), max_chars=115)
        pdf.y -= 36.0

    # Table Header Helper
    def _draw_block_table(title: str, positions: List[Dict[str, Any]], subtotal_label: str, subtotal_val: float, is_enabled: bool) -> None:
        if not is_enabled:
            pdf.ensure_space(19.0)
            pdf.draw_rect(36, pdf.y, 523, 14, fill_rgb=(0.90, 0.92, 0.95), stroke_rgb=(0.75, 0.78, 0.82), line_w=0.4)
            pdf.draw_text(
                42,
                pdf.y - 10,
                f"{title}: [BYPASSED / BUNDLED IN SINGLE-UTILITY BILL - {curr} 0.00]",
                size=7.6,
                bold=True,
                rgb=(0.45, 0.48, 0.53),
                max_chars=105,
            )
            pdf.y -= 19.0
            return

        needed = 32.0 + len(positions) * 14.0
        pdf.ensure_space(needed)
        pdf.draw_rect(36, pdf.y, 523, 15, fill_rgb=(0.12, 0.16, 0.23))
        pdf.draw_text(42, pdf.y - 11, title, size=8.2, bold=True, rgb=(1.0, 1.0, 1.0))
        pdf.y -= 15.0

        # Column headers
        pdf.draw_rect(36, pdf.y, 523, 13, fill_rgb=(0.88, 0.91, 0.94))
        pdf.draw_text(40, pdf.y - 9.5, "Pos.", size=7.2, bold=True)
        pdf.draw_text(68, pdf.y - 9.5, "Description / Tariff Component", size=7.2, bold=True)
        pdf.draw_text(355, pdf.y - 9.5, "Quantity", size=7.2, bold=True, align="right")
        pdf.draw_text(395, pdf.y - 9.5, "Unit", size=7.2, bold=True, align="center")
        pdf.draw_text(468, pdf.y - 9.5, f"Rate ({curr})", size=7.2, bold=True, align="right")
        pdf.draw_text(553, pdf.y - 9.5, f"Net ({curr})", size=7.2, bold=True, align="right")
        pdf.y -= 13.0

        txt_rgb = (0.12, 0.16, 0.22) if is_enabled else (0.50, 0.53, 0.58)
        for idx, p in enumerate(positions):
            pdf.ensure_space(15.0)
            row_bg = (0.98, 0.99, 1.0) if idx % 2 == 0 else (0.94, 0.96, 0.98)
            pdf.draw_rect(36, pdf.y, 523, 13.5, fill_rgb=row_bg, stroke_rgb=(0.86, 0.89, 0.92), line_w=0.3)
            q_disp = str(p.get("quantity_display", f"{p['quantity']:,.1f}"))
            unit_str = str(p["unit"])
            if unit_str in ("kWh", "kW", "kW/mo"):
                r_str = f"{p['rate']:,.4f}"
            elif unit_str == "%":
                r_str = f"{p['rate']:.4f}%"
            else:
                r_str = f"{p['rate']:,.2f}"
            amt_val = 0.0 if not is_enabled else float(p["amount_net"])
            a_str = f"{amt_val:,.2f}"

            pdf.draw_text(40, pdf.y - 9.8, str(p["pos"]), size=7.5, bold=True, rgb=txt_rgb)
            pdf.draw_text(68, pdf.y - 9.8, str(p["description"]), size=7.5, rgb=txt_rgb, max_chars=58)
            pdf.draw_text(355, pdf.y - 9.8, q_disp, size=7.5, rgb=txt_rgb, align="right")
            pdf.draw_text(395, pdf.y - 9.8, unit_str, size=7.2, rgb=txt_rgb, align="center")
            pdf.draw_text(468, pdf.y - 9.8, r_str, size=7.5, rgb=txt_rgb, align="right")
            pdf.draw_text(553, pdf.y - 9.8, a_str, size=7.5, bold=True, rgb=txt_rgb, align="right")
            pdf.y -= 13.5

        # Subtotal row
        sub_v = 0.0 if not is_enabled else subtotal_val
        pdf.draw_rect(36, pdf.y, 523, 14.5, fill_rgb=(0.90, 0.94, 0.98), stroke_rgb=(0.65, 0.75, 0.85), line_w=0.5)
        pdf.draw_text(465, pdf.y - 10.2, f"{subtotal_label}:", size=7.8, bold=True, align="right")
        pdf.draw_text(553, pdf.y - 10.2, f"{curr} {sub_v:,.2f}", size=8.0, bold=True, align="right")
        pdf.y -= 20.0

    _draw_block_table("Pillar 1: Energy Supply (Retailer)", inv_data["block_a"], "Subtotal 1 (Energy Supply Net)", inv_data["subtotal_a"], en_p1)
    _draw_block_table("Pillar 2: Grid Network (DSO / Utility)", inv_data["block_b"], "Subtotal 2 (Grid Network Net)", inv_data["subtotal_b"], en_p2)
    _draw_block_table("Pillar 3: Metering & Telemetry", inv_data["block_c"], "Subtotal 3 (Metering Net)", inv_data["subtotal_c"], en_p3)
    _draw_block_table("Pillar 4: Statutory Taxes & Levies", inv_data["block_d"], "Subtotal 4 (Statutory Taxes Net)", inv_data["subtotal_d"], en_p4)

    # Grand Total Reconciliation Box
    pdf.ensure_space(105.0)
    pdf.draw_rect(36, pdf.y, 523, 16, fill_rgb=(0.05, 0.18, 0.34))
    pdf.draw_text(42, pdf.y - 11.5, "GRAND TOTAL INVOICE RECONCILIATION (1 + 2 + 3 + 4 = TOTAL NET + VAT = TOTAL GROSS)", size=8.2, bold=True, rgb=(1.0, 1.0, 1.0))
    pdf.y -= 16.0

    kwh = max(1.0, float(inv_data["kwh_total"]))
    rec_rows = [
        ("Subtotal 1: Pillar 1 - Energy Supply (Retailer)", inv_data["subtotal_a"], False),
        ("+ Subtotal 2: Pillar 2 - Grid Network (DSO / Utility)", inv_data["subtotal_b"], False),
        ("+ Subtotal 3: Pillar 3 - Metering & Telemetry", inv_data["subtotal_c"], False),
        ("+ Subtotal 4: Pillar 4 - Statutory Taxes & Levies", inv_data["subtotal_d"], False),
        ("= TOTAL NET INVOICE AMOUNT (EXCL. VAT)", inv_data["total_net"], True),
        (f"+ Value Added Tax ({vat_pct:.1f}% VAT)", inv_data["vat_amount"], False),
        ("= TOTAL GROSS AMOUNT DUE (INCL. VAT)", inv_data["total_gross"], True),
    ]
    for idx, (lbl, val, is_bold) in enumerate(rec_rows):
        bg = (0.86, 0.94, 0.90) if idx == len(rec_rows) - 1 else ((0.88, 0.93, 0.98) if is_bold else (0.97, 0.98, 1.0))
        pdf.draw_rect(36, pdf.y, 523, 13.5, fill_rgb=bg, stroke_rgb=(0.80, 0.84, 0.88), line_w=0.4)
        pdf.draw_text(42, pdf.y - 9.8, lbl, size=7.8 if not is_bold else 8.2, bold=is_bold)
        pdf.draw_text(430, pdf.y - 9.8, f"{curr} {val / kwh:.4f}/kWh", size=7.5, bold=is_bold, align="right")
        pdf.draw_text(553, pdf.y - 9.8, f"{curr} {val:,.2f}", size=8.0 if not is_bold else 8.6, bold=is_bold, align="right")
        pdf.y -= 13.5


def generate_multi_period_invoice_pdf(
    result: Any,
    active_config: Any,
    periods: List[str],
    build_positions_fn: Any,
    site_name: str = "Commercial Facility",
    assumptions_dict: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> bytes:
    """
    Generates a single-page or multi-page A4 PDF invoice document for the requested list of
    billing periods (e.g. ['Annual Statement 2025 (Full Year)'] or 12 individual months).
    """
    pdf = SimpleA4PDFBuilder()
    target_list = periods if periods else ["Annual Statement 2025 (Full Year)"]
    for period_label in target_list:
        inv_data = build_positions_fn(result, active_config, period_label)
        _render_single_invoice_page(
            pdf=pdf,
            inv_data=inv_data,
            active_config=active_config,
            site_name=site_name,
            assumptions_dict=assumptions_dict,
        )
    return pdf.build_bytes()


def generate_bess_comparison_report_pdf(
    site_name: str,
    currency_code: str,
    assumptions_dict: Dict[str, List[Dict[str, str]]],
    physical_kpis: Dict[str, Any],
    comparison_rows: List[Dict[str, Any]],
) -> bytes:
    """
    Generates the Executive Side-by-Side Baseline vs. BESS Peak-Shaving Comparison PDF Report:
      - Section 1: Explicit Simulation Assumptions Register
      - Section 2: Physical Peak-Shaving & Battery Dispatch Summary
      - Section 3: Side-by-Side Itemized 4-Pillar Electricity Bill Comparison Table
    """
    pdf = SimpleA4PDFBuilder()
    pdf.add_page()

    # Header Banner
    pdf.draw_rect(36, 810, 523, 44, fill_rgb=(0.05, 0.14, 0.26))
    pdf.draw_text(48, 792, "EXECUTIVE REPORT: BASELINE vs. BESS PEAK-SHAVING BILL COMPARISON", size=11.0, bold=True, rgb=(0.98, 0.99, 1.0))
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.draw_text(48, 776, f"Facility: {site_name}  |  Currency: {currency_code}  |  Generated: {now_str}", size=8.5, rgb=(0.62, 0.72, 0.84))
    pdf.y = 754.0

    # Section 1: Explicit Simulation Assumptions Register
    pdf.draw_rect(36, pdf.y, 523, 15, fill_rgb=(0.12, 0.22, 0.36))
    pdf.draw_text(42, pdf.y - 11, "1. EXPLICIT SIMULATION ASSUMPTIONS REGISTER", size=8.2, bold=True, rgb=(1.0, 1.0, 1.0))
    pdf.y -= 15.0

    for cat_key, cat_title in [
        ("load_and_period", "Load & Period"),
        ("grid_and_tariff", "Grid & Tariff"),
        ("battery_physics", "Battery Physics"),
    ]:
        items = assumptions_dict.get(cat_key, [])
        for idx, item in enumerate(items):
            pdf.ensure_space(13.0)
            bg = (0.97, 0.98, 1.0) if idx % 2 == 0 else (0.93, 0.95, 0.98)
            pdf.draw_rect(36, pdf.y, 523, 12.5, fill_rgb=bg, stroke_rgb=(0.85, 0.88, 0.92), line_w=0.3)
            pdf.draw_text(42, pdf.y - 9.0, f"[{cat_title}] {item['parameter']}", size=7.2, bold=True, max_chars=48)
            pdf.draw_text(245, pdf.y - 9.0, str(item["value"]), size=7.2, max_chars=75)
            pdf.y -= 12.5
    pdf.y -= 8.0

    # Section 2: Physical Peak-Shaving Summary
    pdf.ensure_space(65.0)
    pdf.draw_rect(36, pdf.y, 523, 15, fill_rgb=(0.06, 0.28, 0.22))
    pdf.draw_text(42, pdf.y - 11, "2. PHYSICAL GRID DEMAND PROFILE & PEAK-SHAVING SUMMARY", size=8.2, bold=True, rgb=(1.0, 1.0, 1.0))
    pdf.y -= 15.0

    phys_lines = [
        (
            f"Facility Peak (Before BESS): {physical_kpis.get('peak_before_kw', 0.0):,.1f} kW",
            f"Grid Import Peak (With BESS): {physical_kpis.get('peak_after_kw', 0.0):,.1f} kW",
            f"Peak Shaved: -{physical_kpis.get('peak_shaved_kw', 0.0):,.1f} kW ({physical_kpis.get('peak_shaved_pct', 0.0):.1f}%)",
        ),
        (
            f"Contracted Grid Limit: {physical_kpis.get('grid_limit_kw', 0.0):,.1f} kW",
            f"Overload Hours: {physical_kpis.get('overload_hrs_before', 0.0):,.2f} h -> {physical_kpis.get('overload_hrs_after', 0.0):,.2f} h",
            f"Remaining Unmet Deficit: {physical_kpis.get('remaining_deficit_kwh', 0.0):,.2f} kWh",
        ),
        (
            f"Baseline Load Energy: {physical_kpis.get('load_kwh', 0.0):,.1f} kWh",
            f"With-BESS Grid Import: {physical_kpis.get('grid_import_kwh', 0.0):,.1f} kWh",
            f"BESS Discharge: {physical_kpis.get('discharge_kwh', 0.0):,.1f} kWh (RTE Loss: +{physical_kpis.get('rte_loss_kwh', 0.0):,.1f} kWh)",
        ),
    ]
    for idx, (c1, c2, c3) in enumerate(phys_lines):
        bg = (0.95, 0.98, 0.96) if idx % 2 == 0 else (0.91, 0.96, 0.93)
        pdf.draw_rect(36, pdf.y, 523, 13.5, fill_rgb=bg, stroke_rgb=(0.80, 0.86, 0.82), line_w=0.3)
        pdf.draw_text(42, pdf.y - 9.5, c1, size=7.4, bold=True)
        pdf.draw_text(215, pdf.y - 9.5, c2, size=7.4)
        pdf.draw_text(385, pdf.y - 9.5, c3, size=7.4, bold=True)
        pdf.y -= 13.5
    pdf.y -= 10.0

    # Section 3: Side-by-Side Itemized Electricity Bill Comparison Table
    pdf.ensure_space(60.0)
    pdf.draw_rect(36, pdf.y, 523, 15, fill_rgb=(0.10, 0.15, 0.24))
    pdf.draw_text(42, pdf.y - 11, f"3. SIDE-BY-SIDE ITEMIZED ELECTRICITY BILL COMPARISON ({currency_code})", size=8.2, bold=True, rgb=(1.0, 1.0, 1.0))
    pdf.y -= 15.0

    # Table Header
    pdf.draw_rect(36, pdf.y, 523, 14, fill_rgb=(0.86, 0.89, 0.93))
    pdf.draw_text(42, pdf.y - 10, "Pos. & Cost Component", size=7.4, bold=True)
    pdf.draw_text(340, pdf.y - 10, f"Baseline (No BESS)", size=7.4, bold=True, align="right")
    pdf.draw_text(445, pdf.y - 10, f"With BESS", size=7.4, bold=True, align="right")
    pdf.draw_text(553, pdf.y - 10, f"Delta / Savings", size=7.4, bold=True, align="right")
    pdf.y -= 14.0

    for idx, row in enumerate(comparison_rows):
        pdf.ensure_space(14.5)
        is_summary = bool(row.get("is_summary", False))
        is_header = bool(row.get("is_header", False))
        if is_header:
            pdf.draw_rect(36, pdf.y, 523, 13.5, fill_rgb=(0.20, 0.27, 0.36))
            pdf.draw_text(42, pdf.y - 9.5, str(row["component"]), size=7.6, bold=True, rgb=(1.0, 1.0, 1.0))
            pdf.y -= 13.5
            continue

        bg = (0.88, 0.94, 0.90) if is_summary else ((0.98, 0.99, 1.0) if idx % 2 == 0 else (0.94, 0.96, 0.98))
        pdf.draw_rect(36, pdf.y, 523, 13.5, fill_rgb=bg, stroke_rgb=(0.84, 0.87, 0.90), line_w=0.3)
        pdf.draw_text(42, pdf.y - 9.5, str(row["component"]), size=7.4 if not is_summary else 7.8, bold=is_summary, max_chars=56)
        pdf.draw_text(340, pdf.y - 9.5, str(row["baseline_str"]), size=7.4 if not is_summary else 7.8, bold=is_summary, align="right")
        pdf.draw_text(445, pdf.y - 9.5, str(row["bess_str"]), size=7.4 if not is_summary else 7.8, bold=is_summary, align="right")
        pdf.draw_text(553, pdf.y - 9.5, str(row["delta_str"]), size=7.4 if not is_summary else 7.8, bold=True, align="right")
        pdf.y -= 13.5

    return pdf.build_bytes()

