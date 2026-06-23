#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DRAFT_VERSION = 1


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dominant_value(candidates: dict[str, Any]) -> str:
    if not candidates:
        return ""
    return max(
        ((str(key), int(value)) for key, value in candidates.items()),
        key=lambda item: (item[1], item[0]),
    )[0]


def _dominant_float(candidates: dict[str, Any]) -> float | None:
    best_key = _dominant_value(candidates)
    if not best_key:
        return None
    normalized = best_key.rstrip("s")
    try:
        return float(normalized)
    except ValueError:
        return None


def _dominant_int(candidates: dict[str, Any]) -> int | None:
    best_key = _dominant_value(candidates)
    if not best_key:
        return None
    try:
        return int(float(best_key.rstrip("s")))
    except ValueError:
        return None


def _sample_texts(packet: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for sample in _as_list(packet.get("raw_chunks_sample")):
        sample_record = _as_dict(sample)
        text = str(sample_record.get("text", "")).strip()
        if text:
            texts.append(text)
    return texts


def _draft_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    runtime = _as_dict(packet.get("runtime_candidates"))
    language = str(packet.get("language", "")).strip()
    packet_id = str(packet.get("id", "")).strip()
    return {
        "id": f"{packet_id}_draft",
        "corpus_role": "representative",
        "sampling_unit": str(packet.get("sampling_unit", "")).strip(),
        "sampling_rule": str(packet.get("sampling_rule", "")).strip(),
        "source_log": str(packet.get("source_log", "")).strip(),
        "source_started_at": str(packet.get("source_started_at", "")).strip(),
        "source_ended_at": str(packet.get("source_ended_at", "")).strip(),
        "source_window_filter": _as_dict(packet.get("source_window_filter")),
        "language": language,
        "priority_metric": packet.get("priority_metric"),
        "priority_rank": packet.get("priority_rank"),
        "priority_ratio": packet.get("priority_ratio"),
        "priority_marker_count": packet.get("priority_marker_count"),
        "stt_backend": _dominant_value(_as_dict(runtime.get("stt_backend_candidates"))),
        "stt_model": _dominant_value(_as_dict(runtime.get("stt_model_candidates"))),
        "window_seconds": _dominant_float(_as_dict(runtime.get("window_seconds_candidates"))),
        "step_seconds": _dominant_float(_as_dict(runtime.get("step_seconds_candidates"))),
        "sentence_finalize_age": _dominant_int(
            _as_dict(runtime.get("sentence_finalize_age_candidates"))
        ),
        "review_packet_id": packet_id,
        "expected_final_reviewed_by": "",
        "chunks": _sample_texts(packet),
        "expected_final": [],
        "expected_pending": "",
        "expected_staged": "",
        "draft_expected_final_required": True,
        "expected_final_generated": False,
        "paper_evidence": False,
        "tags": [tag for tag in (language, "representative", "manual-review-draft") if tag],
    }


def build_case_drafts(review_packets: dict[str, Any]) -> dict[str, Any]:
    packets = [_as_dict(packet) for packet in _as_list(review_packets.get("packets"))]
    ready_packets = [
        packet
        for packet in packets
        if bool(_as_dict(packet.get("review_readiness")).get("ready_for_human_review", False))
    ]
    drafts = [_draft_from_packet(packet) for packet in ready_packets]
    return {
        "representative_case_draft_version": DRAFT_VERSION,
        "source_review_packet_count": len(packets),
        "ready_review_packet_count": len(ready_packets),
        "draft_count": len(drafts),
        "paper_evidence": False,
        "case_generation": "manual_expected_final_required",
        "expected_final_generated": False,
        "drafts": drafts,
    }


def render_jsonl(drafts_payload: dict[str, Any]) -> str:
    lines = [
        json.dumps(draft, ensure_ascii=False, sort_keys=True)
        for draft in _as_list(drafts_payload.get("drafts"))
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def render_markdown(drafts_payload: dict[str, Any]) -> str:
    lines = [
        "# Representative Case Drafts",
        "",
        f"- source_review_packet_count: `{drafts_payload['source_review_packet_count']}`",
        f"- ready_review_packet_count: `{drafts_payload['ready_review_packet_count']}`",
        f"- draft_count: `{drafts_payload['draft_count']}`",
        "- paper_evidence: `false`",
        "- expected_final_generated: `false`",
        "",
        "이 파일은 사람이 `expected_final`을 확정하기 전의 draft다. 논문 수치나 benchmark 입력으로 사용하지 않는다.",
        "",
        "## Human Review Steps",
        "",
        "1. Review the linked source packet and the sampled STT chunks.",
        "2. Fill `expected_final` with human-confirmed final sentences.",
        "3. Fill `expected_final_reviewed_by` with a reviewer id or review batch id.",
        "4. Remove `draft_expected_final_required` before promotion.",
        "5. Keep `expected_final_generated=false`; do not auto-generate reference text.",
        "",
        "| id | language | source_log | chunks | review_packet_id |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for draft in _as_list(drafts_payload.get("drafts")):
        record = _as_dict(draft)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(record.get("id", "")),
                    str(record.get("language", "")),
                    str(record.get("source_log", "")),
                    str(len(_as_list(record.get("chunks")))),
                    str(record.get("review_packet_id", "")),
                ]
            )
            + " |"
        )
    for draft in _as_list(drafts_payload.get("drafts")):
        record = _as_dict(draft)
        chunks = [str(chunk) for chunk in _as_list(record.get("chunks")) if str(chunk).strip()]
        preview_chunks = chunks[:3]
        lines.extend(
            [
                "",
                f"## {record.get('id', '')}",
                "",
                f"- language: `{record.get('language', '')}`",
                f"- source_log: `{record.get('source_log', '')}`",
                f"- source_range: `{record.get('source_started_at', '')}` - `{record.get('source_ended_at', '')}`",
                f"- source_window_filter: `{record.get('source_window_filter', {})}`",
                f"- review_packet_id: `{record.get('review_packet_id', '')}`",
                f"- priority: metric=`{record.get('priority_metric', '')}` rank=`{record.get('priority_rank', '')}` ratio=`{record.get('priority_ratio', '')}` count=`{record.get('priority_marker_count', '')}`",
                f"- runtime: backend=`{record.get('stt_backend', '')}` model=`{record.get('stt_model', '')}` window=`{record.get('window_seconds', '')}` step=`{record.get('step_seconds', '')}` age=`{record.get('sentence_finalize_age', '')}`",
                "",
                "Checklist:",
                "",
                "- [ ] `expected_final` is filled by human review.",
                "- [ ] `expected_final_reviewed_by` is filled.",
                "- [ ] `draft_expected_final_required` is removed before promotion.",
                "- [ ] `expected_final_generated=false` is preserved.",
                "",
                "Template fields to edit:",
                "",
                "```json",
                json.dumps(
                    {
                        "id": record.get("id", ""),
                        "expected_final": [],
                        "expected_final_reviewed_by": "",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
            ]
        )
        if preview_chunks:
            lines.extend(["", "STT chunk preview:", ""])
            for index, chunk in enumerate(preview_chunks, start=1):
                lines.append(f"{index}. {chunk}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create manual representative case draft templates from review packets.",
    )
    parser.add_argument("review_packets", type=Path)
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-case-drafts.summary.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path(".tmp/eval/dictation-ai-sbd/representative-case-drafts.md"),
    )
    args = parser.parse_args()
    try:
        payload = json.loads(args.review_packets.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("review packet root must be a JSON object")
        drafts_payload = build_case_drafts(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[dictation-ai-sbd-representative-drafts] error: {exc}", file=sys.stderr)
        return 1
    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.jsonl_output.write_text(render_jsonl(drafts_payload), encoding="utf-8")
    args.summary_output.write_text(
        json.dumps(drafts_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(drafts_payload), encoding="utf-8")
    print(json.dumps(drafts_payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
