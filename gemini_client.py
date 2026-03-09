"""
Клиент Gemini API через google-genai (новый SDK).
Retry при 429, перебор моделей.
"""
import time
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

# Актуальные модели с поддержкой vision
VISION_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]


def get_vision_json(api_key: str, image_bytes: bytes, prompt: str, max_retries: int = 3) -> str:
    """Vision + JSON. Retry при 429, перебор моделей."""
    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
    )
    last_err = None
    for model_name in VISION_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[image_part, prompt],
                    config=config,
                )
                text = response.text.strip() if response.text else ""
                return text
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "resource" in err_str:
                    time.sleep(2 ** attempt)
                    continue
                break
    raise RuntimeError(f"API ошибка: {last_err}")


def get_image_edit(api_key: str, image_bytes: bytes, prompt: str) -> Image.Image | None:
    """Редактирование изображения (Imagen / Gemini Image Gen)."""
    try:
        client = genai.Client(api_key=api_key)
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-image-generation",
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None):
                    return Image.open(BytesIO(part.inline_data.data)).convert("RGB")
    except Exception:
        pass
    return None


def get_vision_compare(
    api_key: str,
    before_bytes: bytes,
    after_bytes: bytes,
    prompt: str,
    mime: str = "image/jpeg",
) -> str:
    """Сравнение двух изображений."""
    client = genai.Client(api_key=api_key)
    before_part = types.Part.from_bytes(data=before_bytes, mime_type=mime)
    after_part = types.Part.from_bytes(data=after_bytes, mime_type=mime)
    config = types.GenerateContentConfig(temperature=0.2)
    last_err = None
    for model_name in VISION_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[before_part, "BEFORE:", after_part, "AFTER. " + prompt],
                config=config,
            )
            return (response.text or "").strip()
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Ни одна модель не сработала: {last_err}")
