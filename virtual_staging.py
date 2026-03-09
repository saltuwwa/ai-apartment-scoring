"""
Задание 2: Виртуальный стейджинг — замена/добавление/удаление мебели на фото.
OpenAI GPT Image 1.5 с документацией гиперпараметров.
"""
import base64
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from config import GEMINI_API_KEY, OPENAI_API_KEY


@dataclass
class StagingConfig:
    """
    Гиперпараметры GPT Image 1.5 (влияние на результат):
    
    input_fidelity:
      - "low" — больше творческой свободы, сильнее изменения (рекомендуется для замены мебели)
      - "high" — сохраняет стиль/детали исходника (для мелких правок)
    
    quality:
      - "low" — быстро, дешевле
      - "medium" — баланс
      - "high" — лучшее качество (рекомендуется)
      - "auto" — модель выбирает сама
    
    size:
      - "auto" — сохраняет пропорции исходника
      - "1024x1024" — квадрат
      - "1536x1024" — альбомная
      - "1024x1536" — портретная
    
    background: "transparent" | "opaque" | "auto"
    """
    input_fidelity: str = "low"
    quality: str = "high"
    size: str = "auto"
    background: str = "auto"
    output_format: str = "png"


# Промпты для типичных операций (хорошо работают с GPT Image)
PROMPTS = {
    "replace": "Replace {old} with {new}. Keep the room layout, lighting and perspective. Photorealistic interior photo.",
    "add": "Add {item} to this room. Match existing lighting and style. Natural placement. Photorealistic.",
    "remove": "Remove {item} from this room. Fill the space naturally, keep the rest unchanged. Photorealistic.",
}


def load_image(image_input: Union[str, Path, Image.Image], max_side: int = 2048, square: bool = False) -> Image.Image:
    """Загружает изображение. square=True для DALL-E 2."""
    if isinstance(image_input, Image.Image):
        img = image_input.convert("RGB")
    else:
        path = Path(image_input)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
    if square:
        size = min(img.size)
        left = (img.width - size) // 2
        top = (img.height - size) // 2
        img = img.crop((left, top, left + size, top + size))
        img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
    return img


def _to_square_png(image_bytes: bytes) -> bytes:
    """Делает квадрат 1024x1024 (требование DALL-E 2)."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    if img.width == img.height and img.width == 1024:
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    size = min(img.width, img.height)
    left = (img.width - size) // 2
    top = (img.height - size) // 2
    img = img.crop((left, top, left + size, top + size)).resize((1024, 1024), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _stage_openai(image_bytes: bytes, prompt: str, config: StagingConfig) -> Image.Image:
    """OpenAI image edit — GPT Image 1.5 или DALL-E 2."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    img_bytes = _to_square_png(image_bytes)
    buf = BytesIO(img_bytes)
    buf.seek(0)
    last_err = None
    for model in ["gpt-image-1.5", "gpt-image-1", "dall-e-2"]:
        for attempt in range(3):
            try:
                img_file = ("image.png", buf, "image/png")
                buf.seek(0)
                kwargs = {"model": model, "image": img_file, "prompt": prompt}
                if model == "dall-e-2":
                    kwargs["response_format"] = "b64_json"
                else:
                    # GPT Image 1.5 — гиперпараметры
                    if config.input_fidelity:
                        kwargs["input_fidelity"] = config.input_fidelity
                    if config.quality:
                        kwargs["quality"] = config.quality
                    if config.size:
                        kwargs["size"] = config.size
                resp = client.images.edit(**kwargs)
                d = resp.data[0]
                if d.b64_json:
                    out = Image.open(BytesIO(base64.b64decode(d.b64_json)))
                elif d.url:
                    import urllib.request
                    with urllib.request.urlopen(d.url) as r:
                        out = Image.open(BytesIO(r.read()))
                else:
                    raise RuntimeError("No image in response")
                return out.convert("RGB")
            except Exception as e:
                last_err = e
                if "invalid" in str(e).lower() and "model" in str(e).lower():
                    break
                if "rate" in str(e).lower() or "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                raise
    raise RuntimeError(f"API error: {last_err}")


def _stage_gemini(image_bytes: bytes, prompt: str, config: StagingConfig) -> Image.Image:
    """Gemini — fallback."""
    from gemini_client import get_image_edit
    result = get_image_edit(GEMINI_API_KEY, image_bytes, prompt)
    if result is None:
        raise RuntimeError("Gemini недоступен. Добавь OPENAI_API_KEY для GPT Image 1.5.")
    return result


def virtual_stage(
    image_input: Union[str, Path, Image.Image],
    prompt: str,
    output_path: Optional[Union[str, Path]] = None,
    config: Optional[StagingConfig] = None,
) -> Image.Image:
    """
    Редактирует фото комнаты: замена/добавление/удаление мебели.
    
    Примеры prompt:
      "Replace the old sofa with a modern gray scandinavian sofa"
      "Add a minimalist white coffee table in front of the sofa"
      "Remove the chair and leave the space empty"
    """
    config = config or StagingConfig()
    image = load_image(image_input)
    buf = BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    if OPENAI_API_KEY and OPENAI_API_KEY not in ("", "your_openai_key_here"):
        try:
            result = _stage_openai(image_bytes, prompt, config)
        except Exception as e:
            if GEMINI_API_KEY and GEMINI_API_KEY not in ("", "YOUR_API_KEY"):
                result = _stage_gemini(image_bytes, prompt, config)
            else:
                raise RuntimeError(f"OpenAI: {e}") from e
    elif GEMINI_API_KEY and GEMINI_API_KEY not in ("", "YOUR_API_KEY"):
        result = _stage_gemini(image_bytes, prompt, config)
    else:
        raise ValueError("Укажи OPENAI_API_KEY или GEMINI_API_KEY в .env")

    if output_path:
        result.save(output_path)
    return result


def stage_replace(image_path: str, old_item: str, new_item: str, output_path: Optional[str] = None, config: Optional[StagingConfig] = None) -> Image.Image:
    """Замена мебели."""
    prompt = PROMPTS["replace"].format(old=old_item, new=new_item)
    return virtual_stage(image_path, prompt, output_path, config)


def stage_add(image_path: str, item: str, output_path: Optional[str] = None, config: Optional[StagingConfig] = None) -> Image.Image:
    """Добавление мебели."""
    prompt = PROMPTS["add"].format(item=item)
    return virtual_stage(image_path, prompt, output_path, config)


def stage_remove(image_path: str, item: str, output_path: Optional[str] = None, config: Optional[StagingConfig] = None) -> Image.Image:
    """Удаление мебели."""
    prompt = PROMPTS["remove"].format(item=item)
    return virtual_stage(image_path, prompt, output_path, config)


# Алиасы для обратной совместимости
stage_add_furniture = stage_add
stage_replace_furniture = stage_replace


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Виртуальный стейджинг с гиперпараметрами")
    parser.add_argument("image", help="Путь к фото")
    parser.add_argument("prompt", help='Промпт, напр. "Replace old sofa with modern gray sofa"')
    parser.add_argument("output", nargs="?", default="staged.jpg", help="Выходной файл")
    parser.add_argument("--input_fidelity", choices=["low", "high"], default="low",
                        help="low=сильнее изменения, high=сохранить детали")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="high")
    parser.add_argument("--size", choices=["auto", "1024x1024", "1536x1024", "1024x1536"], default="auto")
    args = parser.parse_args()
    config = StagingConfig(
        input_fidelity=args.input_fidelity,
        quality=args.quality,
        size=args.size,
    )
    virtual_stage(args.image, args.prompt, args.output, config=config)
    print(f"Saved: {args.output}")
