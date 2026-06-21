from __future__ import annotations

from typing import Any


REPLAYED_STABLE_ANALYSIS_SIGNALS = (
    "stable_analysis.stable_internal_ratio",
    "stable_analysis.stable_internal_chars",
    "stable_analysis.stable_overlap_source",
)


def audit_current_evidence_contract(summary: dict[str, Any]) -> dict[str, Any]:
    """Check that an aggregate paper summary matches the current replay contract."""
    reasons: list[str] = []
    report_count = summary.get("report_count")
    if not isinstance(report_count, int) or isinstance(report_count, bool):
        results = summary.get("results")
        if isinstance(results, list) and results:
            report_count = len(results)
    lifecycle_summary = summary.get("lifecycle_replay_summary", {})
    if not isinstance(lifecycle_summary, dict):
        lifecycle_summary = {}
    replayed_counts = lifecycle_summary.get("replayed_runtime_signal_counts", {})
    if not isinstance(replayed_counts, dict):
        replayed_counts = {}
    if not replayed_counts:
        lifecycle_contract = summary.get("lifecycle_replay_contract", {})
        if isinstance(lifecycle_contract, dict):
            replayed_signals = lifecycle_contract.get("replayed_runtime_signals", [])
            if isinstance(replayed_signals, list):
                replayed_counts = {
                    str(signal): 1 for signal in replayed_signals if str(signal).strip()
                }
    missing_counts = lifecycle_summary.get("missing_runtime_signal_counts", {})
    if not isinstance(missing_counts, dict):
        missing_counts = {}

    if not isinstance(report_count, int) or isinstance(report_count, bool) or report_count <= 0:
        reasons.append("missing positive report_count")
    for signal in REPLAYED_STABLE_ANALYSIS_SIGNALS:
        replayed_count = replayed_counts.get(signal)
        if not isinstance(replayed_count, int) or isinstance(replayed_count, bool) or replayed_count <= 0:
            reasons.append(f"missing replayed runtime signal count: {signal}")
        missing_count = missing_counts.get(signal)
        if isinstance(missing_count, int) and not isinstance(missing_count, bool) and missing_count > 0:
            reasons.append(f"stable analysis signal is still marked missing: {signal}")
    return {
        "ok": not reasons,
        "stale_evidence_reasons": reasons,
        "required_replayed_runtime_signals": list(REPLAYED_STABLE_ANALYSIS_SIGNALS),
    }
