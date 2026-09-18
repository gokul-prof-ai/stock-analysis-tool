from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..calculations.decision import DecisionEngine
from ..calculations.financial_extractor import FinancialExtractor, normalize_token
from ..calculations.forensic import ForensicAnalyzer
from ..calculations.industry import IndustryAnalyzer
from ..calculations.ratios import RatioCalculator
from ..calculations.risk import RiskAnalyzer
from ..calculations.scenario import ScenarioAnalyzer
from ..calculations.technical import TechnicalAnalyzer
from ..calculations.technical_charts import TechnicalChartGenerator
from ..calculations.valuation import ValuationEngine
from ..models import NormalizedCompany
from ..models.report import (
    FinalReport,
    InvestmentDecision,
    ReportSection,
    ReportTable,
    RiskMetrics,
)
from .checklist import build_checklist


class ReportBuilder:
    """Builds the final capstone report from all analysis engines."""

    def __init__(self, chart_dir: str | Path | None = None) -> None:
        self.chart_dir = Path(chart_dir) if chart_dir is not None else None

    def build(
        self,
        company: NormalizedCompany,
        candidates: list[NormalizedCompany] | None = None,
    ) -> FinalReport:
        candidates = candidates or []
        assumptions: list[str] = []
        sections: list[ReportSection] = []
        chart_paths: dict[str, str] = {}

        extractor = FinancialExtractor(company)
        latest_year = extractor.latest_fiscal_year()
        latest_snapshot = extractor.snapshot(latest_year) if latest_year is not None else None

        sections.append(self._company_section(company))

        statement_tables, statement_presence = self._financial_statement_tables(company)
        sections.append(
            ReportSection(
                title="Financial Statements",
                summary="Normalized financial statement line items extracted from the ingested source.",
                tables=statement_tables,
            )
        )

        ratio_set = self._safe(
            lambda: RatioCalculator().calculate_all(company),
            assumptions,
            "Ratio analysis unavailable.",
        )
        sections.append(self._ratio_section(ratio_set))

        forensic_report = self._safe(
            lambda: ForensicAnalyzer().analyze(company),
            assumptions,
            "Forensic analysis unavailable.",
        )
        sections.append(self._forensic_section(forensic_report))

        industry_report = None
        if candidates:
            industry_report = self._safe(
                lambda: IndustryAnalyzer().analyze(company, candidates),
                assumptions,
                "Industry analysis unavailable.",
            )
        else:
            assumptions.append("No peer candidates provided; industry analysis is partial.")

        sections.append(self._industry_section(industry_report))

        technical_report = None
        if company.prices:
            technical_report = self._safe(
                lambda: TechnicalAnalyzer().analyze_prices(company.prices, ticker=company.company.ticker),
                assumptions,
                "Technical analysis unavailable.",
            )

            if technical_report is not None and self.chart_dir is not None:
                try:
                    generated = TechnicalChartGenerator(technical_report).generate_all(self.chart_dir)
                    chart_paths = {name: str(path) for name, path in generated.items()}
                except Exception:
                    assumptions.append("Technical chart export failed.")
        else:
            assumptions.append("No price data provided; technical analysis unavailable.")

        sections.append(self._technical_section(technical_report, chart_paths))

        valuation_report = self._safe(
            lambda: ValuationEngine().analyze(company, candidates),
            assumptions,
            "Valuation analysis unavailable.",
        )
        sections.append(self._valuation_section(valuation_report))

        scenario_report = self._safe(
            lambda: ScenarioAnalyzer().analyze(company),
            assumptions,
            "Scenario analysis unavailable.",
        )
        sections.append(self._scenario_section(scenario_report))

        risk_metrics = None
        if company.prices:
            risk_metrics = self._safe(
                lambda: RiskAnalyzer().analyze_prices(company.prices),
                assumptions,
                "Risk metrics unavailable.",
            )

        dividend_present, dividend_section = self._dividend_section(company)
        sections.append(dividend_section)

        shareholding_present, shareholding_section = self._shareholding_section(company)
        sections.append(shareholding_section)

        sections.append(self._governance_section())
        sections.append(self._risk_section(forensic_report, risk_metrics))

        decision = DecisionEngine().decide(
            valuation_report=valuation_report,
            forensic_report=forensic_report,
            scenario_report=scenario_report,
            technical_report=technical_report,
            ratio_set=ratio_set,
        )

        sections.append(self._decision_section(decision))

        section_status = self._section_status(
            company=company,
            statement_presence=statement_presence,
            ratio_set=ratio_set,
            forensic_report=forensic_report,
            industry_report=industry_report,
            technical_report=technical_report,
            valuation_report=valuation_report,
            scenario_report=scenario_report,
            dividend_present=dividend_present,
            shareholding_present=shareholding_present,
            risk_metrics=risk_metrics,
            decision=decision,
        )

        checklist = build_checklist(section_status)

        executive_summary = self._executive_summary(
            company=company,
            latest_snapshot=latest_snapshot,
            valuation_report=valuation_report,
            forensic_report=forensic_report,
            scenario_report=scenario_report,
            technical_report=technical_report,
            decision=decision,
        )

        core_available = [
            ratio_set is not None,
            forensic_report is not None,
            valuation_report is not None,
            scenario_report is not None,
        ]

        if all(core_available):
            status = "complete"
        elif any(core_available):
            status = "partial"
        else:
            status = "unavailable"

        return FinalReport(
            ticker=company.company.ticker,
            company_name=company.company.name,
            sector=company.company.sector,
            generated_at=datetime.now(),
            executive_summary=executive_summary,
            sections=sections,
            checklist=checklist,
            investment_decision=decision,
            chart_paths=chart_paths,
            assumptions=assumptions,
            status=status,
        )

    def _company_section(self, company: NormalizedCompany) -> ReportSection:
        return ReportSection(
            title="Company & Business",
            summary=(
                f"{company.company.name} ({company.company.ticker}) "
                f"sector: {company.company.sector or 'N/A'}, "
                f"industry: {company.company.industry or 'N/A'}."
            ),
            bullets=[
                f"Financial statement rows: {len(company.financials)}",
                f"Price rows: {len(company.prices)}",
                f"Shareholding rows: {len(company.shareholding)}",
            ],
        )

    def _financial_statement_tables(
        self,
        company: NormalizedCompany,
    ) -> tuple[list[ReportTable], dict[str, bool]]:
        years = sorted({line.fiscal_year for line in company.financials})
        presence = {
            "balance_sheet": False,
            "pnl": False,
            "cashflow": False,
        }

        if not years:
            return [], presence

        latest = years[-1]
        prior = years[-2] if len(years) >= 2 else None

        tables: list[ReportTable] = []
        statement_labels = {
            "balance_sheet": "Balance Sheet",
            "pnl": "Profit & Loss",
            "cashflow": "Cash Flow",
        }

        for statement_type, label in statement_labels.items():
            latest_items = {
                line.line_item: line.value
                for line in company.financials
                if line.fiscal_year == latest and line.statement_type == statement_type
            }

            if not latest_items:
                continue

            presence[statement_type] = True

            prior_items = {}
            if prior is not None:
                prior_items = {
                    line.line_item: line.value
                    for line in company.financials
                    if line.fiscal_year == prior and line.statement_type == statement_type
                }

            headers = ["Line Item", str(latest)]
            if prior is not None:
                headers.append(str(prior))

            rows = []
            for line_item in sorted(latest_items):
                row = [line_item, latest_items[line_item]]

                if prior is not None:
                    row.append(prior_items.get(line_item))

                rows.append(row)

            tables.append(ReportTable(title=label, headers=headers, rows=rows))

        return tables, presence

    def _ratio_section(self, ratio_set) -> ReportSection:
        if ratio_set is None:
            return ReportSection(
                title="Financial Ratio Analysis",
                summary="Ratio analysis unavailable.",
            )

        rows = [
            [ratio.category, ratio.name, self._text(ratio.value), ratio.status]
            for ratio in ratio_set.ratios
        ]

        return ReportSection(
            title="Financial Ratio Analysis",
            summary=f"Calculated {len(rows)} ratios for fiscal year {ratio_set.fiscal_year}.",
            tables=[
                ReportTable(
                    title="Ratio Results",
                    headers=["Category", "Ratio", "Value", "Status"],
                    rows=rows,
                )
            ],
        )

    def _forensic_section(self, forensic_report) -> ReportSection:
        if forensic_report is None:
            return ReportSection(
                title="Forensic Analysis",
                summary="Forensic analysis unavailable.",
            )

        bullets = [
            f"Fraud probability: {self._text(forensic_report.fraud_probability, 1)}%",
            f"Altman Z: {self._text(forensic_report.altman.z_score)} ({forensic_report.altman.zone})",
            f"Beneish M: {self._text(forensic_report.beneish.m_score)}",
            f"Piotroski F: {forensic_report.piotroski.score if forensic_report.piotroski.score is not None else 'N/A'}/9",
            f"Benford chi-square: {self._text(forensic_report.benford.chi_square)}",
        ]

        rows = [
            [flag.severity, flag.code, flag.message]
            for flag in forensic_report.red_flags
        ]

        tables = []
        if rows:
            tables.append(
                ReportTable(
                    title="Red Flags",
                    headers=["Severity", "Code", "Message"],
                    rows=rows,
                )
            )

        return ReportSection(
            title="Forensic Analysis",
            summary="Fraud-risk and accounting-quality diagnostics.",
            bullets=bullets,
            tables=tables,
        )

    def _industry_section(self, industry_report) -> ReportSection:
        if industry_report is None:
            return ReportSection(
                title="Industry & Peer Analysis",
                summary="Industry analysis unavailable or no peer candidates supplied.",
            )

        peer_rows = [
            [peer.ticker, peer.sector or "N/A", peer.industry or "N/A", self._text(peer.similarity_score, 2)]
            for peer in industry_report.peers
        ]

        porter_rows = [
            [force.force, force.score]
            for force in industry_report.porter.forces
        ]

        tables = []

        if peer_rows:
            tables.append(
                ReportTable(
                    title="Selected Peers",
                    headers=["Ticker", "Sector", "Industry", "Similarity"],
                    rows=peer_rows,
                )
            )

        if porter_rows:
            tables.append(
                ReportTable(
                    title="Porter's Five Forces",
                    headers=["Force", "Score"],
                    rows=porter_rows,
                )
            )

        return ReportSection(
            title="Industry & Peer Analysis",
            summary=(
                f"Selected {len(industry_report.peers)} peers. "
                f"Position classification: {industry_report.position.classification}."
            ),
            tables=tables,
        )

    def _technical_section(self, technical_report, chart_paths: dict[str, str]) -> ReportSection:
        if technical_report is None:
            return ReportSection(
                title="Technical Analysis",
                summary="Technical analysis unavailable because no price data was provided.",
            )

        bullets = [
            f"Latest close: {self._text(technical_report.latest_close, 2)}",
            f"Trend: {technical_report.trend}",
            f"RSI: {self._text(technical_report.latest_rsi, 1)}",
            f"Support levels: {[round(level, 2) for level in technical_report.support_levels]}",
            f"Resistance levels: {[round(level, 2) for level in technical_report.resistance_levels]}",
            f"Patterns detected: {len(technical_report.patterns)}",
            f"Charts exported: {len(chart_paths)}",
        ]

        return ReportSection(
            title="Technical Analysis",
            summary="Price trend, indicator, support/resistance, and pattern analysis.",
            bullets=bullets,
        )

    def _valuation_section(self, valuation_report) -> ReportSection:
        if valuation_report is None:
            return ReportSection(
                title="Valuation",
                summary="Valuation analysis unavailable.",
            )

        multiples_rows = [
            ["P/E", self._text(valuation_report.multiples.pe, 2)],
            ["P/B", self._text(valuation_report.multiples.pb, 2)],
            ["P/S", self._text(valuation_report.multiples.ps, 2)],
            ["EV/EBITDA", self._text(valuation_report.multiples.ev_ebitda, 2)],
        ]

        scenario_rows = [
            [
                scenario.name,
                self._text(scenario.dcf_intrinsic, 2),
                self._text(scenario.comparable_intrinsic, 2),
                self._text(scenario.final_intrinsic, 2),
            ]
            for scenario in valuation_report.scenarios
        ]

        sensitivity_rows = []
        for wacc, row in zip(valuation_report.sensitivity.wacc_values, valuation_report.sensitivity.matrix):
            sensitivity_rows.append([f"{wacc:.2%}"] + [self._text(value, 2) for value in row])

        tables = [
            ReportTable(title="Multiples", headers=["Metric", "Value"], rows=multiples_rows),
            ReportTable(
                title="Valuation Scenarios",
                headers=["Scenario", "DCF", "Comparable", "Final"],
                rows=scenario_rows,
            ),
        ]

        if sensitivity_rows:
            sensitivity_headers = ["WACC"] + [
                f"{terminal:.2%}" for terminal in valuation_report.sensitivity.terminal_growth_values
            ]
            tables.append(
                ReportTable(
                    title="DCF Sensitivity",
                    headers=sensitivity_headers,
                    rows=sensitivity_rows,
                )
            )

        bullets = [
            f"Final intrinsic value/share: {self._text(valuation_report.intrinsic_value, 2)}",
            f"Margin of safety: {self._text(valuation_report.margin_of_safety, 1)}%",
            f"Valuation signal: {valuation_report.valuation_signal}",
        ]

        return ReportSection(
            title="Valuation",
            summary="Relative valuation, DCF scenarios, comparables, and sensitivity.",
            bullets=bullets,
            tables=tables,
        )

    def _scenario_section(self, scenario_report) -> ReportSection:
        if scenario_report is None:
            return ReportSection(
                title="Scenario & Forecast Analysis",
                summary="Scenario analysis unavailable.",
            )

        rows = []
        for scenario in scenario_report.scenarios:
            final_revenue = scenario.revenue[-1].value if scenario.revenue else None
            final_ebitda = scenario.ebitda[-1].value if scenario.ebitda else None
            final_eps = scenario.eps[-1].value if scenario.eps else None

            rows.append(
                [
                    scenario.name,
                    f"{scenario.growth_rate:.2%}",
                    self._text(final_revenue, 2),
                    self._text(final_ebitda, 2),
                    self._text(final_eps, 3),
                    self._text(scenario.target_price, 2),
                    self._text(scenario.upside_pct, 1),
                ]
            )

        tables = [
            ReportTable(
                title="Scenario Forecasts",
                headers=[
                    "Scenario",
                    "Revenue Growth",
                    "Final Revenue",
                    "Final EBITDA",
                    "Final EPS",
                    "Target Price",
                    "Upside %",
                ],
                rows=rows,
            )
        ]

        bullets = [
            f"Base target price: {self._text(scenario_report.base_target_price, 2)}",
            f"Target range: {self._text(scenario_report.target_price_lower, 2)} to {self._text(scenario_report.target_price_upper, 2)}",
            f"Macro overlay adjustment: {scenario_report.macro.adjustment:.2%}",
        ]

        return ReportSection(
            title="Scenario & Forecast Analysis",
            summary="Three-year bull/base/bear forecasts and target-price derivation.",
            bullets=bullets,
            tables=tables,
        )

    def _dividend_section(self, company: NormalizedCompany) -> tuple[bool, ReportSection]:
        dividend_lines = [
            line
            for line in company.financials
            if "dividend" in normalize_token(line.line_item)
        ]

        if not dividend_lines:
            return False, ReportSection(
                title="Dividend Analysis",
                summary="No dividend data was found in the ingested dataset.",
            )

        latest_year = max(line.fiscal_year for line in dividend_lines)
        latest_dividend = sum(
            abs(line.value)
            for line in dividend_lines
            if line.fiscal_year == latest_year
        )

        extractor = FinancialExtractor(company)
        snapshot = extractor.snapshot(latest_year)
        net_profit = snapshot.get("net_profit")
        shares = snapshot.get("shares_outstanding")
        price = extractor.latest_close()

        payout = None
        if net_profit is not None and net_profit > 0:
            payout = latest_dividend / net_profit

        dividend_per_share = None
        dividend_yield = None
        if shares is not None and shares > 0:
            dividend_per_share = latest_dividend / shares

            if price is not None and price > 0:
                dividend_yield = dividend_per_share / price

        bullets = [
            f"Latest dividend amount: {self._text(latest_dividend, 2)}",
            f"Payout ratio: {self._text(payout, 2)}",
            f"Dividend/share: {self._text(dividend_per_share, 3)}",
            f"Dividend yield: {self._text(dividend_yield, 2)}",
        ]

        return True, ReportSection(
            title="Dividend Analysis",
            summary="Dividend payout and yield computed from dividend-related line items.",
            bullets=bullets,
        )

    def _shareholding_section(self, company: NormalizedCompany) -> tuple[bool, ReportSection]:
        if not company.shareholding:
            return False, ReportSection(
                title="Shareholding Analysis",
                summary="No shareholding-pattern data was found in the ingested dataset.",
            )

        rows = [
            [
                row.quarter,
                self._text(row.promoter_pct, 2),
                self._text(row.fii_pct, 2),
                self._text(row.dii_pct, 2),
                self._text(row.public_pct, 2),
            ]
            for row in company.shareholding
        ]

        first = company.shareholding[0]
        latest = company.shareholding[-1]

        promoter_change = None
        if first.promoter_pct is not None and latest.promoter_pct is not None:
            promoter_change = latest.promoter_pct - first.promoter_pct

        bullets = [
            f"Shareholding periods: {len(company.shareholding)}",
            f"Promoter change: {self._text(promoter_change, 2)} percentage points",
        ]

        return True, ReportSection(
            title="Shareholding Analysis",
            summary="Investor-category ownership trend.",
            bullets=bullets,
            tables=[
                ReportTable(
                    title="Shareholding Pattern",
                    headers=["Quarter", "Promoter %", "FII %", "DII %", "Public %"],
                    rows=rows,
                )
            ],
        )

    def _governance_section(self) -> ReportSection:
        return ReportSection(
            title="Corporate Governance",
            summary=(
                "No structured governance dataset was provided by the current ingestion source. "
                "Source tracking, uploaded-file audit fields, and data-validation status are captured in the database."
            ),
            bullets=[
                "Governance checklist items are marked partial unless governance data is ingested.",
            ],
        )

    def _risk_section(self, forensic_report, risk_metrics: RiskMetrics | None) -> ReportSection:
        bullets = []

        if forensic_report is not None:
            bullets.append(
                f"Composite fraud probability: {self._text(forensic_report.fraud_probability, 1)}%"
            )

        if risk_metrics is not None:
            bullets.extend(
                [
                    f"Price observations: {risk_metrics.observation_count}",
                    f"Annualized volatility: {self._text(risk_metrics.annualized_volatility, 2)}",
                    f"Maximum drawdown: {self._text(risk_metrics.max_drawdown, 2)}",
                    f"Historical 95% VaR: {self._text(risk_metrics.var_95, 2)}",
                    f"Beta: {self._text(risk_metrics.beta, 2)}",
                ]
            )

        if not bullets:
            bullets.append("Risk analysis unavailable because forensic and price inputs are missing.")

        return ReportSection(
            title="Risk Analysis",
            summary="Forensic risk and market-risk metrics.",
            bullets=bullets,
        )

    def _decision_section(self, decision: InvestmentDecision) -> ReportSection:
        return ReportSection(
            title="Investment Decision",
            summary=f"Recommendation: {decision.recommendation.upper()}",
            bullets=decision.rationale,
        )

    def _executive_summary(
        self,
        company: NormalizedCompany,
        latest_snapshot,
        valuation_report,
        forensic_report,
        scenario_report,
        technical_report,
        decision: InvestmentDecision,
    ) -> list[str]:
        summary = [
            f"{company.company.name} ({company.company.ticker}) — sector: {company.company.sector or 'N/A'}.",
        ]

        if latest_snapshot is not None:
            revenue = latest_snapshot.get("revenue")
            net_profit = latest_snapshot.get("net_profit")

            if revenue is not None:
                summary.append(f"Latest revenue: {self._text(revenue, 2)}.")

            if net_profit is not None:
                summary.append(f"Latest net profit: {self._text(net_profit, 2)}.")

        if valuation_report is not None and valuation_report.intrinsic_value is not None:
            summary.append(
                f"Valuation intrinsic value/share: {self._text(valuation_report.intrinsic_value, 2)} "
                f"with signal '{valuation_report.valuation_signal}'."
            )

        if forensic_report is not None and forensic_report.fraud_probability is not None:
            summary.append(f"Forensic fraud probability: {self._text(forensic_report.fraud_probability, 1)}%.")

        if scenario_report is not None and scenario_report.base_target_price is not None:
            summary.append(f"Scenario base target price: {self._text(scenario_report.base_target_price, 2)}.")

        if technical_report is not None:
            summary.append(f"Technical trend: {technical_report.trend}.")

        summary.append(f"Investment decision: {decision.recommendation.upper()}.")

        return summary

    def _section_status(
        self,
        company: NormalizedCompany,
        statement_presence: dict[str, bool],
        ratio_set,
        forensic_report,
        industry_report,
        technical_report,
        valuation_report,
        scenario_report,
        dividend_present: bool,
        shareholding_present: bool,
        risk_metrics,
        decision: InvestmentDecision,
    ) -> dict[str, str]:
        return {
            "A": "covered",
            "B": "covered" if industry_report is not None and industry_report.peers else "partial",
            "C": "partial" if scenario_report is not None else "not_covered",
            "D": "covered" if statement_presence.get("balance_sheet") else "not_covered",
            "E": "covered" if statement_presence.get("pnl") else "not_covered",
            "F": "covered" if statement_presence.get("cashflow") else "not_covered",
            "G": "covered" if ratio_set is not None else "not_covered",
            "H": "covered" if scenario_report is not None and scenario_report.base_growth is not None else "partial",
            "I": "covered" if technical_report is not None else "not_covered",
            "J": "covered" if valuation_report is not None else "not_covered",
            "K": "covered" if dividend_present else "not_covered",
            "L": "covered" if shareholding_present else "not_covered",
            "M": "partial",
            "N": "covered" if forensic_report is not None and risk_metrics is not None else "partial",
            "O": "partial" if risk_metrics is not None else "not_covered",
            "P": "covered" if industry_report is not None and scenario_report is not None else "partial",
            "Q": "covered" if scenario_report is not None else "not_covered",
            "R": "covered" if decision.recommendation != "unavailable" else "not_covered",
        }

    @staticmethod
    def _safe(function, assumptions: list[str], message: str):
        try:
            return function()
        except Exception as exc:
            assumptions.append(f"{message} Error: {exc}")
            return None

    @staticmethod
    def _text(value: Optional[float], digits: int = 4) -> str:
        return "N/A" if value is None else f"{value:.{digits}f}"
