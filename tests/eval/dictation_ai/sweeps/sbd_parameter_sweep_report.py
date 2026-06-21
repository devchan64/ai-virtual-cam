from __future__ import annotations

from collections import Counter
from typing import Any

from tests.eval.dictation_ai.cases.sbd_case_paths import (
    corpus_interpretation,
    missing_required_evidence_fields,
)


METRIC_KEYS = (
    "final_precision_avg",
    "final_recall_avg",
    "final_f1_avg",
    "final_boundary_f1_avg",
    "finalized_per_stage_start",
)
LANGUAGE_MARKDOWN_KEYS = (
    "final_precision_avg",
    "final_recall_avg",
    "final_f1_avg",
    "final_boundary_f1_avg",
    "staged_residue_count",
    "empty_final_count",
)
TAG_MARKDOWN_KEYS = LANGUAGE_MARKDOWN_KEYS
TAG_MARKDOWN_MAX_ROWS = 40
EVIDENCE_TAGS = (
    "missing-final",
    "stage-queue",
    "cjk-internal-gap",
    "duplicate-final",
    "no-end-marker",
    "boundary-mismatch",
    "staged-residue",
)


def numeric_delta(current: Any, baseline: Any) -> float | None:
    if isinstance(current, bool) or isinstance(baseline, bool):
        return None
    if not isinstance(current, (int, float)) or not isinstance(baseline, (int, float)):
        return None
    return float(current) - float(baseline)


def _numeric_deltas(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for key, value in current.items():
        delta = numeric_delta(value, baseline.get(key))
        if delta is not None:
            deltas[key] = delta
    return deltas


def _lifecycle_bottleneck_deltas(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    current_metrics = dict(current.get("metrics", {}))
    baseline_metrics = dict(baseline.get("metrics", {}))
    current_languages = dict(current.get("by_language", {}))
    baseline_languages = dict(baseline.get("by_language", {}))
    language_deltas: dict[str, dict[str, float]] = {}
    for language, language_summary in current_languages.items():
        baseline_summary = baseline_languages.get(language, {})
        if not isinstance(language_summary, dict) or not isinstance(baseline_summary, dict):
            continue
        language_deltas[language] = _numeric_deltas(language_summary, baseline_summary)
    return {
        "metrics": _numeric_deltas(current_metrics, baseline_metrics),
        "replacement_decision_counts": _numeric_deltas(
            dict(current.get("replacement_decision_counts", {})),
            dict(baseline.get("replacement_decision_counts", {})),
        ),
        "deferred_replacement_decision_counts": _numeric_deltas(
            dict(current.get("deferred_replacement_decision_counts", {})),
            dict(baseline.get("deferred_replacement_decision_counts", {})),
        ),
        "quality_block_reason_counts": _numeric_deltas(
            dict(current.get("quality_block_reason_counts", {})),
            dict(baseline.get("quality_block_reason_counts", {})),
        ),
        "by_language": language_deltas,
    }


def _queue_residue_strata_deltas(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    deltas = _numeric_deltas(current, baseline)
    deltas["metrics"] = _numeric_deltas(
        dict(current.get("metrics", {})),
        dict(baseline.get("metrics", {})),
    )
    return deltas


def attach_baseline_deltas(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = next((result for result in results if not result.get("env_overrides")), None)
    if baseline is None:
        return results
    baseline_metrics = dict(baseline.get("metrics", {}))
    baseline_languages = dict(baseline.get("language_summary", {}))
    baseline_tags = dict(baseline.get("tag_summary", {}))
    baseline_lifecycle_bottlenecks = dict(baseline.get("lifecycle_bottleneck_summary", {}))
    baseline_queue_residue = dict(baseline.get("staged_queue_residue_summary", {}))
    baseline_queue_strata = dict(baseline.get("queue_residue_strata_summary", {}))
    baseline_strata = dict(baseline.get("evidence_strata_summary", {}))
    updated: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        metric_deltas = _numeric_deltas(dict(result.get("metrics", {})), baseline_metrics)
        language_deltas: dict[str, dict[str, float]] = {}
        for language, language_summary in dict(result.get("language_summary", {})).items():
            baseline_summary = baseline_languages.get(language, {})
            if not isinstance(language_summary, dict) or not isinstance(baseline_summary, dict):
                continue
            language_deltas[language] = _numeric_deltas(language_summary, baseline_summary)
        item["metric_deltas"] = metric_deltas
        item["language_deltas"] = language_deltas
        tag_deltas: dict[str, dict[str, float]] = {}
        for tag, tag_summary in dict(result.get("tag_summary", {})).items():
            baseline_summary = baseline_tags.get(tag, {})
            if not isinstance(tag_summary, dict) or not isinstance(baseline_summary, dict):
                continue
            tag_deltas[tag] = _numeric_deltas(tag_summary, baseline_summary)
        item["tag_deltas"] = tag_deltas
        item["lifecycle_bottleneck_deltas"] = _lifecycle_bottleneck_deltas(
            dict(result.get("lifecycle_bottleneck_summary", {})),
            baseline_lifecycle_bottlenecks,
        )
        item["staged_queue_residue_deltas"] = _numeric_deltas(
            dict(result.get("staged_queue_residue_summary", {})),
            baseline_queue_residue,
        )
        queue_strata_deltas: dict[str, dict[str, Any]] = {}
        for stratum, stratum_summary in dict(result.get("queue_residue_strata_summary", {})).items():
            baseline_summary = baseline_queue_strata.get(stratum, {})
            if not isinstance(stratum_summary, dict) or not isinstance(baseline_summary, dict):
                continue
            queue_strata_deltas[stratum] = _queue_residue_strata_deltas(stratum_summary, baseline_summary)
        item["queue_residue_strata_deltas"] = queue_strata_deltas
        strata_deltas: dict[str, dict[str, float]] = {}
        for stratum, stratum_summary in dict(result.get("evidence_strata_summary", {})).items():
            baseline_summary = baseline_strata.get(stratum, {})
            if not isinstance(stratum_summary, dict) or not isinstance(baseline_summary, dict):
                continue
            strata_deltas[stratum] = _numeric_deltas(stratum_summary, baseline_summary)
        item["evidence_strata_deltas"] = strata_deltas
        updated.append(item)
    return updated


def _select_summary_values(summary: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: summary.get(key) for key in keys if key in summary}


def _has_negative_delta(summary: dict[str, Any], key: str) -> bool:
    value = summary.get(key)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) < 0.0


def _has_positive_delta(summary: dict[str, Any], key: str) -> bool:
    value = summary.get(key)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0.0


def build_interpretation_flags(
    *,
    metric_deltas: dict[str, Any],
    language_deltas: dict[str, dict[str, Any]],
    key_tag_deltas: dict[str, dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    if _has_positive_delta(metric_deltas, "final_f1_avg") and _has_negative_delta(
        metric_deltas, "final_precision_avg"
    ):
        flags.append("overall-final-f1-up-precision-down")
    if _has_positive_delta(metric_deltas, "final_f1_avg") and _has_negative_delta(
        metric_deltas, "final_boundary_f1_avg"
    ):
        flags.append("overall-final-f1-up-boundary-down")
    if any(_has_negative_delta(deltas, "final_f1_avg") for deltas in language_deltas.values()):
        flags.append("language-final-f1-regression")
    if any(_has_negative_delta(deltas, "final_precision_avg") for deltas in language_deltas.values()):
        flags.append("language-precision-regression")
    if any(_has_negative_delta(deltas, "final_precision_avg") for deltas in key_tag_deltas.values()):
        flags.append("key-tag-precision-regression")
    if any(_has_negative_delta(deltas, "final_boundary_f1_avg") for deltas in key_tag_deltas.values()):
        flags.append("key-tag-boundary-regression")
    return flags


def _adoption_review_status(interpretation_flags: list[str], *, has_override: bool) -> str:
    if not has_override:
        return "baseline"
    if interpretation_flags:
        return "review-risk"
    return "no-risk-flag"


def build_evidence_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact interpretation payload for paper/evidence notes."""
    compact_results: list[dict[str, Any]] = []
    flag_counts: Counter[str] = Counter()
    adoption_review_counts: Counter[str] = Counter()
    for result in results:
        language_deltas = {}
        for language, deltas in dict(result.get("language_deltas", {})).items():
            if not isinstance(deltas, dict):
                continue
            language_deltas[language] = _select_summary_values(deltas, LANGUAGE_MARKDOWN_KEYS)

        tag_deltas = {}
        for tag in EVIDENCE_TAGS:
            deltas = dict(result.get("tag_deltas", {})).get(tag)
            if not isinstance(deltas, dict):
                continue
            tag_deltas[tag] = _select_summary_values(deltas, TAG_MARKDOWN_KEYS)

        metric_deltas = dict(result.get("metric_deltas", {}))
        interpretation_flags = build_interpretation_flags(
            metric_deltas=metric_deltas,
            language_deltas=language_deltas,
            key_tag_deltas=tag_deltas,
        )
        has_override = bool(dict(result.get("env_overrides", {})))
        if has_override:
            flag_counts.update(interpretation_flags)
        adoption_review = _adoption_review_status(
            interpretation_flags,
            has_override=has_override,
        )
        if has_override:
            adoption_review_counts.update([adoption_review])
        compact_results.append(
            {
                "label": result.get("label"),
                "env_overrides": result.get("env_overrides", {}),
                "metrics": dict(result.get("metrics", {})),
                "metric_deltas": metric_deltas,
                "language_deltas": language_deltas,
                "key_tag_deltas": tag_deltas,
                "lifecycle_bottleneck_summary": result.get("lifecycle_bottleneck_summary", {}),
                "lifecycle_bottleneck_deltas": result.get("lifecycle_bottleneck_deltas", {}),
                "staged_queue_residue_summary": result.get("staged_queue_residue_summary", {}),
                "staged_queue_residue_deltas": result.get("staged_queue_residue_deltas", {}),
                "queue_residue_strata_summary": result.get("queue_residue_strata_summary", {}),
                "queue_residue_strata_deltas": result.get("queue_residue_strata_deltas", {}),
                "evidence_strata_summary": result.get("evidence_strata_summary", {}),
                "evidence_strata_deltas": result.get("evidence_strata_deltas", {}),
                "case_exemplar_summary": result.get("case_exemplar_summary", {}),
                "interpretation_flags": interpretation_flags,
                "adoption_review": adoption_review,
            }
        )
    return {
        "metric_keys": list(METRIC_KEYS),
        "language_keys": list(LANGUAGE_MARKDOWN_KEYS),
        "key_tags": list(EVIDENCE_TAGS),
        "interpretation_flag_counts": dict(sorted(flag_counts.items())),
        "adoption_review_counts": dict(sorted(adoption_review_counts.items())),
        "results": compact_results,
    }


def _format_markdown_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _format_markdown_delta(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if abs(float(value)) < 0.00005:
        return "+0.0000"
    return f"{float(value):+.4f}"


def _format_markdown_counts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ", ".join(f"{key}={count}" for key, count in sorted(value.items()))


def _append_evidence_summary_markdown(lines: list[str], evidence_summary: dict[str, Any]) -> None:
    all_results = list(evidence_summary.get("results", []))
    results = [
        result
        for result in all_results
        if dict(result.get("env_overrides", {}))
    ]
    if not results:
        return
    lines.extend(
        [
            "",
            "## Evidence Summary",
            "",
            "| label | env | final_f1_delta | precision_delta | recall_delta | boundary_f1_delta |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        deltas = dict(result.get("metric_deltas", {}))
        env = ", ".join(f"{key}={value}" for key, value in dict(result.get("env_overrides", {})).items()) or "baseline"
        lines.append(
            f"| {result.get('label', '')} | {env} | "
            f"{_format_markdown_delta(deltas.get('final_f1_avg'))} | "
            f"{_format_markdown_delta(deltas.get('final_precision_avg'))} | "
            f"{_format_markdown_delta(deltas.get('final_recall_avg'))} | "
            f"{_format_markdown_delta(deltas.get('final_boundary_f1_avg'))} |"
        )

    lines.extend(
        [
            "",
            "| label | adoption_review | interpretation_flags |",
            "| --- | --- | --- |",
        ]
    )
    for result in results:
        flags = list(result.get("interpretation_flags", []))
        lines.append(
            f"| {result.get('label', '')} | {result.get('adoption_review', '')} | "
            f"{', '.join(str(flag) for flag in flags) or 'none'} |"
        )

    adoption_review_counts = dict(evidence_summary.get("adoption_review_counts", {}))
    if adoption_review_counts:
        lines.extend(
            [
                "",
                "| adoption_review | count |",
                "| --- | ---: |",
            ]
        )
        for status, count in sorted(adoption_review_counts.items()):
            lines.append(f"| {status} | {_format_markdown_number(count)} |")

    flag_counts = dict(evidence_summary.get("interpretation_flag_counts", {}))
    if flag_counts:
        lines.extend(
            [
                "",
                "| interpretation_flag | count |",
                "| --- | ---: |",
            ]
        )
        for flag, count in sorted(flag_counts.items()):
            lines.append(f"| {flag} | {_format_markdown_number(count)} |")

    lines.extend(
        [
            "",
            "| label | language | final_f1_delta | precision_delta | recall_delta | staged_residue_delta | empty_final_delta |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        for language, deltas in sorted(dict(result.get("language_deltas", {})).items()):
            if not isinstance(deltas, dict):
                continue
            lines.append(
                f"| {result.get('label', '')} | {language} | "
                f"{_format_markdown_delta(deltas.get('final_f1_avg'))} | "
                f"{_format_markdown_delta(deltas.get('final_precision_avg'))} | "
                f"{_format_markdown_delta(deltas.get('final_recall_avg'))} | "
                f"{_format_markdown_delta(deltas.get('staged_residue_count'))} | "
                f"{_format_markdown_delta(deltas.get('empty_final_count'))} |"
            )

    lines.extend(
        [
            "",
            "| label | tag | final_f1_delta | precision_delta | recall_delta | staged_residue_delta | empty_final_delta |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        for tag, deltas in dict(result.get("key_tag_deltas", {})).items():
            if not isinstance(deltas, dict):
                continue
            lines.append(
                f"| {result.get('label', '')} | {tag} | "
                f"{_format_markdown_delta(deltas.get('final_f1_avg'))} | "
                f"{_format_markdown_delta(deltas.get('final_precision_avg'))} | "
                f"{_format_markdown_delta(deltas.get('final_recall_avg'))} | "
                f"{_format_markdown_delta(deltas.get('staged_residue_count'))} | "
                f"{_format_markdown_delta(deltas.get('empty_final_count'))} |"
            )

    lines.extend(
        [
            "",
            "| label | stage_replace_deferred | queue_revision | quality_blocked | no_end_marker | short_no_end_fragment | unconfirmed_deferred | open_latin_deferred | unconfirmed_cjk_deferred |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in all_results:
        lifecycle_summary = dict(result.get("lifecycle_bottleneck_summary", {}))
        metrics = dict(lifecycle_summary.get("metrics", {}))
        quality_counts = dict(lifecycle_summary.get("quality_block_reason_counts", {}))
        deferred_counts = dict(lifecycle_summary.get("deferred_replacement_decision_counts", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_number(metrics.get('stage_replace_deferred'))} | "
            f"{_format_markdown_number(metrics.get('stage_queue_revision'))} | "
            f"{_format_markdown_number(metrics.get('stage_candidate_quality_blocked'))} | "
            f"{_format_markdown_number(quality_counts.get('no_end_marker'))} | "
            f"{_format_markdown_number(quality_counts.get('short_no_end_fragment'))} | "
            f"{_format_markdown_number(deferred_counts.get('unconfirmed'))} | "
            f"{_format_markdown_number(deferred_counts.get('open_latin_clause'))} | "
            f"{_format_markdown_number(deferred_counts.get('unconfirmed_cjk'))} |"
        )

    lines.extend(
        [
            "",
            "| label | queue_residue_cases | queue_residue_total | queue_residue_avg_when_present | queue_residue_max | queue_len_ge_2 | queue_len_ge_5 | active_staged_residue | pending_residue |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in all_results:
        queue_summary = dict(result.get("staged_queue_residue_summary", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_case_count'))} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_total'))} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_avg_when_present'))} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_max'))} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_len_ge_2_count'))} | "
            f"{_format_markdown_number(queue_summary.get('queue_residue_len_ge_5_count'))} | "
            f"{_format_markdown_number(queue_summary.get('active_staged_residue_case_count'))} | "
            f"{_format_markdown_number(queue_summary.get('pending_residue_case_count'))} |"
        )

    lines.extend(
        [
            "",
            "| label | top_queue_case | queue_len | queue_revision | replace_deferred | final_f1 | boundary_f1 | active_staged | pending |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for result in all_results:
        queue_summary = dict(result.get("staged_queue_residue_summary", {}))
        top_cases = list(queue_summary.get("top_queue_residue_cases", []))
        top = dict(top_cases[0]) if top_cases else {}
        lines.append(
            f"| {result.get('label', '')} | {top.get('id', '')} | "
            f"{_format_markdown_number(top.get('queue_len'))} | "
            f"{_format_markdown_number(top.get('stage_queue_revision'))} | "
            f"{_format_markdown_number(top.get('stage_replace_deferred'))} | "
            f"{_format_markdown_number(top.get('final_f1'))} | "
            f"{_format_markdown_number(top.get('final_boundary_f1'))} | "
            f"{_format_markdown_number(top.get('active_staged'))} | "
            f"{_format_markdown_number(top.get('pending'))} |"
        )

    lines.extend(
        [
            "",
            "| label | queue_stratum | cases | final_f1 | boundary_f1 | staged_residue | empty_final | queue_revision | replace_deferred |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in all_results:
        queue_strata = dict(result.get("queue_residue_strata_summary", {}))
        for stratum in ("no_queue", "queue_len_1", "queue_len_2_to_4", "queue_len_ge_5"):
            summary = dict(queue_strata.get(stratum, {}))
            metrics = dict(summary.get("metrics", {}))
            lines.append(
                f"| {result.get('label', '')} | {stratum} | "
                f"{_format_markdown_number(summary.get('case_count'))} | "
                f"{_format_markdown_number(summary.get('final_f1_avg'))} | "
                f"{_format_markdown_number(summary.get('final_boundary_f1_avg'))} | "
                f"{_format_markdown_number(summary.get('staged_residue_count'))} | "
                f"{_format_markdown_number(summary.get('empty_final_count'))} | "
                f"{_format_markdown_number(metrics.get('stage_queue_revision'))} | "
                f"{_format_markdown_number(metrics.get('stage_replace_deferred'))} |"
            )

    lines.extend(
        [
            "",
            "| label | lifecycle_focus_cases | lifecycle_without_input_review_cases | input_contamination_review_cases |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for result in all_results:
        strata = dict(result.get("evidence_strata_summary", {}))
        lifecycle_focus = dict(strata.get("lifecycle_focus", {}))
        lifecycle_clean = dict(strata.get("lifecycle_without_input_review", {}))
        input_review = dict(strata.get("input_contamination_review", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_number(lifecycle_focus.get('case_count'))} | "
            f"{_format_markdown_number(lifecycle_clean.get('case_count'))} | "
            f"{_format_markdown_number(input_review.get('case_count'))} |"
        )

    lines.extend(
        [
            "",
            "| label | clean_lifecycle_f1_delta | clean_lifecycle_boundary_delta | clean_lifecycle_staged_residue_delta | input_review_f1_delta | input_review_boundary_delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        strata_deltas = dict(result.get("evidence_strata_deltas", {}))
        lifecycle_clean = dict(strata_deltas.get("lifecycle_without_input_review", {}))
        input_review = dict(strata_deltas.get("input_contamination_review", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_delta(lifecycle_clean.get('final_f1_avg'))} | "
            f"{_format_markdown_delta(lifecycle_clean.get('final_boundary_f1_avg'))} | "
            f"{_format_markdown_delta(lifecycle_clean.get('staged_residue_count'))} | "
            f"{_format_markdown_delta(input_review.get('final_f1_avg'))} | "
            f"{_format_markdown_delta(input_review.get('final_boundary_f1_avg'))} |"
        )

    lines.extend(
        [
            "",
            "| label | top_lifecycle_case | bottleneck_score | queue_revision | replace_deferred | quality_blocked | final_f1 | boundary_f1 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in all_results:
        exemplars = dict(result.get("case_exemplar_summary", {}))
        lifecycle_top = list(exemplars.get("lifecycle_focus_top", []))
        top = dict(lifecycle_top[0]) if lifecycle_top else {}
        metrics = dict(top.get("metrics", {}))
        lines.append(
            f"| {result.get('label', '')} | {top.get('id', '')} | "
            f"{_format_markdown_number(top.get('bottleneck_score'))} | "
            f"{_format_markdown_number(metrics.get('stage_queue_revision'))} | "
            f"{_format_markdown_number(metrics.get('stage_replace_deferred'))} | "
            f"{_format_markdown_number(metrics.get('stage_candidate_quality_blocked'))} | "
            f"{_format_markdown_number(top.get('final_f1'))} | "
            f"{_format_markdown_number(top.get('final_boundary_f1'))} |"
        )

    lines.extend(
        [
            "",
            "| label | stage_replace_deferred_delta | queue_revision_delta | quality_blocked_delta | no_end_marker_delta | short_no_end_fragment_delta | unconfirmed_deferred_delta | open_latin_deferred_delta | unconfirmed_cjk_deferred_delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        lifecycle_deltas = dict(result.get("lifecycle_bottleneck_deltas", {}))
        metric_deltas = dict(lifecycle_deltas.get("metrics", {}))
        quality_deltas = dict(lifecycle_deltas.get("quality_block_reason_counts", {}))
        deferred_deltas = dict(lifecycle_deltas.get("deferred_replacement_decision_counts", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_delta(metric_deltas.get('stage_replace_deferred'))} | "
            f"{_format_markdown_delta(metric_deltas.get('stage_queue_revision'))} | "
            f"{_format_markdown_delta(metric_deltas.get('stage_candidate_quality_blocked'))} | "
            f"{_format_markdown_delta(quality_deltas.get('no_end_marker'))} | "
            f"{_format_markdown_delta(quality_deltas.get('short_no_end_fragment'))} | "
            f"{_format_markdown_delta(deferred_deltas.get('unconfirmed'))} | "
            f"{_format_markdown_delta(deferred_deltas.get('open_latin_clause'))} | "
            f"{_format_markdown_delta(deferred_deltas.get('unconfirmed_cjk'))} |"
        )

    lines.extend(
        [
            "",
            "| label | queue_residue_cases_delta | queue_residue_total_delta | queue_avg_present_delta | queue_max_delta | queue_len_ge_2_delta | queue_len_ge_5_delta | active_staged_residue_delta | pending_residue_delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        queue_deltas = dict(result.get("staged_queue_residue_deltas", {}))
        lines.append(
            f"| {result.get('label', '')} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_case_count'))} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_total'))} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_avg_when_present'))} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_max'))} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_len_ge_2_count'))} | "
            f"{_format_markdown_delta(queue_deltas.get('queue_residue_len_ge_5_count'))} | "
            f"{_format_markdown_delta(queue_deltas.get('active_staged_residue_case_count'))} | "
            f"{_format_markdown_delta(queue_deltas.get('pending_residue_case_count'))} |"
        )

    lines.extend(
        [
            "",
            "| label | queue_stratum | final_f1_delta | boundary_f1_delta | staged_residue_delta | empty_final_delta | queue_revision_delta | replace_deferred_delta |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        queue_strata_deltas = dict(result.get("queue_residue_strata_deltas", {}))
        for stratum in ("no_queue", "queue_len_1", "queue_len_2_to_4", "queue_len_ge_5"):
            deltas = dict(queue_strata_deltas.get(stratum, {}))
            lines.append(
                f"| {result.get('label', '')} | {stratum} | "
                f"{_format_markdown_delta(deltas.get('final_f1_avg'))} | "
                f"{_format_markdown_delta(deltas.get('final_boundary_f1_avg'))} | "
                f"{_format_markdown_delta(deltas.get('staged_residue_count'))} | "
                f"{_format_markdown_delta(deltas.get('empty_final_count'))} | "
                f"{_format_markdown_delta(deltas.get('metrics', {}).get('stage_queue_revision') if isinstance(deltas.get('metrics'), dict) else None)} | "
                f"{_format_markdown_delta(deltas.get('metrics', {}).get('stage_replace_deferred') if isinstance(deltas.get('metrics'), dict) else None)} |"
            )


def render_markdown_summary(payload: dict[str, Any]) -> str:
    case_summary = dict(payload.get("case_summary", {}))
    evidence_protocol = dict(payload.get("evidence_protocol", {}))
    runtime = dict(payload.get("runtime_contract", {}))
    lifecycle_replay = dict(payload.get("lifecycle_replay_contract", {}))
    offline_env = dict(runtime.get("offline_model_env", {}))
    corpus_role = str(evidence_protocol.get("corpus_role") or case_summary.get("corpus_role", "unknown"))
    required_fields = ", ".join(
        str(field) for field in evidence_protocol.get("required_evidence_fields", [])
    )
    missing_fields = ", ".join(
        str(field) for field in evidence_protocol.get("missing_required_evidence_fields", [])
    )
    supported_claims = ", ".join(str(item) for item in evidence_protocol.get("supported_claims", []))
    unsupported_claims = ", ".join(str(item) for item in evidence_protocol.get("unsupported_claims", []))
    deferred_claims = ", ".join(str(item) for item in evidence_protocol.get("deferred_claims", []))
    missing_runtime_signals = [
        str(item) for item in lifecycle_replay.get("missing_runtime_signals", []) if str(item).strip()
    ]
    replayed_runtime_signals = [
        str(item) for item in lifecycle_replay.get("replayed_runtime_signals", []) if str(item).strip()
    ]
    representative_metadata = dict(case_summary.get("representative_metadata", {}))
    representative_review_packet_validation = dict(case_summary.get("representative_review_packet_validation", {}))
    lines = [
        "# Dictation AI SBD Parameter Sweep",
        "",
        f"- dry_run: {str(payload.get('dry_run', False)).lower()}",
        f"- jobs: {len(payload.get('jobs', []))}",
        f"- corpus_roles: {', '.join(str(role) for role in payload.get('corpus_roles', [])) or 'unknown'}",
        f"- parameter_axes: {', '.join(str(axis) for axis in payload.get('parameter_axes', [])) or 'none'}",
        f"- corpus_role: {corpus_role}",
        f"- case_count: {case_summary.get('case_count', '')}",
        f"- expected_final_case_count: {case_summary.get('expected_final_case_count', '')}",
        f"- draft_count: {case_summary.get('draft_count', '')}",
        f"- interpretation: {evidence_protocol.get('corpus_interpretation') or corpus_interpretation(corpus_role)}",
        f"- experiment_stage: {evidence_protocol.get('experiment_stage', '')}",
        f"- experiment_stage_description: {evidence_protocol.get('experiment_stage_description', '')}",
        f"- evidence_use: {evidence_protocol.get('evidence_use', '')}",
        f"- claim_scope_key: {evidence_protocol.get('claim_scope_key', '')}",
        f"- claim_scope: {evidence_protocol.get('claim_scope', '')}",
        f"- supported_claims: {supported_claims}",
        f"- unsupported_claims: {unsupported_claims}",
        f"- deferred_claims: {deferred_claims}",
        f"- runtime: {runtime.get('backend', '')} + {runtime.get('device', '')} + {runtime.get('compute_type', '')}",
        f"- model_source: {runtime.get('model_source', '')}",
        f"- offline_model_env: {', '.join(f'{key}={value}' for key, value in sorted(offline_env.items()))}",
        f"- lifecycle_state_machine_parity: {lifecycle_replay.get('state_machine_parity', '')}",
        f"- lifecycle_runtime_state_owner: {lifecycle_replay.get('runtime_state_owner', '')}",
        f"- lifecycle_replay_state_owner: {lifecycle_replay.get('replay_state_owner', '')}",
        f"- lifecycle_replayed_runtime_signals: {', '.join(replayed_runtime_signals)}",
        f"- lifecycle_missing_runtime_signals: {', '.join(missing_runtime_signals)}",
        f"- paper_evidence_requested: {str(evidence_protocol.get('paper_evidence_requested', False)).lower()}",
        f"- paper_evidence: {str(evidence_protocol.get('paper_evidence', False)).lower()}",
        f"- paper_evidence_eligible: {str(evidence_protocol.get('paper_evidence_eligible', False)).lower()}",
        f"- required_evidence_fields: {required_fields}",
        f"- missing_required_evidence_fields: {missing_fields or 'none'}",
        "",
        "## Overall Metrics",
        "",
        "| label | env | " + " | ".join(METRIC_KEYS) + " |",
        "| --- | --- | " + " | ".join("---:" for _ in METRIC_KEYS) + " |",
    ]
    if representative_metadata:
        lines[10:10] = [
            f"- representative_sampling_units: {_format_markdown_counts(representative_metadata.get('sampling_unit_counts'))}",
            f"- representative_sampling_rules: {_format_markdown_counts(representative_metadata.get('sampling_rule_counts'))}",
            f"- representative_source_log_count: {representative_metadata.get('source_log_count', '')}",
            f"- representative_review_packet_count: {representative_metadata.get('review_packet_count', '')}",
            f"- representative_reviewers: {_format_markdown_counts(representative_metadata.get('expected_final_reviewer_counts'))}",
        ]
    if representative_review_packet_validation:
        lines[10:10] = [
            f"- representative_review_packet_validation_packet_count: {representative_review_packet_validation.get('packet_count', '')}",
            f"- representative_review_packet_validation_ready_packet_count: {representative_review_packet_validation.get('ready_packet_count', '')}",
            f"- representative_review_packet_validation_matched_case_count: {representative_review_packet_validation.get('matched_case_count', '')}",
        ]
    results = list(payload.get("results", []))
    for result in results:
        metrics = dict(result.get("metrics", {}))
        deltas = dict(result.get("metric_deltas", {}))
        env = ", ".join(f"{key}={value}" for key, value in dict(result.get("env_overrides", {})).items()) or "baseline"
        cells = []
        for key in METRIC_KEYS:
            value = _format_markdown_number(metrics.get(key))
            delta = _format_markdown_delta(deltas.get(key))
            cells.append(f"{value} ({delta})" if delta else value)
        lines.append(f"| {result.get('label', '')} | {env} | " + " | ".join(cells) + " |")

    _append_evidence_summary_markdown(lines, dict(payload.get("evidence_summary", {})))

    lines.extend(
        [
            "",
            "## Language Metrics",
            "",
            "| label | language | " + " | ".join(LANGUAGE_MARKDOWN_KEYS) + " |",
            "| --- | --- | " + " | ".join("---:" for _ in LANGUAGE_MARKDOWN_KEYS) + " |",
        ]
    )
    for result in results:
        language_summary = dict(result.get("language_summary", {}))
        language_deltas = dict(result.get("language_deltas", {}))
        for language in sorted(language_summary):
            summary = dict(language_summary.get(language, {}))
            deltas = dict(language_deltas.get(language, {}))
            cells = []
            for key in LANGUAGE_MARKDOWN_KEYS:
                value = _format_markdown_number(summary.get(key))
                delta = _format_markdown_delta(deltas.get(key))
                cells.append(f"{value} ({delta})" if delta else value)
            lines.append(f"| {result.get('label', '')} | {language} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Tag Metrics",
            "",
            "| label | tag | " + " | ".join(TAG_MARKDOWN_KEYS) + " |",
            "| --- | --- | " + " | ".join("---:" for _ in TAG_MARKDOWN_KEYS) + " |",
        ]
    )
    for result in results:
        tag_summary = dict(result.get("tag_summary", {}))
        tag_deltas = dict(result.get("tag_deltas", {}))
        ordered_tags = sorted(
            tag_summary,
            key=lambda tag: (-int(dict(tag_summary.get(tag, {})).get("case_count", 0)), tag),
        )[:TAG_MARKDOWN_MAX_ROWS]
        for tag in ordered_tags:
            summary = dict(tag_summary.get(tag, {}))
            deltas = dict(tag_deltas.get(tag, {}))
            cells = []
            for key in TAG_MARKDOWN_KEYS:
                value = _format_markdown_number(summary.get(key))
                delta = _format_markdown_delta(deltas.get(key))
                cells.append(f"{value} ({delta})" if delta else value)
            lines.append(f"| {result.get('label', '')} | {tag} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)
