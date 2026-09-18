from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..models import NormalizedCompany
from ..models.forensic import (
    AltmanResult,
    BenfordResult,
    BeneishResult,
    ForensicReport,
    PiotroskiResult,
    RedFlag,
)
from .financial_extractor import FinancialExtractor, FinancialSnapshot, normalize_token

DEFAULT_WEIGHTS = {
    "altman": 0.30,
    "beneish": 0.30,
    "piotroski": 0.20,
    "benford": 0.20,
}


@dataclass(frozen=True)
class ForensicConfig:
    """Tunable forensic thresholds."""

    altman_safe: float = 2.99
    altman_grey: float = 1.81
    beneish_threshold: float = -1.78
    benford_critical: float = 15.507
    benford_min_obs: int = 10
    piotroski_weak: int = 3
    piotroski_moderate: int = 5
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @classmethod
    def from_dict(cls, data: dict | None) -> ForensicConfig:
        base = cls()

        if not isinstance(data, dict):
            return base

        try:
            altman_safe = float(data.get("altman_safe", base.altman_safe))
            altman_grey = float(data.get("altman_grey", base.altman_grey))
            beneish_threshold = float(data.get("beneish_threshold", base.beneish_threshold))
            benford_critical = float(data.get("benford_critical", base.benford_critical))
            benford_min_obs = int(data.get("benford_min_obs", base.benford_min_obs))
            piotroski_weak = int(data.get("piotroski_weak", base.piotroski_weak))
            piotroski_moderate = int(data.get("piotroski_moderate", base.piotroski_moderate))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid forensic configuration value") from exc

        weights = dict(base.weights)
        raw_weights = data.get("weights", {})
        if isinstance(raw_weights, dict):
            for key, value in raw_weights.items():
                if key in weights:
                    try:
                        parsed = float(value)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(parsed) and parsed >= 0:
                        weights[key] = parsed

        return cls(
            altman_safe=altman_safe,
            altman_grey=altman_grey,
            beneish_threshold=beneish_threshold,
            benford_critical=benford_critical,
            benford_min_obs=benford_min_obs,
            piotroski_weak=piotroski_weak,
            piotroski_moderate=piotroski_moderate,
            weights=weights,
        )


def _safe_div(
    numerator: Optional[float],
    denominator: Optional[float],
    require_positive_den: bool = True,
) -> Optional[float]:
    if numerator is None or denominator is None:
        return None

    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None

    if math.isclose(denominator, 0.0, abs_tol=1e-12):
        return None

    if require_positive_den and denominator <= 0:
        return None

    return numerator / denominator


def _ratio_of_values(
    numerator: Optional[float],
    denominator: Optional[float],
    require_positive_den: bool = False,
) -> Optional[float]:
    return _safe_div(numerator, denominator, require_positive_den=require_positive_den)


def _ratio_of_ratios(
    current_numerator: Optional[float],
    current_denominator: Optional[float],
    prior_numerator: Optional[float],
    prior_denominator: Optional[float],
) -> Optional[float]:
    current = _safe_div(current_numerator, current_denominator, require_positive_den=False)
    prior = _safe_div(prior_numerator, prior_denominator, require_positive_den=False)

    if current is None or prior is None:
        return None

    if math.isclose(prior, 0.0, abs_tol=1e-12):
        if math.isclose(current, 0.0, abs_tol=1e-12):
            return 1.0
        return None

    return current / prior


def _first_digit(value: float) -> Optional[int]:
    if not math.isfinite(value):
        return None

    magnitude = abs(value)
    if math.isclose(magnitude, 0.0, abs_tol=1e-12):
        return None

    while magnitude >= 10:
        magnitude /= 10

    while magnitude < 1:
        magnitude *= 10

    digit = int(magnitude)

    if 1 <= digit <= 9:
        return digit

    return None


class ForensicExtractor:
    """Extends M2 extraction with forensic-specific canonical fields."""

    def __init__(self, company: NormalizedCompany) -> None:
        self._company = company
        self._base = FinancialExtractor(company)

    def fiscal_years(self) -> list[int]:
        return self._base.fiscal_years()

    def latest_fiscal_year(self) -> Optional[int]:
        return self._base.latest_fiscal_year()

    def latest_close(self) -> Optional[float]:
        return self._base.latest_close()

    def prior_year(self, fiscal_year: int) -> Optional[int]:
        earlier = [year for year in self.fiscal_years() if year < fiscal_year]
        return earlier[-1] if earlier else None

    def snapshot(self, fiscal_year: int) -> FinancialSnapshot:
        base_snapshot = self._base.snapshot(fiscal_year)
        values = dict(base_snapshot.values)

        retained = self._retained_earnings(fiscal_year)
        if retained is not None:
            values["retained_earnings"] = retained

        return FinancialSnapshot(fiscal_year=fiscal_year, values=values)

    def _retained_earnings(self, fiscal_year: int) -> Optional[float]:
        lines = sorted(self._company.financials, key=lambda line: (line.statement_type, line.line_item))

        for line in lines:
            if line.fiscal_year != fiscal_year:
                continue

            token = normalize_token(line.line_item)
            if "retained" in token:
                return line.value

        return None


class ForensicAnalyzer:
    """Computes Altman Z, Beneish M, Piotroski F, Benford, and composite fraud risk."""

    def __init__(self, config: ForensicConfig | None = None) -> None:
        self.config = config or ForensicConfig()

    def analyze(
        self,
        company: NormalizedCompany,
        fiscal_year: int | None = None,
    ) -> ForensicReport:
        extractor = ForensicExtractor(company)

        if fiscal_year is None:
            fiscal_year = extractor.latest_fiscal_year()

        if fiscal_year is None:
            raise ValueError("No fiscal years available for forensic analysis")

        current = extractor.snapshot(fiscal_year)
        prior_year = extractor.prior_year(fiscal_year)
        prior = extractor.snapshot(prior_year) if prior_year is not None else None

        market_cap = self._market_cap(extractor, fiscal_year, current)

        altman = self.calculate_altman(current, market_cap)
        beneish = self.calculate_beneish(current, prior)
        piotroski = self.calculate_piotroski(current, prior)
        benford = self.calculate_benford(self._benford_values(company, fiscal_year))

        fraud_probability = self._composite_probability(altman, beneish, piotroski, benford)
        red_flags = self._red_flags(current, prior, altman, beneish, piotroski, benford, prior is None)

        available = [
            altman.z_score is not None,
            beneish.m_score is not None,
            piotroski.score is not None,
            benford.chi_square is not None,
        ]

        if not any(available):
            status = "unavailable"
        elif not all(available):
            status = "partial"
        else:
            status = "ok"

        return ForensicReport(
            fiscal_year=fiscal_year,
            altman=altman,
            beneish=beneish,
            piotroski=piotroski,
            benford=benford,
            fraud_probability=fraud_probability,
            red_flags=red_flags,
            status=status,
        )

    def calculate_altman(
        self,
        snapshot: FinancialSnapshot,
        market_cap: Optional[float],
    ) -> AltmanResult:
        formula = "1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5"

        current_assets = snapshot.get("current_assets")
        current_liabilities = snapshot.get("current_liabilities")
        total_assets = snapshot.get("total_assets")
        retained_earnings = snapshot.get("retained_earnings")
        ebit = snapshot.get("ebit")
        total_liabilities = snapshot.get("total_liabilities")
        revenue = snapshot.get("revenue")

        working_capital = None
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities

        equity_value = market_cap if market_cap is not None else snapshot.get("total_equity")

        x1 = _safe_div(working_capital, total_assets)
        x2 = _safe_div(retained_earnings, total_assets)
        x3 = _safe_div(ebit, total_assets)
        x4 = _safe_div(equity_value, total_liabilities)
        x5 = _safe_div(revenue, total_assets)

        inputs = {
            "working_capital": working_capital,
            "total_assets": total_assets,
            "retained_earnings": retained_earnings,
            "ebit": ebit,
            "equity_value": equity_value,
            "total_liabilities": total_liabilities,
            "revenue": revenue,
            "x1": x1,
            "x2": x2,
            "x3": x3,
            "x4": x4,
            "x5": x5,
        }

        if None in (x1, x2, x3, x4, x5):
            return AltmanResult(
                z_score=None,
                zone="not_available",
                inputs=inputs,
                formula=formula,
                interpretation="Altman Z-Score unavailable because required inputs are missing.",
            )

        z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

        if z_score < self.config.altman_grey:
            zone = "distress"
            interpretation = f"Altman Z-Score {z_score:.4f} is below {self.config.altman_grey:.2f}, indicating distress risk."
        elif z_score <= self.config.altman_safe:
            zone = "grey"
            interpretation = f"Altman Z-Score {z_score:.4f} is in the grey zone between {self.config.altman_grey:.2f} and {self.config.altman_safe:.2f}."
        else:
            zone = "safe"
            interpretation = f"Altman Z-Score {z_score:.4f} is above {self.config.altman_safe:.2f}, indicating a safe zone."

        return AltmanResult(
            z_score=z_score,
            zone=zone,
            inputs=inputs,
            formula=formula,
            interpretation=interpretation,
        )

    def calculate_beneish(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> BeneishResult:
        formula = (
            "-4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + "
            "0.115*DEPI + 0.172*SGAI + 4.679*TATA - 0.327*LVGI"
        )

        if prior is None:
            return BeneishResult(
                m_score=None,
                variables={},
                likely_manipulator=None,
                formula=formula,
                interpretation="Beneish M-Score unavailable because prior-year data is missing.",
            )

        dsri = _ratio_of_ratios(
            current.get("receivables"),
            current.get("revenue"),
            prior.get("receivables"),
            prior.get("revenue"),
        )

        current_gm = _safe_div(current.get("gross_profit"), current.get("revenue"))
        prior_gm = _safe_div(prior.get("gross_profit"), prior.get("revenue"))
        gmi = _ratio_of_values(prior_gm, current_gm)

        current_aqi = self._aqi(current)
        prior_aqi = self._aqi(prior)
        aqi = _ratio_of_values(current_aqi, prior_aqi)

        sgi = _ratio_of_values(current.get("revenue"), prior.get("revenue"))

        current_depi = self._depi_rate(current)
        prior_depi = self._depi_rate(prior)
        depi = _ratio_of_values(prior_depi, current_depi)

        sgai = _ratio_of_ratios(
            current.get("operating_expenses"),
            current.get("revenue"),
            prior.get("operating_expenses"),
            prior.get("revenue"),
        )

        net_profit = current.get("net_profit")
        operating_cash_flow = current.get("operating_cash_flow")
        tata_numerator = None
        if net_profit is not None and operating_cash_flow is not None:
            tata_numerator = net_profit - operating_cash_flow

        tata = _safe_div(tata_numerator, current.get("total_assets"))

        lvgi = _ratio_of_ratios(
            current.get("total_liabilities"),
            current.get("total_assets"),
            prior.get("total_liabilities"),
            prior.get("total_assets"),
        )

        variables = {
            "DSRI": dsri,
            "GMI": gmi,
            "AQI": aqi,
            "SGI": sgi,
            "DEPI": depi,
            "SGAI": sgai,
            "TATA": tata,
            "LVGI": lvgi,
        }

        if any(value is None for value in variables.values()):
            return BeneishResult(
                m_score=None,
                variables=variables,
                likely_manipulator=None,
                formula=formula,
                interpretation="Beneish M-Score unavailable because one or more required variables are missing.",
            )

        m_score = (
            -4.84
            + 0.920 * variables["DSRI"]
            + 0.528 * variables["GMI"]
            + 0.404 * variables["AQI"]
            + 0.892 * variables["SGI"]
            + 0.115 * variables["DEPI"]
            + 0.172 * variables["SGAI"]
            + 4.679 * variables["TATA"]
            - 0.327 * variables["LVGI"]
        )

        likely = m_score > self.config.beneish_threshold

        if likely:
            interpretation = (
                f"Beneish M-Score {m_score:.4f} is above {self.config.beneish_threshold:.2f}, "
                "indicating earnings-manipulation risk."
            )
        else:
            interpretation = (
                f"Beneish M-Score {m_score:.4f} is below {self.config.beneish_threshold:.2f}, "
                "indicating no manipulation signal."
            )

        return BeneishResult(
            m_score=m_score,
            variables=variables,
            likely_manipulator=likely,
            formula=formula,
            interpretation=interpretation,
        )

    def calculate_piotroski(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> PiotroskiResult:
        formula = "Sum of 9 binary fundamental strength signals"

        signals = {
            "positive_roa": self._positive_roa(current),
            "positive_operating_cash_flow": self._positive_cfo(current),
            "roa_improvement": self._roa_improvement(current, prior),
            "positive_accruals": self._positive_accruals(current),
            "leverage_decrease": self._leverage_decrease(current, prior),
            "liquidity_improvement": self._liquidity_improvement(current, prior),
            "no_share_dilution": self._no_share_dilution(current, prior),
            "gross_margin_improvement": self._gross_margin_improvement(current, prior),
            "asset_turnover_improvement": self._asset_turnover_improvement(current, prior),
        }

        score = sum(1 for value in signals.values() if value)

        if prior is None:
            interpretation = (
                f"Piotroski F-Score is {score}/9. Prior-year data is unavailable, "
                "so change-based signals are scored zero."
            )
        else:
            interpretation = f"Piotroski F-Score is {score}/9."

        return PiotroskiResult(
            score=score,
            signals=signals,
            formula=formula,
            interpretation=interpretation,
        )

    def calculate_benford(self, values: list[float]) -> BenfordResult:
        formula = "Chi-square test of first-digit distribution against Benford's Law"
        cleaned: list[float] = []

        for value in values:
            if value is None or not math.isfinite(value):
                continue
            if math.isclose(value, 0.0, abs_tol=1e-12):
                continue
            cleaned.append(abs(value))

        observation_count = len(cleaned)

        if observation_count < self.config.benford_min_obs:
            return BenfordResult(
                observation_count=observation_count,
                chi_square=None,
                critical_value=self.config.benford_critical,
                suspicious=None,
                distribution={},
                formula=formula,
                interpretation=(
                    f"Benford analysis unavailable because only {observation_count} observations "
                    f"were found and at least {self.config.benford_min_obs} are required."
                ),
            )

        counts = {digit: 0 for digit in range(1, 10)}

        for value in cleaned:
            digit = _first_digit(value)
            if digit is not None:
                counts[digit] += 1

        expected = {
            digit: observation_count * math.log10(1 + 1 / digit)
            for digit in range(1, 10)
        }

        chi_square = 0.0
        for digit in range(1, 10):
            observed = float(counts[digit])
            exp = expected[digit]
            chi_square += ((observed - exp) ** 2) / exp

        suspicious = chi_square > self.config.benford_critical
        distribution = {digit: counts[digit] / observation_count for digit in range(1, 10)}

        if suspicious:
            interpretation = (
                f"Benford chi-square {chi_square:.4f} exceeds critical value "
                f"{self.config.benford_critical:.4f}, indicating suspicious digit distribution."
            )
        else:
            interpretation = (
                f"Benford chi-square {chi_square:.4f} is below critical value "
                f"{self.config.benford_critical:.4f}, indicating no digit-distribution red flag."
            )

        return BenfordResult(
            observation_count=observation_count,
            chi_square=chi_square,
            critical_value=self.config.benford_critical,
            suspicious=suspicious,
            distribution=distribution,
            formula=formula,
            interpretation=interpretation,
        )

    def _market_cap(
        self,
        extractor: ForensicExtractor,
        fiscal_year: int,
        snapshot: FinancialSnapshot,
    ) -> Optional[float]:
        if fiscal_year != extractor.latest_fiscal_year():
            return None

        close = extractor.latest_close()
        shares = snapshot.get("shares_outstanding")

        if close is None or shares is None:
            return None

        return close * shares

    def _benford_values(self, company: NormalizedCompany, fiscal_year: int) -> list[float]:
        values = [
            line.value
            for line in company.financials
            if line.fiscal_year == fiscal_year and line.value is not None
        ]

        if len(values) < self.config.benford_min_obs:
            values = [line.value for line in company.financials if line.value is not None]

        return values

    def _aqi(self, snapshot: FinancialSnapshot) -> Optional[float]:
        total_assets = snapshot.get("total_assets")
        if total_assets is None or math.isclose(total_assets, 0.0, abs_tol=1e-12):
            return None

        fixed_assets = snapshot.get("fixed_assets") or 0.0
        current_assets = snapshot.get("current_assets") or 0.0
        short_term_investments = snapshot.get("short_term_investments") or 0.0

        excluded = fixed_assets + current_assets + short_term_investments
        return 1 - (excluded / total_assets)

    def _depi_rate(self, snapshot: FinancialSnapshot) -> Optional[float]:
        depreciation = snapshot.get("depreciation_amortization")
        fixed_assets = snapshot.get("fixed_assets")

        if depreciation is None or fixed_assets is None:
            return None

        denominator = depreciation + fixed_assets
        if denominator <= 0:
            return None

        return depreciation / denominator

    def _positive_roa(self, snapshot: FinancialSnapshot) -> bool:
        roa = _safe_div(snapshot.get("net_profit"), snapshot.get("total_assets"))
        return roa is not None and roa > 0

    def _positive_cfo(self, snapshot: FinancialSnapshot) -> bool:
        cfo = snapshot.get("operating_cash_flow")
        return cfo is not None and cfo > 0

    def _roa_improvement(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_roa = _safe_div(current.get("net_profit"), current.get("total_assets"))
        prior_roa = _safe_div(prior.get("net_profit"), prior.get("total_assets"))

        return current_roa is not None and prior_roa is not None and current_roa > prior_roa

    def _positive_accruals(self, snapshot: FinancialSnapshot) -> bool:
        cfo = snapshot.get("operating_cash_flow")
        net_profit = snapshot.get("net_profit")
        return cfo is not None and net_profit is not None and cfo > net_profit

    def _leverage(self, snapshot: FinancialSnapshot) -> Optional[float]:
        debt = snapshot.get("long_term_debt")
        if debt is None:
            debt = snapshot.get("total_debt")

        return _safe_div(debt, snapshot.get("total_assets"))

    def _leverage_decrease(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_leverage = self._leverage(current)
        prior_leverage = self._leverage(prior)

        return (
            current_leverage is not None
            and prior_leverage is not None
            and current_leverage <= prior_leverage
        )

    def _liquidity_improvement(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_ratio = _safe_div(current.get("current_assets"), current.get("current_liabilities"))
        prior_ratio = _safe_div(prior.get("current_assets"), prior.get("current_liabilities"))

        return (
            current_ratio is not None
            and prior_ratio is not None
            and current_ratio > prior_ratio
        )

    def _no_share_dilution(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_shares = current.get("shares_outstanding")
        prior_shares = prior.get("shares_outstanding")

        return (
            current_shares is not None
            and prior_shares is not None
            and current_shares <= prior_shares
        )

    def _gross_margin_improvement(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_gm = _safe_div(current.get("gross_profit"), current.get("revenue"))
        prior_gm = _safe_div(prior.get("gross_profit"), prior.get("revenue"))

        return current_gm is not None and prior_gm is not None and current_gm > prior_gm

    def _asset_turnover_improvement(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
    ) -> bool:
        if prior is None:
            return False

        current_turnover = _safe_div(current.get("revenue"), current.get("total_assets"))
        prior_turnover = _safe_div(prior.get("revenue"), prior.get("total_assets"))

        return (
            current_turnover is not None
            and prior_turnover is not None
            and current_turnover > prior_turnover
        )

    def _composite_probability(
        self,
        altman: AltmanResult,
        beneish: BeneishResult,
        piotroski: PiotroskiResult,
        benford: BenfordResult,
    ) -> Optional[float]:
        risks: dict[str, Optional[float]] = {}

        if altman.zone == "distress":
            risks["altman"] = 1.0
        elif altman.zone == "grey":
            risks["altman"] = 0.5
        elif altman.zone == "safe":
            risks["altman"] = 0.0
        else:
            risks["altman"] = None

        if beneish.likely_manipulator is None:
            risks["beneish"] = None
        elif beneish.likely_manipulator:
            risks["beneish"] = 1.0
        else:
            risks["beneish"] = 0.0

        if piotroski.score is None:
            risks["piotroski"] = None
        elif piotroski.score <= self.config.piotroski_weak:
            risks["piotroski"] = 1.0
        elif piotroski.score <= self.config.piotroski_moderate:
            risks["piotroski"] = 0.5
        else:
            risks["piotroski"] = 0.0

        if benford.chi_square is None:
            risks["benford"] = None
        elif benford.chi_square > self.config.benford_critical:
            risks["benford"] = 1.0
        else:
            risks["benford"] = 0.0

        available = {
            key: (risk, self.config.weights.get(key, 0.0))
            for key, risk in risks.items()
            if risk is not None and self.config.weights.get(key, 0.0) > 0
        }

        if not available:
            return None

        total_weight = sum(weight for _, weight in available.values())
        if math.isclose(total_weight, 0.0, abs_tol=1e-12):
            return None

        weighted_risk = sum(risk * weight for risk, weight in available.values())
        probability = 100.0 * weighted_risk / total_weight

        return max(0.0, min(100.0, probability))

    def _red_flags(
        self,
        current: FinancialSnapshot,
        prior: Optional[FinancialSnapshot],
        altman: AltmanResult,
        beneish: BeneishResult,
        piotroski: PiotroskiResult,
        benford: BenfordResult,
        prior_missing: bool,
    ) -> list[RedFlag]:
        flags: list[RedFlag] = []

        if altman.zone == "distress":
            flags.append(
                RedFlag(
                    code="ALTMAN_DISTRESS",
                    severity="high",
                    message="Altman Z-Score is in the distress zone.",
                )
            )
        elif altman.zone == "grey":
            flags.append(
                RedFlag(
                    code="ALTMAN_GREY",
                    severity="warning",
                    message="Altman Z-Score is in the grey zone.",
                )
            )

        if beneish.likely_manipulator is True:
            flags.append(
                RedFlag(
                    code="BENEISH_MANIPULATION",
                    severity="high",
                    message="Beneish M-Score indicates earnings-manipulation risk.",
                )
            )

        if piotroski.score is not None and piotroski.score <= self.config.piotroski_weak:
            flags.append(
                RedFlag(
                    code="PIOTROVSKI_WEAK",
                    severity="high",
                    message=f"Piotroski F-Score is weak at {piotroski.score}/9.",
                )
            )
        elif piotroski.score is not None and piotroski.score <= self.config.piotroski_moderate:
            flags.append(
                RedFlag(
                    code="PIOTROVSKI_MODERATE",
                    severity="warning",
                    message=f"Piotroski F-Score is moderate at {piotroski.score}/9.",
                )
            )

        if benford.suspicious is True:
            flags.append(
                RedFlag(
                    code="BENFORD_SUSPICIOUS",
                    severity="high",
                    message="Benford's Law chi-square indicates suspicious digit distribution.",
                )
            )

        net_profit = current.get("net_profit")
        if net_profit is not None and net_profit < 0:
            flags.append(
                RedFlag(
                    code="NEGATIVE_NET_PROFIT",
                    severity="warning",
                    message="Net profit is negative.",
                )
            )

        cfo = current.get("operating_cash_flow")
        if cfo is not None and cfo < 0:
            if net_profit is not None and net_profit > 0:
                flags.append(
                    RedFlag(
                        code="NEGATIVE_OPERATING_CASH_FLOW",
                        severity="high",
                        message="Operating cash flow is negative while net profit is positive.",
                    )
                )
            else:
                flags.append(
                    RedFlag(
                        code="NEGATIVE_OPERATING_CASH_FLOW",
                        severity="warning",
                        message="Operating cash flow is negative.",
                    )
                )

        total_equity = current.get("total_equity")
        total_liabilities = current.get("total_liabilities")

        if total_equity is not None and total_equity <= 0:
            flags.append(
                RedFlag(
                    code="NEGATIVE_EQUITY",
                    severity="high",
                    message="Shareholders' equity is zero or negative.",
                )
            )
        else:
            leverage = _safe_div(total_liabilities, total_equity)
            if leverage is not None:
                if leverage > 5:
                    flags.append(
                        RedFlag(
                            code="HIGH_LEVERAGE",
                            severity="high",
                            message="Liabilities-to-equity leverage is very high.",
                        )
                    )
                elif leverage > 2:
                    flags.append(
                        RedFlag(
                            code="HIGH_LEVERAGE",
                            severity="warning",
                            message="Liabilities-to-equity leverage is elevated.",
                        )
                    )

        if prior is not None:
            current_gm = _safe_div(current.get("gross_profit"), current.get("revenue"))
            prior_gm = _safe_div(prior.get("gross_profit"), prior.get("revenue"))

            if current_gm is not None and prior_gm is not None and current_gm < prior_gm:
                flags.append(
                    RedFlag(
                        code="DECLINING_GROSS_MARGIN",
                        severity="warning",
                        message="Gross margin declined versus the prior year.",
                    )
                )

            current_receivables = current.get("receivables")
            prior_receivables = prior.get("receivables")
            current_revenue = current.get("revenue")
            prior_revenue = prior.get("revenue")

            if all(
                value is not None
                for value in (current_receivables, prior_receivables, current_revenue, prior_revenue)
            ):
                if not math.isclose(prior_receivables, 0.0, abs_tol=1e-12) and not math.isclose(
                    prior_revenue,
                    0.0,
                    abs_tol=1e-12,
                ):
                    receivables_growth = (current_receivables - prior_receivables) / abs(prior_receivables)
                    revenue_growth = (current_revenue - prior_revenue) / abs(prior_revenue)

                    if receivables_growth > revenue_growth:
                        flags.append(
                            RedFlag(
                                code="RECEIVABLES_GROWTH",
                                severity="warning",
                                message="Receivables grew faster than revenue.",
                            )
                        )

        if prior_missing:
            flags.append(
                RedFlag(
                    code="PRIOR_YEAR_MISSING",
                    severity="info",
                    message="Prior-year data is unavailable for trend-based forensic tests.",
                )
            )

        return flags
