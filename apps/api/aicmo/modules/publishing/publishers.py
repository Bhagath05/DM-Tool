"""Platform publishers — real API calls only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import structlog

from aicmo.modules.integrations import crypto
from aicmo.modules.integrations.http_retry import with_retry
from aicmo.modules.integrations.models import IntegrationCredential
from aicmo.modules.integrations.providers.facebook_pages import get_page_access_token
from aicmo.modules.publishing.text import extract_caption, extract_media_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

_GRAPH_BASE = "https://graph.facebook.com/v18.0"
_GBP_BASE = "https://mybusiness.googleapis.com/v4"
_LINKEDIN_API = "https://api.linkedin.com"
_YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
_PINTEREST_API = "https://api.pinterest.com/v5"
_LINKEDIN_VERSION = "202401"


@dataclass(frozen=True)
class PublishResult:
    platform_post_id: str
    raw: dict


async def publish_instagram(
    session: AsyncSession,
    *,
    access_token: str,
    metadata: dict,
    payload: dict,
) -> PublishResult:
    ig_id = metadata.get("ig_business_account_id")
    if not ig_id:
        raise RuntimeError(
            "Instagram Business Account ID missing — reconnect Instagram."
        )

    caption = extract_caption(payload)
    media_url = extract_media_url(payload)
    if not caption and not media_url:
        raise RuntimeError("Nothing to publish — asset has no caption or media.")

    async with httpx.AsyncClient(timeout=60.0) as client:
        if media_url:
            create = await client.post(
                f"{_GRAPH_BASE}/{ig_id}/media",
                params={
                    "access_token": access_token,
                    "image_url": media_url,
                    "caption": caption[:2200] if caption else "",
                },
            )
        else:
            raise RuntimeError(
                "Instagram requires an image URL to publish — attach a rendered poster first."
            )
        if create.status_code >= 400:
            raise RuntimeError(f"Instagram media create failed: {create.text[:500]}")
        creation_id = create.json().get("id")
        if not creation_id:
            raise RuntimeError("Instagram did not return a media container id.")

        publish = await client.post(
            f"{_GRAPH_BASE}/{ig_id}/media_publish",
            params={
                "access_token": access_token,
                "creation_id": creation_id,
            },
        )
        if publish.status_code >= 400:
            raise RuntimeError(f"Instagram publish failed: {publish.text[:500]}")
        post_id = publish.json().get("id")
        if not post_id:
            raise RuntimeError("Instagram did not return a published post id.")

    return PublishResult(platform_post_id=str(post_id), raw={"creation_id": creation_id})


async def publish_google_business_profile(
    session: AsyncSession,
    *,
    connection_id: str,
    location_name: str | None,
    payload: dict,
) -> PublishResult:
    if not location_name:
        raise RuntimeError(
            "Google Business Profile location missing — reconnect GBP."
        )

    conn_uuid = uuid.UUID(connection_id)
    cred = (
        await session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.connection_id == conn_uuid
            )
        )
    ).scalar_one_or_none()
    if cred is None:
        raise RuntimeError("Google Business Profile credentials missing.")

    access_token = crypto.decrypt(cred.encrypted_access_token)
    summary = extract_caption(payload)
    if not summary:
        raise RuntimeError("Nothing to publish — asset has no text.")

    body = {
        "languageCode": "en",
        "summary": summary[:1500],
        "topicType": "STANDARD",
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            f"{_GBP_BASE}/{location_name}/localPosts",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GBP local post failed: {resp.text[:500]}")
        data = resp.json()
        post_name = data.get("name") or data.get("searchUrl") or "gbp_post"

    return PublishResult(platform_post_id=str(post_name), raw=data)


async def publish_facebook(
    session: AsyncSession,
    *,
    access_token: str,
    page_id: str | None,
    payload: dict,
) -> PublishResult:
    if not page_id:
        raise RuntimeError("Facebook Page ID missing — reconnect Facebook.")

    caption = extract_caption(payload)
    media_url = extract_media_url(payload)
    if not caption and not media_url:
        raise RuntimeError("Nothing to publish — asset has no caption or media.")

    page_token = await get_page_access_token(access_token, page_id)
    async with httpx.AsyncClient(timeout=60.0) as client:
        if media_url:
            resp = await with_retry(
                lambda: client.post(
                    f"{_GRAPH_BASE}/{page_id}/photos",
                    params={
                        "access_token": page_token,
                        "url": media_url,
                        "caption": caption[:63206] if caption else "",
                    },
                )
            )
        else:
            resp = await with_retry(
                lambda: client.post(
                    f"{_GRAPH_BASE}/{page_id}/feed",
                    params={
                        "access_token": page_token,
                        "message": caption[:63206],
                    },
                )
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Facebook publish failed: {resp.text[:500]}")
        data = resp.json()
        post_id = data.get("id") or data.get("post_id") or "facebook_post"

    return PublishResult(platform_post_id=str(post_id), raw=data)


async def publish_linkedin(
    session: AsyncSession,
    *,
    access_token: str,
    organization_id: str | None,
    payload: dict,
) -> PublishResult:
    if not organization_id:
        raise RuntimeError("LinkedIn organization missing — reconnect LinkedIn.")

    caption = extract_caption(payload)
    media_url = extract_media_url(payload)
    if not caption and not media_url:
        raise RuntimeError("Nothing to publish — asset has no caption or media.")

    org_urn = organization_id
    if not org_urn.startswith("urn:"):
        org_urn = f"urn:li:organization:{organization_id}"

    body: dict = {
        "author": org_urn,
        "commentary": caption[:3000] if caption else "",
        "visibility": "PUBLIC",
        "lifecycleState": "PUBLISHED",
        "distribution": {"feedDistribution": "MAIN_FEED"},
    }
    if media_url:
        body["content"] = {
            "media": {
                "title": caption[:200] if caption else "Post",
                "id": media_url,
            }
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": _LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await with_retry(
            lambda: client.post(
                f"{_LINKEDIN_API}/rest/posts",
                headers=headers,
                json=body,
            )
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"LinkedIn publish failed: {resp.text[:500]}")
        post_id = resp.headers.get("x-restli-id") or resp.json().get("id", "linkedin_post")

    return PublishResult(platform_post_id=str(post_id), raw={"status": resp.status_code})


async def publish_youtube(
    session: AsyncSession,
    *,
    access_token: str,
    channel_id: str | None,
    payload: dict,
) -> PublishResult:
    caption = extract_caption(payload)
    media_url = extract_media_url(payload)
    if not media_url:
        raise RuntimeError(
            "YouTube requires a video URL to publish — attach a video asset first."
        )

    title = (caption.split("\n")[0] if caption else "Uploaded video")[:100]
    description = caption[:5000] if caption else ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        video_resp = await with_retry(lambda: client.get(media_url))
        if video_resp.status_code >= 400:
            raise RuntimeError(f"Could not fetch video from {media_url[:80]}")
        video_bytes = video_resp.content

        init_resp = await with_retry(
            lambda: client.post(
                f"{_YOUTUBE_API}/videos",
                params={
                    "part": "snippet,status",
                    "uploadType": "resumable",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "snippet": {
                        "title": title,
                        "description": description,
                        "channelId": channel_id,
                    },
                    "status": {"privacyStatus": "public"},
                },
            )
        )
        if init_resp.status_code >= 400:
            raise RuntimeError(f"YouTube upload init failed: {init_resp.text[:500]}")
        upload_url = init_resp.headers.get("location")
        if not upload_url:
            raise RuntimeError("YouTube did not return an upload URL.")

        upload_resp = await with_retry(
            lambda: client.put(
                upload_url,
                content=video_bytes,
                headers={
                    "Content-Type": "video/*",
                    "Content-Length": str(len(video_bytes)),
                },
            )
        )
        if upload_resp.status_code >= 400:
            raise RuntimeError(f"YouTube upload failed: {upload_resp.text[:500]}")
        data = upload_resp.json()
        video_id = data.get("id", "youtube_video")

    _ = channel_id
    return PublishResult(platform_post_id=str(video_id), raw=data)


async def publish_pinterest(
    session: AsyncSession,
    *,
    access_token: str,
    board_id: str | None,
    payload: dict,
) -> PublishResult:
    if not board_id:
        raise RuntimeError("Pinterest board missing — reconnect Pinterest.")

    caption = extract_caption(payload)
    media_url = extract_media_url(payload)
    if not media_url:
        raise RuntimeError(
            "Pinterest requires an image URL to publish — attach a rendered image first."
        )

    body = {
        "board_id": board_id,
        "title": (caption.split("\n")[0] if caption else "Pin")[:100],
        "description": caption[:500] if caption else "",
        "media_source": {"source_type": "image_url", "url": media_url},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await with_retry(
            lambda: client.post(
                f"{_PINTEREST_API}/pins",
                headers=headers,
                json=body,
            )
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Pinterest publish failed: {resp.text[:500]}")
        data = resp.json()
        pin_id = data.get("id", "pinterest_pin")

    return PublishResult(platform_post_id=str(pin_id), raw=data)
