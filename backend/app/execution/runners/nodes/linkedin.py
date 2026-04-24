"""LinkedIn post runner — publishes a post to LinkedIn using OAuth credentials.

Credential resolution
---------------------
The ``execute_workflow`` task pre-resolves every ``credential_id`` found in node
configs and stores them in:
- ``runner_context["resolved_credentials"]``       : ``str(credential_id) → api_key``
- ``runner_context["resolved_credential_data"]``   : ``str(credential_id) → token_data``

This runner reads access_token + member_urn from credential data.

Config keys
-----------
- ``credential_id`` : str — UUID of an ``app_credentials`` row (app_name="linkedin").
- ``post_text``     : str — The post text to publish.
- ``image``         : str — Optional base64 image or data URI.
- ``visibility``    : str — One of PUBLIC or CONNECTIONS.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any

import httpx

LINKEDIN_UGC_POST_ENDPOINT = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_ASSETS_ENDPOINT = "https://api.linkedin.com/v2/assets?action=registerUpload"
LINKEDIN_ME_ENDPOINT = "https://api.linkedin.com/v2/userinfo"

class LinkedInRunner:
    """Posts content to LinkedIn using a saved LinkedIn credential."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        cred_id = config.get("credential_id")
        credential_data: dict[str, Any] = {}
        if cred_id:
            all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
            raw_data = all_credential_data.get(str(cred_id))
            if isinstance(raw_data, dict):
                credential_data = raw_data

        access_token = (
            config.get("access_token")
            or credential_data.get("access_token")
            or credential_data.get("api_key")
        )
        if not access_token:
            raise ValueError(
                "LinkedIn: No access token available. "
                "Add a credential (app_name='linkedin') with LinkedIn OAuth and set credential_id on the node config."
            )

        member_urn = config.get("member_urn") or credential_data.get("member_urn")
        if not member_urn:
            member_urn = self._fetch_member_urn(access_token)

        post_text = str(config.get("post_text") or "").strip()
        image = str(config.get("image") or "").strip()
        visibility = str(config.get("visibility") or "PUBLIC").strip().upper()
        if visibility.lower() == "connections":
            visibility = "CONNECTIONS"
        if visibility not in {"PUBLIC", "CONNECTIONS"}:
            raise ValueError(
                "LinkedIn: visibility must be PUBLIC or CONNECTIONS."
            )
        if not post_text:
            raise ValueError("LinkedIn: 'post_text' is required and cannot be empty.")

        try:
            asset_urn = (
                self._upload_image_asset(
                    access_token=access_token,
                    owner=member_urn,
                    image=image,
                )
                if image
                else None
            )
            response_data = self._create_ugc_post(
                access_token=access_token,
                author=member_urn,
                post_text=post_text,
                visibility=visibility,
                asset_urn=asset_urn,
            )
        except Exception as exc:
            raise ValueError(f"LinkedIn: Failed to publish post — {exc}") from exc

        _STRIP_PREFIXES = ("dummy_node_",)
        _STRIP_KEYS = {"_branch", "_split_index"}

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            for key, value in input_data.items():
                if key in _STRIP_KEYS:
                    continue
                if any(key.startswith(prefix) for prefix in _STRIP_PREFIXES):
                    continue
                result[key] = value

        post_id = response_data.get("id", "")
        
        result["post_id"] = post_id
        result["url"] = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""
        result["post_url"] = result["url"]
        result["image_asset_urn"] = asset_urn or ""
        result["published_at"] = datetime.now(timezone.utc).isoformat()
        return result

    @staticmethod
    def _fetch_member_urn(access_token: str) -> str:
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        def _do_request() -> str:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(LINKEDIN_ME_ENDPOINT, headers=headers)
                resp.raise_for_status()
                payload = resp.json()

            member_id = str(payload.get("sub") or "").strip()
            if not member_id:
                raise ValueError("LinkedIn: Could not resolve member URN from /v2/me response.")
            return f"urn:li:person:{member_id}"

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

    @staticmethod
    def _create_ugc_post(
        *,
        access_token: str,
        author: str,
        post_text: str,
        visibility: str,
        asset_urn: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        share_content: dict[str, Any] = {
            "shareCommentary": {"text": post_text},
            "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
        }
        if asset_urn:
            share_content["media"] = [
                {
                    "status": "READY",
                    "media": asset_urn,
                    "title": {"text": "Autoflow image"},
                }
            ]

        payload: dict[str, Any] = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility,
            },
        }

        def _do_request() -> dict[str, Any]:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(LINKEDIN_UGC_POST_ENDPOINT, json=payload, headers=headers)
                body = resp.json() if resp.content else {}
                if resp.status_code >= 400:
                    detail = body.get("message") or body.get("serviceErrorCode") or resp.text
                    if resp.status_code == 401:
                        raise ValueError(f"LinkedIn OAuth token expired or invalid. ({detail})")
                    if resp.status_code == 429:
                        raise ValueError(f"LinkedIn API rate limit exceeded. ({detail})")
                    raise ValueError(f"LinkedIn API error: {detail}")
                return body

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

    @staticmethod
    def _upload_image_asset(
        *,
        access_token: str,
        owner: str,
        image: str,
    ) -> str:
        image_bytes, mime_type = LinkedInRunner._decode_image(image)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": owner,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        def _do_request() -> str:
            with httpx.Client(timeout=30.0) as client:
                register_resp = client.post(
                    LINKEDIN_ASSETS_ENDPOINT,
                    json=register_payload,
                    headers=headers,
                )
                register_body = register_resp.json() if register_resp.content else {}
                if register_resp.status_code >= 400:
                    detail = register_body.get("message") or register_resp.text
                    raise ValueError(f"LinkedIn asset registration failed: {detail}")

                value = register_body.get("value") or {}
                upload_mechanism = (
                    value.get("uploadMechanism", {})
                    .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                )
                upload_url = upload_mechanism.get("uploadUrl")
                asset_urn = value.get("asset")
                if not upload_url or not asset_urn:
                    raise ValueError("LinkedIn asset registration response was missing uploadUrl or asset URN.")

                upload_resp = client.put(
                    upload_url,
                    content=image_bytes,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": mime_type,
                    },
                )
                if upload_resp.status_code >= 400:
                    raise ValueError(f"LinkedIn image upload failed: {upload_resp.text}")
                return str(asset_urn)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

    @staticmethod
    def _decode_image(value: str) -> tuple[bytes, str]:
        raw = str(value or "").strip()
        mime_type = "image/png"
        if raw.startswith("data:"):
            header, _, body = raw.partition(",")
            if ";base64" in header and header.startswith("data:"):
                mime_type = header[5:].split(";", 1)[0] or mime_type
            raw = body
        try:
            return base64.b64decode(raw, validate=True), mime_type
        except Exception as exc:
            raise ValueError("LinkedIn: image field must resolve to valid base64 image data.") from exc
