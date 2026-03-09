"""
Задание 1: AI-Scoring — Оценка квартиры по фото с помощью Vision-Language моделей.
Использует Gemini API для анализа состояния помещения и выдачи структурированного JSON.
"""
import json
from io import BytesIO
from pathlib import Path
from typing import Union

from PIL import Image

from config import GEMINI_API_KEY
from gemini_client import get_vision_json

# Системный промпт: роль опытного оценщика недвижимости
SYSTEM_PROMPT = """Ты — опытный оценщик недвижимости и риелтор с 15-летним стажем. 
Твоя задача — объективно оценить состояние помещения на фотографии по визуальным критериям.

Критерии оценки (шкала 1–10):

1. **cleanliness** (Чистота и порядок): 
   - 1 = Сильный беспорядок, грязь, мусор
   - 10 = Идеальная чистота, как в отеле

2. **repair_condition** (Состояние ремонта):
   - 1 = Требует капитального ремонта
   - 10 = Свежий евроремонт отличного качества

3. **modernity** (Актуальность дизайна):
   - 1 = Устаревший «бабушкин» ремонт, старая мебель
   - 10 = Современный стильный дизайн (лофт, минимализм, сканди)

4. **lighting** (Освещённость):
   - 1 = Темное, мрачное помещение
   - 10 = Светлая комната с большими окнами и хорошим светом

5. **clutter** (Захламлённость):
   - 1 = Много лишних личных вещей
   - 10 = Пространство свободно, минимум предметов

Оцени каждый критерий объективно. Ответь СТРОГО в формате JSON без дополнительного текста.

Формат ответа:
{
  "cleanliness": <число 1-10>,
  "repair_condition": <число 1-10>,
  "modernity": <число 1-10>,
  "lighting": <число 1-10>,
  "clutter": <число 1-10>,
  "overall_score": <среднее арифметическое>,
  "summary": "<краткое описание 1-2 предложения>"
}"""

USER_PROMPT = """Проанализируй эту фотографию комнаты/квартиры и выстави оценки по всем критериям. 
Верни результат только в формате JSON."""


def load_image(image_input: Union[str, Path, Image.Image]) -> Image.Image:
    """Загружает изображение из пути или возвращает PIL Image."""
    if isinstance(image_input, Image.Image):
        return image_input
    path = Path(image_input)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    return Image.open(path).convert("RGB")


def score_apartment(
    image_input: Union[str, Path, Image.Image],
    api_key: str = None,
) -> dict:
    """
    Оценивает квартиру по фото с помощью Gemini Vision.
    
    Args:
        image_input: Путь к изображению или PIL Image
        api_key: API ключ Gemini (если None — берётся из config)
    
    Returns:
        dict с оценками и summary
    """
    api_key = api_key or GEMINI_API_KEY
    if not api_key or api_key == "YOUR_API_KEY":
        raise ValueError("Set GEMINI_API_KEY in .env or pass api_key argument")

    image = load_image(image_input)
    buf = BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    full_prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"

    text = get_vision_json(api_key, image_bytes, full_prompt)
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    
    return json.loads(text)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ai_scoring.py <path_to_room_photo>")
        sys.exit(1)
    
    result = score_apartment(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
