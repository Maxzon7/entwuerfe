"""
========================================================================================
Electricity Supply Contract & Tariff Model (current_model/models/contract.py)
========================================================================================

Description:
------------
Defines the `Contract` dataclass encapsulating all billing, capacity limits,
dynamic Time-of-Use (TOU) energy rates, reactive power penalties, and custom tax structures.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional
import datetime


@dataclass
class Contract:
    """
    Represents an electricity supply contract with dynamic Time-of-Use (TOU) rate windows,
    capacity tariffs, reactive energy thresholds, and taxes.
    """
    name: str = "Electricity Contract"
    currency: str = "EUR"
    base_monthly_fee: float = 50.0

    # Active Power & Capacity Parameters
    contracted_capacity_kw: float = 400.0          # Contracted active capacity limit (kW)
    monthly_capacity_tariff: float = 0.15          # Capacity charge (€/kW/month - Uso de Red)
    demand_capacity_tariff: float = 0.0            # Measured Peak Demand Charge (€/kW/month - Consumo de Potencia)
    max_physical_limit_kw: float = 1000.0          # Absolute physical grid fuse limit (kW)
    peak_penalty_rate: float = 0.25                # Penalty rate for exceeding contracted capacity (€/kW)

    # Reactive Power Parameters
    reactive_power_tariff: float = 0.03            # Tariff for excess reactive energy (€/kVARh)
    min_power_factor: float = 0.90                 # Minimum allowed power factor (cos phi)
    reactive_power_allowance_pct: float = 33.0     # Free reactive allowance as % of active kWh

    # Dynamic Time-of-Use (TOU) Energy Rates Table
    # By default: 1 standard entry covering 24 hours
    tou_rates: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}
    ])
    default_energy_rate: float = 0.20              # Fallback rate (€/kWh)
    weekend_is_off_peak: bool = False

    # Taxes & Additional Fees (Dynamic Table)
    taxes_and_fees: List[Dict[str, Any]] = field(default_factory=list)


    def _parse_time_to_minutes(self, t_val: Any) -> int:
        """Helper to convert time string, int hour, or datetime.time to minutes of day [0, 1440]."""
        if isinstance(t_val, (datetime.time, datetime.datetime)):
            return t_val.hour * 60 + t_val.minute
        s = str(t_val).strip()
        if ":" in s:
            parts = s.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return h * 60 + m
        try:
            return int(float(s)) * 60
        except ValueError:
            return 0

    def get_energy_rate(self, dt_or_hour: Any) -> float:
        """
        Returns the active energy price (€/kWh) for a given hour (int), time, or datetime object
        by matching against the configured dynamic TOU rate windows.
        """
        if isinstance(dt_or_hour, datetime.datetime):
            if self.weekend_is_off_peak and dt_or_hour.weekday() >= 5:
                # Return minimum available rate for weekend off-peak
                rates = [float(r.get("rate", self.default_energy_rate)) for r in self.tou_rates if "rate" in r]
                return min(rates) if rates else self.default_energy_rate
            current_m = dt_or_hour.hour * 60 + dt_or_hour.minute
        elif isinstance(dt_or_hour, datetime.time):
            current_m = dt_or_hour.hour * 60 + dt_or_hour.minute
        else:
            try:
                current_m = int(dt_or_hour) * 60
            except (ValueError, TypeError):
                current_m = 0

        if not self.tou_rates:
            return self.default_energy_rate

        # Iterate through dynamic TOU windows (last matching or first matching)
        for tou in self.tou_rates:
            start_m = self._parse_time_to_minutes(tou.get("start_time", "00:00"))
            end_m = self._parse_time_to_minutes(tou.get("end_time", "24:00"))
            rate = float(tou.get("rate", self.default_energy_rate))

            # Full 24-hour window
            if (start_m == 0 and end_m >= 1440) or (start_m == 0 and end_m == 0 and len(self.tou_rates) == 1):
                return rate

            # Standard window (e.g. 08:00 to 20:00 -> 480 to 1200)
            if start_m < end_m:
                if start_m <= current_m < end_m:
                    return rate
            # Overnight window (e.g. 22:00 to 06:00 -> 1320 to 360)
            elif start_m > end_m:
                if current_m >= start_m or current_m < end_m:
                    return rate

        # Fallback to default or first rate
        return float(self.tou_rates[0].get("rate", self.default_energy_rate))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Contract to a clean JSON-ready dictionary."""
        return {
            "format": "drac_contract",
            "version": "1.0",
            "name": self.name,
            "currency": self.currency,
            "base_monthly_fee": float(self.base_monthly_fee),
            "contracted_capacity_kw": float(self.contracted_capacity_kw),
            "monthly_capacity_tariff": float(self.monthly_capacity_tariff),
            "demand_capacity_tariff": float(self.demand_capacity_tariff),
            "max_physical_limit_kw": float(self.max_physical_limit_kw),
            "peak_penalty_rate": float(self.peak_penalty_rate),
            "reactive_power_tariff": float(self.reactive_power_tariff),
            "min_power_factor": float(self.min_power_factor),
            "reactive_power_allowance_pct": float(self.reactive_power_allowance_pct),
            "tou_rates": [
                {
                    "name": str(r.get("name", "Tariff")),
                    "rate": float(r.get("rate", self.default_energy_rate)),
                    "start_time": str(r.get("start_time", "00:00")),
                    "end_time": str(r.get("end_time", "24:00"))
                }
                for r in self.tou_rates
            ],
            "default_energy_rate": float(self.default_energy_rate),
            "weekend_is_off_peak": bool(self.weekend_is_off_peak),
            "taxes_and_fees": [
                {
                    "name": str(t.get("name", "")),
                    "type": str(t.get("type", "percentage")),
                    "value": float(t.get("value", 0.0)),
                    "description": str(t.get("description", ""))
                }
                for t in self.taxes_and_fees
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        """Deserializes a dictionary or JSON payload into a Contract instance."""
        if not isinstance(data, dict):
            return cls()

        name = str(data.get("name", data.get("contract_name", "Electricity Contract")))
        currency = str(data.get("currency", "EUR")).upper().strip()
        base_monthly_fee = float(data.get("base_monthly_fee", 50.0))
        contracted_capacity_kw = float(data.get("contracted_capacity_kw", 400.0))
        monthly_capacity_tariff = float(data.get("monthly_capacity_tariff", 0.15))
        demand_capacity_tariff = float(data.get("demand_capacity_tariff", 0.0))
        max_physical_limit_kw = float(data.get("max_physical_limit_kw", 1000.0))
        peak_penalty_rate = float(data.get("peak_penalty_rate", 0.25))
        reactive_power_tariff = float(data.get("reactive_power_tariff", 0.03))
        min_power_factor = float(data.get("min_power_factor", 0.90))
        reactive_power_allowance_pct = float(data.get("reactive_power_allowance_pct", 33.0))
        weekend_is_off_peak = bool(data.get("weekend_is_off_peak", False))

        raw_tou = data.get("tou_rates", [])
        tou_rates = []
        if isinstance(raw_tou, list) and len(raw_tou) > 0:
            for r in raw_tou:
                if isinstance(r, dict):
                    tou_rates.append({
                        "name": str(r.get("name", "Tariff")),
                        "rate": float(r.get("rate", 0.20)),
                        "start_time": str(r.get("start_time", "00:00")),
                        "end_time": str(r.get("end_time", "24:00"))
                    })

        default_energy_rate = float(data.get("default_energy_rate", 0.20))
        if not tou_rates:
            tou_rates = [{"name": "Standard Rate", "rate": default_energy_rate, "start_time": "00:00", "end_time": "24:00"}]
        else:
            default_energy_rate = float(tou_rates[0].get("rate", default_energy_rate))

        raw_taxes = data.get("taxes_and_fees", [])
        taxes_and_fees = []
        if isinstance(raw_taxes, list):
            for t in raw_taxes:
                if isinstance(t, dict) and t.get("name"):
                    taxes_and_fees.append({
                        "name": str(t.get("name", "")),
                        "type": str(t.get("type", "percentage")),
                        "value": float(t.get("value", 0.0)),
                        "description": str(t.get("description", ""))
                    })

        return cls(
            name=name,
            currency=currency,
            base_monthly_fee=base_monthly_fee,
            contracted_capacity_kw=contracted_capacity_kw,
            monthly_capacity_tariff=monthly_capacity_tariff,
            demand_capacity_tariff=demand_capacity_tariff,
            max_physical_limit_kw=max_physical_limit_kw,
            peak_penalty_rate=peak_penalty_rate,
            reactive_power_tariff=reactive_power_tariff,
            min_power_factor=min_power_factor,
            reactive_power_allowance_pct=reactive_power_allowance_pct,
            tou_rates=tou_rates,
            default_energy_rate=default_energy_rate,
            weekend_is_off_peak=weekend_is_off_peak,
            taxes_and_fees=taxes_and_fees
        )

    def to_json(self, indent: int = 2) -> str:
        """Serializes the Contract to a formatted JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Contract":
        """Reconstructs a Contract from a JSON string."""
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)


def get_contract_presets() -> Dict[str, Contract]:
    """Returns standard industry electricity supply contract presets."""
    return {
        "Paula1 (Bodegas Salentein - EDEMSA T2 R MT)": Contract(
            name="Paula1",
            currency="ARS",
            base_monthly_fee=514145.55,
            contracted_capacity_kw=430.0,
            monthly_capacity_tariff=40607.0460,
            demand_capacity_tariff=8554.4390,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=40607.0460,
            reactive_power_tariff=0.0,
            min_power_factor=0.90,
            reactive_power_allowance_pct=33.0,
            tou_rates=[
                {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "00:00", "end_time": "05:00"},
                {"name": "Resto (05:00 - 18:00)", "rate": 66.7737, "start_time": "05:00", "end_time": "18:00"},
                {"name": "Pico (18:00 - 23:00)", "rate": 68.4335, "start_time": "18:00", "end_time": "23:00"},
                {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "23:00", "end_time": "24:00"}
            ],
            default_energy_rate=66.7737,
            weekend_is_off_peak=False,
            taxes_and_fees=[
                {"name": "I.V.A. Resp. Inscripto", "type": "percentage", "value": 27.00, "description": "IVA Nacional"},
                {"name": "CCCE art 74 inc d) Ley 6497", "type": "percentage", "value": 9.00, "description": "Fondo Compensador Provincial"},
                {"name": "Impuestos Provinciales IIBB Ley 6922/8398", "type": "percentage", "value": 3.09, "description": "Ingresos Brutos"},
                {"name": "Tasa Fisc. y Control art 64 Ley 6497", "type": "percentage", "value": 1.50, "description": "EPRE Fiscalización"},
                {"name": "Sobretasa Provincial Ley 2539", "type": "percentage", "value": 1.00, "description": "Sobretasa Provincial"},
                {"name": "Imp. Sellos Art 240 Ley 8523", "type": "percentage", "value": 1.00, "description": "Impuesto de Sellos"},
                {"name": "Cargo AP Municipal Ord. 3028", "type": "fixed_monthly", "value": 43091.00, "description": "Alumbrado Público Municipal"}
            ]
        ),
        "Industrial Multi-Tariff (EUR)": Contract(
            name="Industrial Multi-Tariff Contract",
            currency="EUR",
            base_monthly_fee=120.0,
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=0.18,
            demand_capacity_tariff=2.50,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=0.45,
            reactive_power_tariff=0.035,
            min_power_factor=0.92,
            reactive_power_allowance_pct=33.0,
            tou_rates=[
                {"name": "Off-Peak (Valle)", "rate": 0.12, "start_time": "00:00", "end_time": "08:00"},
                {"name": "Mid-Peak (Llano)", "rate": 0.18, "start_time": "08:00", "end_time": "18:00"},
                {"name": "On-Peak (Punta)", "rate": 0.28, "start_time": "18:00", "end_time": "23:00"},
                {"name": "Off-Peak (Valle)", "rate": 0.12, "start_time": "23:00", "end_time": "24:00"}
            ],
            default_energy_rate=0.18,
            weekend_is_off_peak=True,
            taxes_and_fees=[
                {"name": "Electricity Tax", "type": "percentage", "value": 5.11, "description": "National energy excise"},
                {"name": "VAT / MwSt", "type": "percentage", "value": 19.0, "description": "Value added tax"}
            ]
        ),
        "Commercial Standard Fixed (EUR)": Contract(
            name="Commercial Standard Fixed Contract",
            currency="EUR",
            base_monthly_fee=45.0,
            contracted_capacity_kw=100.0,
            monthly_capacity_tariff=0.14,
            demand_capacity_tariff=0.0,
            max_physical_limit_kw=250.0,
            peak_penalty_rate=0.30,
            reactive_power_tariff=0.03,
            min_power_factor=0.90,
            reactive_power_allowance_pct=33.0,
            tou_rates=[
                {"name": "Flat Commercial Rate", "rate": 0.22, "start_time": "00:00", "end_time": "24:00"}
            ],
            default_energy_rate=0.22,
            weekend_is_off_peak=False,
            taxes_and_fees=[
                {"name": "VAT / MwSt", "type": "percentage", "value": 19.0, "description": "Standard VAT"}
            ]
        ),
        "Argentine T3 Grandes Demandas (ARS)": Contract(
            name="Tarifa T3 Grandes Demandas",
            currency="ARS",
            base_monthly_fee=15500.0,
            contracted_capacity_kw=300.0,
            monthly_capacity_tariff=3200.0,
            demand_capacity_tariff=1850.0,
            max_physical_limit_kw=800.0,
            peak_penalty_rate=4500.0,
            reactive_power_tariff=12.5,
            min_power_factor=0.85,
            reactive_power_allowance_pct=40.0,
            tou_rates=[
                {"name": "Valle Nocturno", "rate": 65.20, "start_time": "00:00", "end_time": "05:00"},
                {"name": "Resto", "rate": 78.40, "start_time": "05:00", "end_time": "18:00"},
                {"name": "Pico", "rate": 95.80, "start_time": "18:00", "end_time": "23:00"},
                {"name": "Valle Nocturno", "rate": 65.20, "start_time": "23:00", "end_time": "24:00"}
            ],
            default_energy_rate=78.40,
            weekend_is_off_peak=False,
            taxes_and_fees=[
                {"name": "IVA General", "type": "percentage", "value": 21.0, "description": "Impuesto al Valor Agregado"},
                {"name": "Tasa Municipal / Alumbrado", "type": "percentage", "value": 6.0, "description": "Contribución municipal"}
            ]
        )
    }


