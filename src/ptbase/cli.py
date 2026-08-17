from __future__ import annotations

import argparse
from pathlib import Path

from .config import END_YEAR, ROOT, START_YEAR
from .extractors.states.az import extract_az
from .extractors.states.ca import extract_ca
from .extractors.states.fl import extract_fl
from .extractors.states.ga import extract_ga
from .extractors.states.mn import extract_mn
from .extractors.states.tx import extract_tx
from .extractors.states.wa import extract_wa
from .extractors.states.wi import extract_wi
from .reporting import write_validation_summary
from .transform import build_state_panel
from .validate import (
    validate_identical_schema,
    validate_no_combined_final,
    validate_state_panel,
    validate_value_concordance,
)

EXTRACTORS = {
    "AZ": extract_az,
    "CA": extract_ca,
    "FL": extract_fl,
    "GA": extract_ga,
    "MN": extract_mn,
    "TX": extract_tx,
    "WA": extract_wa,
    "WI": extract_wi,
}


def run_all(root: Path = ROOT) -> None:
    panels = {}
    diagnostics = {}
    errors: list[str] = []

    for state, extract in EXTRACTORS.items():
        raw, diag = extract()
        diagnostics[state] = diag

        intermediate_dir = root / "data" / "intermediate" / state
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        raw.to_csv(intermediate_dir / f"{state.lower()}_raw_normalized.csv", index=False)

        panel = build_state_panel(raw, state)
        panels[state] = panel

        out = (
            root
            / "data"
            / "final"
            / "states"
            / state
            / f"{state.lower()}_county_year_valuation_panel_{START_YEAR}_{END_YEAR}.csv"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        panel.to_csv(out, index=False)

        errors.extend(validate_state_panel(panel, state).errors)
        errors.extend(validate_value_concordance(panel, state, root / "metadata"))

    errors.extend(validate_identical_schema(panels))
    errors.extend(validate_no_combined_final(root))

    write_validation_summary(panels, diagnostics, errors, root / "reports" / "validation_summary.md")

    if errors:
        raise SystemExit("Validation failed:\n" + "\n".join(f"- {error}" for error in errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build official county-year valuation panels per state.")
    parser.add_argument("command", choices=["all"], help="Pipeline command to run.")
    args = parser.parse_args()
    if args.command == "all":
        run_all()


if __name__ == "__main__":
    main()
