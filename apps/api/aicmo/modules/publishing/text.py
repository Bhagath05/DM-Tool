"""Extract publishable text and media from content asset payloads."""

from __future__ import annotations


def extract_caption(payload: dict) -> str:
    output = payload.get("output") or {}
    content_type = payload.get("content_type") or payload.get("asset_type")

    if content_type == "social_post":
        parts = [
            output.get("hook"),
            output.get("body"),
            output.get("cta"),
        ]
        hashtags = output.get("hashtags") or []
        text = "\n\n".join(p for p in parts if p)
        if hashtags:
            text = f"{text}\n\n{' '.join('#' + h.lstrip('#') for h in hashtags)}"
        return text.strip()

    if content_type == "reel":
        parts = [output.get("hook"), output.get("caption")]
        hashtags = output.get("hashtags") or []
        text = "\n".join(p for p in parts if p)
        if hashtags:
            text = f"{text}\n\n{' '.join('#' + h.lstrip('#') for h in hashtags)}"
        return text.strip()

    if content_type == "carousel":
        slides = output.get("slides") or []
        slide_text = []
        for i, slide in enumerate(slides, start=1):
            title = slide.get("title") or slide.get("headline") or ""
            body = slide.get("body") or slide.get("caption") or ""
            slide_text.append(f"Slide {i}: {title}\n{body}".strip())
        caption = output.get("caption") or output.get("cover_caption") or ""
        parts = slide_text + ([caption] if caption else [])
        return "\n\n".join(parts).strip()

    if content_type == "ad_copy":
        parts = [
            output.get("headline"),
            output.get("primary_text"),
            output.get("description"),
            output.get("cta"),
        ]
        return "\n\n".join(p for p in parts if p).strip()

    if isinstance(output, dict) and output.get("caption"):
        return str(output["caption"])

    return str(output)[:2000] if output else ""


def extract_media_url(payload: dict) -> str | None:
    media = payload.get("media_url") or payload.get("image_url")
    if media:
        return str(media)
    output = payload.get("output") or {}
    if isinstance(output, dict):
        return output.get("media_url") or output.get("image_url")
    return None
