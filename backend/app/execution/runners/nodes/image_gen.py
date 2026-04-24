"""OpenAI image generation runner."""

from __future__ import annotations

import asyncio
from typing import Any


IMAGE_GEN_MODELS = {"gpt-image-1", "dall-e-3", "dall-e-2"}
IMAGE_GEN_SIZES_BY_MODEL = {
    "dall-e-3": {"1024x1024", "1792x1024", "1024x1792"},
    "dall-e-2": {"256x256", "512x512", "1024x1024"},
    "gpt-image-1": {"1024x1024", "1536x1024", "1024x1536"},
}
IMAGE_GEN_QUALITIES = {"standard", "hd"}
IMAGE_GEN_STYLES = {"vivid", "natural"}


class ImageGenRunner:
    """Generates one image with OpenAI and returns browser-ready base64 output."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        credential_id = str(config.get("credential_id") or "").strip()
        if not credential_id:
            raise ValueError("Image Gen: 'credential_id' is required.")

        api_key = self._resolve_api_key(credential_id, context)
        if not api_key:
            raise ValueError(
                "Image Gen: No OpenAI API key found for the selected credential. "
                "Save an OpenAI credential and select it on this node."
            )

        model = str(config.get("model") or "dall-e-3").strip()
        prompt = str(config.get("prompt") or "").strip()
        size = str(config.get("size") or "1024x1024").strip()
        quality = str(config.get("quality") or "standard").strip()
        style = str(config.get("style") or "vivid").strip()

        self._validate_config(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
        )

        try:
            image = self._generate_image(
                api_key=api_key,
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
            )
        except Exception as exc:
            raise ValueError(self._format_openai_error(exc)) from exc

        image_base64 = str(image.get("b64_json") or "").strip()
        if not image_base64:
            raise ValueError("Image Gen: OpenAI did not return base64 image data.")

        width, height = self._parse_size(size)
        return {
            "image_base64": image_base64,
            "image_url": f"data:image/png;base64,{image_base64}",
            "mime_type": "image/png",
            "prompt_used": prompt,
            "revised_prompt": image.get("revised_prompt"),
            "width": width,
            "height": height,
            "model": model,
        }

    @staticmethod
    def _resolve_api_key(credential_id: str, context: dict[str, Any]) -> str:
        resolved_credentials: dict[str, str] = context.get("resolved_credentials") or {}
        api_key = str(resolved_credentials.get(credential_id) or "").strip()
        if api_key:
            return api_key

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        credential_data = all_credential_data.get(credential_id)
        if isinstance(credential_data, dict):
            return str(
                credential_data.get("api_key")
                or credential_data.get("openai_api_key")
                or credential_data.get("token")
                or ""
            ).strip()
        return ""

    @staticmethod
    def _validate_config(
        *,
        model: str,
        prompt: str,
        size: str,
        quality: str,
        style: str,
    ) -> None:
        if model not in IMAGE_GEN_MODELS:
            raise ValueError(
                "Image Gen: model must be one of gpt-image-1, dall-e-3, or dall-e-2."
            )
        if not prompt:
            raise ValueError("Image Gen: 'prompt' is required.")
        if size not in IMAGE_GEN_SIZES_BY_MODEL[model]:
            allowed = ", ".join(sorted(IMAGE_GEN_SIZES_BY_MODEL[model]))
            raise ValueError(f"Image Gen: size '{size}' is invalid for {model}. Use one of: {allowed}.")
        if quality not in IMAGE_GEN_QUALITIES:
            raise ValueError("Image Gen: quality must be standard or hd.")
        if style not in IMAGE_GEN_STYLES:
            raise ValueError("Image Gen: style must be vivid or natural.")

    @staticmethod
    def _generate_image(
        *,
        api_key: str,
        model: str,
        prompt: str,
        size: str,
        quality: str,
        style: str,
    ) -> dict[str, Any]:
        def _do_request() -> dict[str, Any]:
            import base64
            import httpx
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            kwargs: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "n": 1,
                "response_format": "b64_json",
            }
            if model == "dall-e-3":
                kwargs["quality"] = quality
                kwargs["style"] = style

            try:
                response = client.images.generate(**kwargs)
            except Exception as exc:
                if model == "gpt-image-1" and "response_format" in str(exc):
                    kwargs.pop("response_format", None)
                    response = client.images.generate(**kwargs)
                else:
                    raise

            data = getattr(response, "data", None) or []
            if not data:
                raise ValueError("OpenAI image response did not include any images.")

            first = data[0]
            b64 = getattr(first, "b64_json", None)
            url = getattr(first, "url", None)
            if not b64 and url:
                image_response = httpx.get(url)
                image_response.raise_for_status()
                b64 = base64.b64encode(image_response.content).decode("utf-8")

            return {
                "b64_json": b64,
                "revised_prompt": getattr(first, "revised_prompt", None),
            }

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

    @staticmethod
    def _parse_size(size: str) -> tuple[int, int]:
        try:
            width, height = size.lower().split("x", 1)
            return int(width), int(height)
        except Exception:
            return 1024, 1024

    @staticmethod
    def _format_openai_error(exc: Exception) -> str:
        message = str(exc)
        status_code = getattr(exc, "status_code", None)
        lower = message.lower()

        if status_code == 401 or "invalid api key" in lower or "incorrect api key" in lower:
            return "Image Gen: OpenAI API key is invalid or expired."
        if status_code == 429 or "rate limit" in lower:
            return "Image Gen: OpenAI rate limit exceeded. Try again later."
        if "safety" in lower or "policy" in lower or "content_policy" in lower:
            return f"Image Gen: Prompt was rejected by OpenAI policy. {message}"
        if "size" in lower:
            return f"Image Gen: Invalid image size for the selected model. {message}"
        return f"Image Gen: OpenAI image generation failed. {message}"
