from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from src.calculations.decision import DecisionEngine
from src.calculations.forensic import ForensicAnalyzer
from src.calculations.ratios import RatioCalculator
from src.calculations.repository import RatioRepository
from src.calculations.scenario import ScenarioAnalyzer
from src.calculations.technical import TechnicalAnalyzer
from src.calculations.valuation import ValuationEngine
from src.config import load_config
from src.database import get_connection, init_db
from src.models import NormalizedCompany


@dataclass
class AnalysisBundle:
    """All engine outputs for one company."""

    company: NormalizedCompany
    ratios: Any = None
    forensic: Any = None
    technical: Any = None
    valuation: Any = None
    scenario: Any = None
    decision: Any = None
    assumptions: list[str] = field(default_factory=list)


class AnalysisWorker(QThread):
    """Computes every analysis engine off the UI thread."""

    done = Signal(object)
    error = Signal(str)

    def __init__(self, ticker: str) -> None:
        super().__init__()
        self.ticker = ticker

    def run(self) -> None:
        try:
            config = load_config()
            conn = get_connection(config.database.path)
            init_db(conn)
            company = RatioRepository(conn).load_normalized_company(self.ticker)
        except Exception as exc:
            self.error.emit(str(exc))
            return

        bundle = AnalysisBundle(company=company)

        try:
            bundle.ratios = RatioCalculator().calculate_all(company)
        except Exception as exc:
            bundle.assumptions.append(f"Ratio analysis unavailable: {exc}")

        try:
            bundle.forensic = ForensicAnalyzer().analyze(company)
        except Exception as exc:
            bundle.assumptions.append(f"Forensic analysis unavailable: {exc}")

        if company.prices:
            try:
                bundle.technical = TechnicalAnalyzer().analyze_prices(company.prices, company.company.ticker)
            except Exception as exc:
                bundle.assumptions.append(f"Technical analysis unavailable: {exc}")
        else:
            bundle.assumptions.append("No price data available; technical analysis skipped.")

        try:
            bundle.valuation = ValuationEngine().analyze(company, [])
        except Exception as exc:
            bundle.assumptions.append(f"Valuation unavailable: {exc}")

        try:
            bundle.scenario = ScenarioAnalyzer().analyze(company)
        except Exception as exc:
            bundle.assumptions.append(f"Scenario analysis unavailable: {exc}")

        try:
            bundle.decision = DecisionEngine().decide(
                valuation_report=bundle.valuation,
                forensic_report=bundle.forensic,
                scenario_report=bundle.scenario,
                technical_report=bundle.technical,
                ratio_set=bundle.ratios,
            )
        except Exception as exc:
            bundle.assumptions.append(f"Investment decision unavailable: {exc}")

        self.done.emit(bundle)
