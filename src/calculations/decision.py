from __future__ import annotations

from typing import Any

from ..models.report import InvestmentDecision


class DecisionEngine:
    """Combines valuation, forensic, scenario, technical and fundamental signals."""

    def decide(
        self,
        valuation_report: Any | None = None,
        forensic_report: Any | None = None,
        scenario_report: Any | None = None,
        technical_report: Any | None = None,
        ratio_set: Any | None = None,
    ) -> InvestmentDecision:
        score = 50.0
        rationale: list[str] = []
        inputs: dict[str, Any] = {}
        breakdown: list[dict[str, Any]] = []
        available = False

        if valuation_report is not None and getattr(valuation_report, "valuation_signal", "unavailable") != "unavailable":
            available = True
            signal = valuation_report.valuation_signal
            inputs["valuation_signal"] = signal

            if signal == "undervalued":
                points = 25.0
                rationale.append("Valuation signal is undervalued.")
            elif signal == "fair":
                points = 10.0
                rationale.append("Valuation signal is fair.")
            else:
                points = -15.0
                rationale.append("Valuation signal is overvalued.")

            score += points
            breakdown.append({"component": "Valuation", "reading": signal, "points": points})

        if forensic_report is not None and getattr(forensic_report, "fraud_probability", None) is not None:
            available = True
            fraud_probability = float(forensic_report.fraud_probability)
            inputs["fraud_probability"] = fraud_probability

            if fraud_probability <= 20.0:
                points = 15.0
                rationale.append("Forensic fraud probability is low.")
            elif fraud_probability <= 50.0:
                points = 0.0
                rationale.append("Forensic fraud probability is moderate.")
            else:
                points = -25.0
                rationale.append("Forensic fraud probability is high.")

            score += points
            breakdown.append({"component": "Forensic Risk", "reading": f"{fraud_probability:.1f}% fraud probability", "points": points})

        if scenario_report is not None and getattr(scenario_report, "scenarios", None):
            base_scenario = next(
                (scenario for scenario in scenario_report.scenarios if scenario.name == "base"),
                None,
            )

            if base_scenario is not None and base_scenario.upside_pct is not None:
                available = True
                upside = float(base_scenario.upside_pct)
                inputs["scenario_upside_pct"] = upside

                if upside > 30.0:
                    points = 20.0
                    rationale.append(f"Scenario upside is strong at {upside:.1f}%.")
                elif upside > 10.0:
                    points = 10.0
                    rationale.append(f"Scenario upside is positive at {upside:.1f}%.")
                elif upside >= 0.0:
                    points = 0.0
                    rationale.append(f"Scenario upside is limited at {upside:.1f}%.")
                else:
                    points = -10.0
                    rationale.append(f"Scenario downside is {upside:.1f}%.")

                score += points
                breakdown.append({"component": "Scenario Upside", "reading": f"{upside:.1f}% base upside", "points": points})

        if technical_report is not None and getattr(technical_report, "trend", None):
            trend = technical_report.trend

            if trend != "insufficient_data":
                available = True
                inputs["technical_trend"] = trend

                if trend == "uptrend":
                    points = 10.0
                    rationale.append("Technical trend is upward.")
                elif trend == "short_term_bullish":
                    points = 5.0
                    rationale.append("Technical trend is short-term bullish.")
                elif trend == "sideways":
                    points = 0.0
                    rationale.append("Technical trend is sideways.")
                elif trend == "short_term_bearish":
                    points = -5.0
                    rationale.append("Technical trend is short-term bearish.")
                else:
                    points = -10.0
                    rationale.append("Technical trend is downward.")

                score += points
                breakdown.append({"component": "Technical Trend", "reading": trend.replace("_", " "), "points": points})

        if forensic_report is not None and getattr(forensic_report, "piotroski", None) is not None:
            piotroski_score = getattr(forensic_report.piotroski, "score", None)

            if piotroski_score is not None:
                available = True
                inputs["piotroski_f"] = piotroski_score

                if piotroski_score >= 7:
                    points = 10.0
                    rationale.append(f"Piotroski F-Score is strong at {piotroski_score}/9.")
                elif piotroski_score >= 4:
                    points = 5.0
                    rationale.append(f"Piotroski F-Score is moderate at {piotroski_score}/9.")
                else:
                    points = -10.0
                    rationale.append(f"Piotroski F-Score is weak at {piotroski_score}/9.")

                score += points
                breakdown.append({"component": "Fundamental Quality", "reading": f"Piotroski {piotroski_score}/9", "points": points})

        inputs["component_breakdown"] = breakdown

        if not available:
            return InvestmentDecision(
                recommendation="unavailable",
                score=None,
                rationale=["Insufficient analysis outputs are available to make an investment decision."],
                inputs=inputs,
            )

        score = max(0.0, min(100.0, score))

        if score >= 70.0:
            recommendation = "buy"
        elif score >= 50.0:
            recommendation = "hold"
        else:
            recommendation = "avoid"

        rationale.insert(0, f"Composite decision score is {score:.1f}/100.")

        return InvestmentDecision(
            recommendation=recommendation,
            score=score,
            rationale=rationale,
            inputs=inputs,
        )
