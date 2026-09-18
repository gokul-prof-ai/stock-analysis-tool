from __future__ import annotations

from ..models.report import ChecklistItem, ChecklistStatus

CHECKLIST_SECTIONS: list[tuple[str, str, int, str]] = [
    ("A", "Company & Business", 15, "M1 + M8"),
    ("B", "Industry Analysis", 12, "M4"),
    ("C", "Macro Analysis", 11, "M1 + M7"),
    ("D", "Balance Sheet", 12, "M1 + M2"),
    ("E", "P&L Statement", 9, "M1 + M2"),
    ("F", "Cash Flow", 6, "M1 + M2"),
    ("G", "Financial Ratios", 26, "M2"),
    ("H", "Growth Analysis", 11, "M2 + M7"),
    ("I", "Technical Analysis", 30, "M5"),
    ("J", "Valuation", 16, "M6"),
    ("K", "Dividend", 7, "M2"),
    ("L", "Shareholding", 9, "M1"),
    ("M", "Governance", 9, "M1 + M5"),
    ("N", "Risk Analysis", 12, "M3 + M5"),
    ("O", "Beta & Risk-Return", 11, "M6"),
    ("P", "Market Analysis", 9, "M4 + M7"),
    ("Q", "Scenario & Forecast", 11, "M7"),
    ("R", "Investment Decision", 11, "M8"),
]


def build_checklist(section_status: dict[str, ChecklistStatus]) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    for code, section_name, count, module in CHECKLIST_SECTIONS:
        status = section_status.get(code, "not_covered")

        for item_number in range(1, count + 1):
            items.append(
                ChecklistItem(
                    item_id=f"{code}{item_number:02d}",
                    section=section_name,
                    description=f"{section_name} checkpoint {item_number}",
                    module=module,
                    status=status,
                )
            )

    return items


def checklist_summary(items: list[ChecklistItem]) -> dict[str, int]:
    summary = {
        "covered": 0,
        "partial": 0,
        "not_covered": 0,
    }

    for item in items:
        summary[item.status] += 1

    return summary
