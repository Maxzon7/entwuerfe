"""
========================================================================================
Scenario & Project Domain Models (current_model/models/scenario.py)
========================================================================================

Description:
------------
Defines the core 1-to-N Scenario Architecture:
  - `BaseScenario`: The immutable Status Quo benchmark anchor containing the facility
    load profile, active grid contract, geographic location, and baseline financial trajectory.
  - `SubScenario`: An isolated branchable solution path combining arbitrary hardware
    modules (Solar PV, BESS, Generator, Alternative Grid Tariff), with explicit opt-in flags,
    independent dispatch results, and comparative ROI metrics against the Base Scenario.
  - `ProjectContainer`: Top-level multi-scenario workspace container supporting full
    `.dracproj` / JSON serialization, scenario cloning, management, and export.
"""

import json
import uuid
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from current_model.models.load_component import SimpleConsumer
from current_model.models.contract import Contract
from current_model.models.solar import SolarLocation, SolarPVConfig, SolarFinancialConfig
from current_model.models.bess import BESSConfig
from current_model.models.generator import GeneratorConfig


@dataclass
class BaseScenario:
    """
    Represents the immutable Status Quo benchmark scenario.
    All return-on-investment, net present value, and avoided cost metrics across all
    sub-scenarios are strictly computed against this baseline.
    """
    name: str = "Status Quo (Base Scenario)"
    description: str = "Baseline facility demand and utility electricity contract without intervention."
    
    # Load Profile Modeling Data
    load_source_type: str = "synthetic"           # "synthetic" or "csv"
    load_profile_name: str = "Baseline Facility Load"
    synthetic_horizon: str = "Full Year (365 Days / 35,040 Steps)"
    consumers: List[SimpleConsumer] = field(default_factory=list)
    holidays: List[Dict[str, str]] = field(default_factory=list)
    
    # CSV Real Meter Data (if active)
    csv_filename: Optional[str] = None
    csv_power_column: Optional[str] = None
    csv_data_records: Optional[List[Dict[str, Any]]] = None
    
    # Grid Utility Contract
    base_contract: Optional[Contract] = None
    
    # Geographic Location
    location: Optional[SolarLocation] = None
    
    # Cached Baseline KPIs (Calculated against Base Contract)
    baseline_annual_kwh: float = 0.0
    baseline_peak_kw: float = 0.0
    baseline_annual_cost: float = 0.0
    baseline_15year_cost: float = 0.0
    baseline_payment_schedule: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes BaseScenario to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "load_source_type": self.load_source_type,
            "load_profile_name": self.load_profile_name,
            "synthetic_horizon": self.synthetic_horizon,
            "consumers": [c.to_dict() for c in self.consumers],
            "holidays": self.holidays,
            "csv_filename": self.csv_filename,
            "csv_power_column": self.csv_power_column,
            "csv_data_records": self.csv_data_records,
            "base_contract": self.base_contract.to_dict() if self.base_contract else None,
            "location": self.location.to_dict() if self.location else None,
            "baseline_annual_kwh": float(self.baseline_annual_kwh),
            "baseline_peak_kw": float(self.baseline_peak_kw),
            "baseline_annual_cost": float(self.baseline_annual_cost),
            "baseline_15year_cost": float(self.baseline_15year_cost),
            "baseline_payment_schedule": self.baseline_payment_schedule
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseScenario":
        """Deserializes dictionary into BaseScenario."""
        if not data:
            return cls()
        
        raw_consumers = data.get("consumers", [])
        consumers = [SimpleConsumer.from_dict(c) for c in raw_consumers if isinstance(c, dict)]
        
        raw_contract = data.get("base_contract")
        contract = Contract.from_dict(raw_contract) if raw_contract else None
        
        raw_loc = data.get("location")
        location = SolarLocation.from_dict(raw_loc) if raw_loc else None
        
        return cls(
            name=data.get("name", "Status Quo (Base Scenario)"),
            description=data.get("description", ""),
            load_source_type=data.get("load_source_type", "synthetic"),
            load_profile_name=data.get("load_profile_name", "Baseline Facility Load"),
            synthetic_horizon=data.get("synthetic_horizon", "Full Year (365 Days / 35,040 Steps)"),
            consumers=consumers,
            holidays=data.get("holidays", []),
            csv_filename=data.get("csv_filename"),
            csv_power_column=data.get("csv_power_column"),
            csv_data_records=data.get("csv_data_records"),
            base_contract=contract,
            location=location,
            baseline_annual_kwh=float(data.get("baseline_annual_kwh", 0.0)),
            baseline_peak_kw=float(data.get("baseline_peak_kw", 0.0)),
            baseline_annual_cost=float(data.get("baseline_annual_cost", 0.0)),
            baseline_15year_cost=float(data.get("baseline_15year_cost", 0.0)),
            baseline_payment_schedule=data.get("baseline_payment_schedule", [])
        )


@dataclass
class SubScenario:
    """
    Represents an isolated proposed technical and commercial solution path.
    Can activate any arbitrary combination of Solar PV, BESS, Generator, and Alternative Tariff.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Sub-Scenario 1"
    description: str = ""
    color_code: str = "#2563EB"                   # Hex color for multi-curve charting
    is_active: bool = True

    # Explicit Component Opt-In Switches
    include_solar: bool = False
    include_bess: bool = False
    include_generator: bool = False
    use_custom_grid_tariff: bool = False

    # Component Configurations
    solar_config: Optional[SolarPVConfig] = None
    solar_financial: Optional[SolarFinancialConfig] = None
    bess_config: Optional[BESSConfig] = None
    generator_config: Optional[GeneratorConfig] = None
    custom_contract: Optional[Contract] = None

    # Performance & Financial Results (Populated by Dispatch Engine)
    summary_kpis: Dict[str, Any] = field(default_factory=dict)
    financial_cashflows: List[Dict[str, Any]] = field(default_factory=list)
    dispatch_records: Optional[List[Dict[str, Any]]] = None

    @property
    def technology_mix_label(self) -> str:
        """Returns a concise description of active technologies."""
        techs = []
        if self.include_solar:
            techs.append("Solar PV")
        if self.include_bess:
            techs.append("BESS")
        if self.include_generator:
            techs.append("Genset")
        if self.use_custom_grid_tariff:
            techs.append("Alt Grid Tariff")
        return " + ".join(techs) if techs else "Grid Only (No Active Modules)"

    def clone(self, new_id: Optional[str] = None, new_name: Optional[str] = None) -> "SubScenario":
        """
        Creates an exact deep copy clone of this sub-scenario with an independent ID and name.
        Ideal for rapid sizing sensitivity tests.
        """
        data = self.to_dict()
        data["id"] = new_id if new_id else str(uuid.uuid4())[:8]
        data["name"] = new_name if new_name else f"{self.name} (Copy)"
        return SubScenario.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes SubScenario to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color_code": self.color_code,
            "is_active": bool(self.is_active),
            "include_solar": bool(self.include_solar),
            "include_bess": bool(self.include_bess),
            "include_generator": bool(self.include_generator),
            "use_custom_grid_tariff": bool(self.use_custom_grid_tariff),
            "solar_config": self.solar_config.to_dict() if self.solar_config else None,
            "solar_financial": self.solar_financial.to_dict() if self.solar_financial else None,
            "bess_config": self.bess_config.to_dict() if self.bess_config else None,
            "generator_config": self.generator_config.to_dict() if self.generator_config else None,
            "custom_contract": self.custom_contract.to_dict() if self.custom_contract else None,
            "summary_kpis": self.summary_kpis,
            "financial_cashflows": self.financial_cashflows,
            "dispatch_records": self.dispatch_records
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubScenario":
        """Deserializes dictionary into SubScenario."""
        if not data:
            return cls()

        raw_solar_cfg = data.get("solar_config")
        solar_cfg = SolarPVConfig.from_dict(raw_solar_cfg) if raw_solar_cfg else None

        raw_solar_fin = data.get("solar_financial")
        solar_fin = SolarFinancialConfig.from_dict(raw_solar_fin) if raw_solar_fin else None

        raw_bess = data.get("bess_config")
        bess_cfg = BESSConfig.from_dict(raw_bess) if raw_bess else None

        raw_gen = data.get("generator_config")
        gen_cfg = GeneratorConfig.from_dict(raw_gen) if raw_gen else None

        raw_contract = data.get("custom_contract")
        custom_contract = Contract.from_dict(raw_contract) if raw_contract else None

        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Sub-Scenario"),
            description=data.get("description", ""),
            color_code=data.get("color_code", "#2563EB"),
            is_active=bool(data.get("is_active", True)),
            include_solar=bool(data.get("include_solar", False)),
            include_bess=bool(data.get("include_bess", False)),
            include_generator=bool(data.get("include_generator", False)),
            use_custom_grid_tariff=bool(data.get("use_custom_grid_tariff", False)),
            solar_config=solar_cfg,
            solar_financial=solar_fin,
            bess_config=bess_cfg,
            generator_config=gen_cfg,
            custom_contract=custom_contract,
            summary_kpis=data.get("summary_kpis", {}),
            financial_cashflows=data.get("financial_cashflows", []),
            dispatch_records=data.get("dispatch_records")
        )


@dataclass
class ProjectContainer:
    """
    Top-level project workspace container housing the immutable Base Scenario,
    all 1-to-N Sub-Scenarios, metadata, and serialization pipelines.
    """
    format: str = "drac_simulation_project"
    version: str = "1.0"
    project_name: str = "Energy Transition Simulation Project"
    description: str = ""
    author: str = "DRACBV Consultant"
    currency: str = "EUR"
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    base_scenario: BaseScenario = field(default_factory=BaseScenario)
    sub_scenarios: List[SubScenario] = field(default_factory=list)
    active_sub_scenario_id: Optional[str] = None

    def add_sub_scenario(self, scenario: SubScenario) -> None:
        """Adds a new sub-scenario and activates it."""
        self.sub_scenarios.append(scenario)
        self.active_sub_scenario_id = scenario.id
        self.updated_at = datetime.datetime.utcnow().isoformat()

    def get_sub_scenario(self, scenario_id: str) -> Optional[SubScenario]:
        """Finds a sub-scenario by its unique ID."""
        for s in self.sub_scenarios:
            if s.id == scenario_id:
                return s
        return None

    def get_active_scenario(self) -> Optional[SubScenario]:
        """Returns the currently active sub-scenario, or first if not specified."""
        if not self.sub_scenarios:
            return None
        if self.active_sub_scenario_id:
            s = self.get_sub_scenario(self.active_sub_scenario_id)
            if s:
                return s
        return self.sub_scenarios[0]

    def duplicate_sub_scenario(self, scenario_id: str, new_name: Optional[str] = None) -> Optional[SubScenario]:
        """Duplicates an existing sub-scenario and adds it to the project."""
        original = self.get_sub_scenario(scenario_id)
        if not original:
            return None
        cloned = original.clone(new_name=new_name)
        # Assign distinct color
        colors = ["#2563EB", "#059669", "#D97706", "#DC2626", "#7C3AED", "#DB2777", "#0891B2"]
        cloned.color_code = colors[len(self.sub_scenarios) % len(colors)]
        self.add_sub_scenario(cloned)
        return cloned

    def delete_sub_scenario(self, scenario_id: str) -> bool:
        """Deletes a sub-scenario from the project."""
        initial_len = len(self.sub_scenarios)
        self.sub_scenarios = [s for s in self.sub_scenarios if s.id != scenario_id]
        if len(self.sub_scenarios) < initial_len:
            if self.active_sub_scenario_id == scenario_id:
                self.active_sub_scenario_id = self.sub_scenarios[0].id if self.sub_scenarios else None
            self.updated_at = datetime.datetime.utcnow().isoformat()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the complete project container to a JSON-ready dictionary."""
        return {
            "format": self.format,
            "version": self.version,
            "project_name": self.project_name,
            "description": self.description,
            "author": self.author,
            "currency": self.currency,
            "created_at": self.created_at,
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "active_sub_scenario_id": self.active_sub_scenario_id,
            "base_scenario": self.base_scenario.to_dict(),
            "sub_scenarios": [s.to_dict() for s in self.sub_scenarios]
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes the project container to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectContainer":
        """Deserializes dictionary into ProjectContainer."""
        if not data:
            return cls()

        raw_base = data.get("base_scenario", {})
        base_scenario = BaseScenario.from_dict(raw_base)

        raw_sub = data.get("sub_scenarios", [])
        sub_scenarios = [SubScenario.from_dict(s) for s in raw_sub if isinstance(s, dict)]

        return cls(
            format=data.get("format", "drac_simulation_project"),
            version=data.get("version", "1.0"),
            project_name=data.get("project_name", "Energy Transition Project"),
            description=data.get("description", ""),
            author=data.get("author", "DRACBV Consultant"),
            currency=data.get("currency", "EUR"),
            created_at=data.get("created_at", datetime.datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.datetime.utcnow().isoformat()),
            active_sub_scenario_id=data.get("active_sub_scenario_id"),
            base_scenario=base_scenario,
            sub_scenarios=sub_scenarios
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ProjectContainer":
        """Deserializes JSON string into ProjectContainer."""
        data = json.loads(json_str)
        return cls.from_dict(data)
