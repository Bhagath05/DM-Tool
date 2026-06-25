"""Coerce LLM output before strict schema validation."""

from __future__ import annotations

from typing import Any


def _first_sentence(text: str, *, max_len: int = 60) -> str:
    chunk = (text or "").strip().split(".")[0].strip()
    if not chunk:
        return ""
    return chunk[:max_len]


def normalize_content_payload(content_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM omissions without inventing business facts."""
    out = dict(data)

    if content_type == "carousel":
        slides = out.get("slides") or []
        fixed_slides: list[dict[str, Any]] = []
        for i, slide in enumerate(slides):
            if not isinstance(slide, dict):
                continue
            s = dict(slide)
            title = (s.get("title") or s.get("headline") or "").strip()
            body = (s.get("body") or "").strip()
            if not title:
                title = _first_sentence(body) or f"Slide {i + 1}"
            s["title"] = title[:120]
            if not body:
                s["body"] = title
            fixed_slides.append(s)
        out["slides"] = fixed_slides
        cta_raw = out.get("cta_slide")
        if isinstance(cta_raw, dict):
            cta = dict(cta_raw)
            title = (cta.get("title") or cta.get("headline") or "").strip()
            body = (cta.get("body") or "").strip()
            if not title:
                title = (
                    _first_sentence(body)
                    or (str(out.get("cta") or "").strip())
                    or "Take action"
                )
            if not body:
                body = str(out.get("cta") or title).strip()
            out["cta_slide"] = {"title": title[:120], "body": body[:500]}
        elif fixed_slides:
            last = fixed_slides[-1]
            out["cta_slide"] = {
                "title": last.get("title", "Take action"),
                "body": last.get("body", out.get("cta", "Book now")),
            }

    if content_type == "reel":
        ost = out.get("on_screen_text")
        if isinstance(ost, list) and len(ost) > 8:
            out["on_screen_text"] = ost[:8]
        beats = out.get("beats")
        if isinstance(beats, list):
            fixed_beats = []
            for i, beat in enumerate(beats):
                if not isinstance(beat, dict):
                    continue
                b = dict(beat)
                if not (b.get("label") or "").strip():
                    b["label"] = f"Scene {i + 1}"
                fixed_beats.append(b)
            out["beats"] = fixed_beats
        if not out.get("voiceover_script"):
            parts: list[str] = []
            if out.get("hook"):
                parts.append(str(out["hook"]))
            for beat in out.get("beats") or []:
                if isinstance(beat, dict) and beat.get("description"):
                    parts.append(str(beat["description"]))
            if out.get("cta"):
                parts.append(str(out["cta"]))
            out["voiceover_script"] = " ".join(parts)[:2000]

    if content_type == "landing_page_copy":
        benefits = out.get("benefits") or []
        fixed_benefits: list[dict[str, Any]] = []
        for i, item in enumerate(benefits):
            if not isinstance(item, dict):
                continue
            b = dict(item)
            title = (b.get("title") or b.get("headline") or "").strip()
            body = (b.get("body") or "").strip()
            if not title:
                title = _first_sentence(body) or f"Benefit {i + 1}"
            if not body:
                body = title
            fixed_benefits.append({"title": title[:120], "body": body[:400]})
        if fixed_benefits:
            out["benefits"] = fixed_benefits

    return out
