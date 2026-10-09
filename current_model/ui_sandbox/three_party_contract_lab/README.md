# :material/bolt: 3-Party Unbundled Electricity Contract Laboratory (`three_party_contract_lab`)

An isolated, single-page sandbox laboratory demonstrating the European 3-Party Unbundled Electricity Market Architecture coupled with 15-minute interval CSV consumption profiles.

---

## :material/folder_open: Structure

- [`minimal_contract_system.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/three_party_contract_lab/minimal_contract_system.py): Complete standalone Streamlit application and domain model (`ThreePartyContract`) covering:
  1. **Regulated Grid Operator (DSO / Netbeheerder)**: Contracted capacity, peak demand, volume transport, overload charges.
  2. **Certified Metering Company (Meetbedrijf)**: RLM interval meter rental, remote GSM telemetry.
  3. **Competitive Energy Supplier (Energieleverancier)**: Commodity power (Fixed TOU or Spot), retail margin (*Opslag*).
  4. **Statutory Taxes & Levies**: VAT/BTW, energy taxes (*Energiebelasting*), and municipal concessions.

---

## :material/play_arrow: Running Directly

```bash
python -m streamlit run current_model/ui_sandbox/three_party_contract_lab/minimal_contract_system.py
```
