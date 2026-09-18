from __future__ import annotations

import math
from typing import Optional

from ..models import NormalizedCompany
from ..models.industry import (
    CompetitivePosition,
    IndustryReport,
    PeerCompany,
    PercentileRanking,
    PorterFiveForcesResult,
    PorterForceScore,
)
from .financial_extractor import FinancialExtractor
from .ratios import RatioCalculator

LOWER_IS_BETTER = {
    "debt_to_equity",
    "debt_to_assets",
    "equity_multiplier",
    "long_term_debt_to_equity",
    "pe_ratio",
    "pb_ratio",
}


def calculate_percentile(value: Optional[float], values: list[float]) -> Optional[float]:
    """Midpoint percentile rank."""
    if value is None or not values:
        return None

    if not math.isfinite(value):
        return None

    cleaned = [item for item in values if item is not None and math.isfinite(item)]
    if not cleaned:
        return None

    sorted_values = sorted(cleaned)
    less_than = sum(1 for item in sorted_values if item < value)
    equal_to = sum(1 for item in sorted_values if item == value)

    return 100.0 * (less_than + 0.5 * equal_to) / len(sorted_values)


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None:
        return None

    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None

    if denominator <= 0:
        return None

    return numerator / denominator


def _mean(values: list[float]) -> Optional[float]:
    cleaned = [value for value in values if value is not None and math.isfinite(value)]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _median(values: list[float]) -> Optional[float]:
    cleaned = sorted(value for value in values if value is not None and math.isfinite(value))
    if not cleaned:
        return None

    mid = len(cleaned) // 2
    if len(cleaned) % 2 == 1:
        return cleaned[mid]

    return (cleaned[mid - 1] + cleaned[mid]) / 2


def _score_higher(value: Optional[float], t5: float, t4: float, t3: float, t2: float) -> int:
    if value is None:
        return 3
    if value >= t5:
        return 5
    if value >= t4:
        return 4
    if value >= t3:
        return 3
    if value >= t2:
        return 2
    return 1


def _score_lower(value: Optional[float], t5: float, t4: float, t3: float, t2: float) -> int:
    if value is None:
        return 3
    if value <= t5:
        return 5
    if value <= t4:
        return 4
    if value <= t3:
        return 3
    if value <= t2:
        return 2
    return 1


class IndustryAnalyzer:
    """Peer selection, percentile comparison, Porter's Five Forces, and positioning."""

    def __init__(
        self,
        ratio_calculator: RatioCalculator | None = None,
        max_peers: int = 5,
    ) -> None:
        self._ratio_calculator = ratio_calculator or RatioCalculator()
        self.max_peers = max_peers

    def analyze(
        self,
        target: NormalizedCompany,
        candidates: list[NormalizedCompany],
    ) -> IndustryReport:
        peers = self.select_peers(target, candidates)

        peer_map = {candidate.company.ticker: candidate for candidate in candidates}
        selected_candidates = [peer_map[peer.ticker] for peer in peers if peer.ticker in peer_map]

        target_ratio_set = self._safe_ratio_set(target)
        target_fiscal_year = target_ratio_set.fiscal_year if target_ratio_set else None
        target_ratios = (
            {ratio.name: ratio.value for ratio in target_ratio_set.ratios}
            if target_ratio_set
            else {}
        )

        peer_metrics: dict[str, dict[str, Optional[float]]] = {}
        peer_metrics[target.company.ticker] = target_ratios

        for candidate in selected_candidates:
            ratio_set = self._safe_ratio_set(candidate)
            peer_metrics[candidate.company.ticker] = (
                {ratio.name: ratio.value for ratio in ratio_set.ratios}
                if ratio_set
                else {}
            )

        rankings = self._rankings(target_ratios, peer_metrics)
        porter = self._porter(target, selected_candidates)
        position = self._position(rankings)

        if not target_ratios:
            status = "unavailable"
        elif not peers:
            status = "partial"
        else:
            status = "ok"

        return IndustryReport(
            target_ticker=target.company.ticker,
            fiscal_year=target_fiscal_year,
            peers=peers,
            peer_metrics=peer_metrics,
            rankings=rankings,
            porter=porter,
            position=position,
            status=status,
        )

    def select_peers(
        self,
        target: NormalizedCompany,
        candidates: list[NormalizedCompany],
        max_peers: int | None = None,
    ) -> list[PeerCompany]:
        limit = max_peers if max_peers is not None else self.max_peers
        target_size = self._size_metric(target)

        selected: list[PeerCompany] = []

        for candidate in candidates:
            if candidate.company.ticker == target.company.ticker:
                continue

            if not self._sector_match(target, candidate):
                continue

            candidate_size = self._size_metric(candidate)
            similarity = self._similarity_score(target, target_size, candidate, candidate_size)

            if similarity <= 0:
                continue

            selected.append(
                PeerCompany(
                    ticker=candidate.company.ticker,
                    name=candidate.company.name,
                    sector=candidate.company.sector,
                    industry=candidate.company.industry,
                    size_metric=candidate_size,
                    similarity_score=similarity,
                )
            )

        selected.sort(key=lambda peer: peer.similarity_score, reverse=True)
        return selected[:limit]

    def _sector_match(
        self,
        target: NormalizedCompany,
        candidate: NormalizedCompany,
    ) -> bool:
        target_sector = (target.company.sector or "").strip().lower()
        candidate_sector = (candidate.company.sector or "").strip().lower()

        if target_sector:
            return target_sector == candidate_sector

        target_industry = (target.company.industry or "").strip().lower()
        candidate_industry = (candidate.company.industry or "").strip().lower()

        if target_industry:
            return target_industry == candidate_industry

        return True

    def _similarity_score(
        self,
        target: NormalizedCompany,
        target_size: Optional[float],
        candidate: NormalizedCompany,
        candidate_size: Optional[float],
    ) -> float:
        score = 0.0

        target_sector = (target.company.sector or "").strip().lower()
        candidate_sector = (candidate.company.sector or "").strip().lower()
        target_industry = (target.company.industry or "").strip().lower()
        candidate_industry = (candidate.company.industry or "").strip().lower()

        if target_sector and candidate_sector and target_sector == candidate_sector:
            score += 3.0
        elif target_industry and candidate_industry and target_industry == candidate_industry:
            score += 3.0

        if target_industry and candidate_industry and target_industry == candidate_industry:
            score += 1.0

        if (
            target_size is not None
            and candidate_size is not None
            and target_size > 0
            and candidate_size > 0
        ):
            size_ratio = min(target_size / candidate_size, candidate_size / target_size)
            score += 3.0 * size_ratio

        return score

    def _size_metric(self, company: NormalizedCompany) -> Optional[float]:
        extractor = FinancialExtractor(company)
        fiscal_year = extractor.latest_fiscal_year()

        if fiscal_year is None:
            return None

        snapshot = extractor.snapshot(fiscal_year)

        close = extractor.latest_close()
        shares = snapshot.get("shares_outstanding")

        if close is not None and shares is not None and shares > 0:
            return close * shares

        revenue = snapshot.get("revenue")
        if revenue is not None:
            return revenue

        return snapshot.get("total_assets")

    def _safe_ratio_set(self, company: NormalizedCompany):
        try:
            return self._ratio_calculator.calculate_all(company)
        except ValueError:
            return None

    def _rankings(
        self,
        target_ratios: dict[str, Optional[float]],
        peer_metrics: dict[str, dict[str, Optional[float]]],
    ) -> list[PercentileRanking]:
        rankings: list[PercentileRanking] = []

        for ratio_name, target_value in target_ratios.items():
            if target_value is None or not math.isfinite(target_value):
                continue

            values: list[float] = []
            for metrics in peer_metrics.values():
                value = metrics.get(ratio_name)
                if value is not None and math.isfinite(value):
                    values.append(value)

            if not values:
                continue

            percentile = calculate_percentile(target_value, values)
            higher_is_better = ratio_name not in LOWER_IS_BETTER

            rankings.append(
                PercentileRanking(
                    ratio_name=ratio_name,
                    company_value=target_value,
                    peer_count=len(values),
                    percentile=percentile,
                    peer_min=min(values),
                    peer_median=_median(values),
                    peer_max=max(values),
                    higher_is_better=higher_is_better,
                )
            )

        return rankings

    def _position(self, rankings: list[PercentileRanking]) -> CompetitivePosition:
        adjusted: dict[str, Optional[float]] = {}

        for ranking in rankings:
            if ranking.percentile is None:
                continue

            if ranking.higher_is_better:
                adjusted[ranking.ratio_name] = ranking.percentile
            else:
                adjusted[ranking.ratio_name] = 100.0 - ranking.percentile

        composite_values = [value for value in adjusted.values() if value is not None]
        composite = _mean(composite_values)

        if composite is None:
            classification = "unavailable"
        elif composite >= 75:
            classification = "leader"
        elif composite >= 50:
            classification = "strong"
        elif composite >= 25:
            classification = "average"
        else:
            classification = "laggard"

        return CompetitivePosition(
            composite_score=composite,
            classification=classification,
            adjusted_percentiles=adjusted,
        )

    def _porter(
        self,
        target: NormalizedCompany,
        peers: list[NormalizedCompany],
    ) -> PorterFiveForcesResult:
        extractor = FinancialExtractor(target)
        years = extractor.fiscal_years()

        if not years:
            return PorterFiveForcesResult(
                forces=[],
                overall_score=None,
                interpretation="Porter's Five Forces unavailable because target financial data is missing.",
            )

        current = extractor.snapshot(years[-1])
        prior = extractor.snapshot(years[-2]) if len(years) >= 2 else None

        fixed_assets = current.get("fixed_assets")
        total_assets = current.get("total_assets")
        capital_intensity = _safe_div(fixed_assets, total_assets)

        cogs = current.get("cogs")
        payables = current.get("payables")
        payables_turnover = _safe_div(cogs, payables)

        receivables = current.get("receivables")
        revenue = current.get("revenue")
        receivables_ratio = _safe_div(receivables, revenue)

        gross_profit = current.get("gross_profit")
        gross_margin = _safe_div(gross_profit, revenue)

        operating_profit = current.get("operating_profit")
        operating_margin = _safe_div(operating_profit, revenue)

        revenue_growth = None
        if prior is not None:
            prior_revenue = prior.get("revenue")
            if (
                revenue is not None
                and prior_revenue is not None
                and not math.isclose(prior_revenue, 0.0, abs_tol=1e-12)
            ):
                revenue_growth = (revenue - prior_revenue) / abs(prior_revenue)

        buyer_pressure = None
        if receivables_ratio is not None and gross_margin is not None:
            buyer_pressure = receivables_ratio + max(0.0, 1.0 - gross_margin)

        substitute_metric = None
        if operating_margin is not None:
            substitute_metric = operating_margin + (revenue_growth if revenue_growth is not None else 0.0)

        net_margins: list[float] = []
        for company in [target] + peers:
            company_extractor = FinancialExtractor(company)
            company_years = company_extractor.fiscal_years()

            if not company_years:
                continue

            snapshot = company_extractor.snapshot(company_years[-1])
            margin = _safe_div(snapshot.get("net_profit"), snapshot.get("revenue"))

            if margin is not None:
                net_margins.append(margin)

        avg_net_margin = _mean(net_margins)

        rivalry_pressure = None
        if avg_net_margin is not None:
            rivalry_pressure = min(len(peers) / 5.0, 1.0) + max(0.0, 1.0 - avg_net_margin)

        new_entrants_score = _score_higher(capital_intensity, 0.40, 0.25, 0.10, 0.05)
        supplier_score = _score_lower(payables_turnover, 4.0, 6.0, 9.0, 12.0)
        buyer_score = _score_lower(buyer_pressure, 0.60, 0.80, 1.00, 1.20)
        substitutes_score = _score_higher(substitute_metric, 0.35, 0.25, 0.15, 0.05)
        rivalry_score = _score_lower(rivalry_pressure, 0.50, 0.80, 1.10, 1.40)

        forces = [
            PorterForceScore(
                force="Threat of New Entrants",
                score=new_entrants_score,
                interpretation="Higher score means stronger entry barriers and lower new-entrant threat.",
                inputs={"capital_intensity": capital_intensity},
            ),
            PorterForceScore(
                force="Supplier Power",
                score=supplier_score,
                interpretation="Higher score means lower supplier power.",
                inputs={"payables_turnover": payables_turnover},
            ),
            PorterForceScore(
                force="Buyer Power",
                score=buyer_score,
                interpretation="Higher score means lower buyer power.",
                inputs={
                    "receivables_to_revenue": receivables_ratio,
                    "gross_margin": gross_margin,
                    "buyer_pressure": buyer_pressure,
                },
            ),
            PorterForceScore(
                force="Threat of Substitutes",
                score=substitutes_score,
                interpretation="Higher score means lower substitution threat.",
                inputs={
                    "operating_margin": operating_margin,
                    "revenue_growth": revenue_growth,
                    "substitute_metric": substitute_metric,
                },
            ),
            PorterForceScore(
                force="Competitive Rivalry",
                score=rivalry_score,
                interpretation="Higher score means lower rivalry pressure.",
                inputs={
                    "peer_count": float(len(peers)),
                    "average_net_margin": avg_net_margin,
                    "rivalry_pressure": rivalry_pressure,
                },
            ),
        ]

        overall = _mean([force.score for force in forces])

        if overall is None:
            interpretation = "Porter's Five Forces unavailable."
        elif overall >= 4.2:
            interpretation = f"Industry structure is highly attractive ({overall:.2f}/5)."
        elif overall >= 3.4:
            interpretation = f"Industry structure is attractive ({overall:.2f}/5)."
        elif overall >= 2.6:
            interpretation = f"Industry structure is neutral ({overall:.2f}/5)."
        elif overall >= 1.8:
            interpretation = f"Industry structure is challenging ({overall:.2f}/5)."
        else:
            interpretation = f"Industry structure is difficult ({overall:.2f}/5)."

        return PorterFiveForcesResult(
            forces=forces,
            overall_score=overall,
            interpretation=interpretation,
        )
