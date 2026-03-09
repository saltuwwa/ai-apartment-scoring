"""
Надёжный агент: AI-оценка и виртуальный стейджинг.
Retry, короткие промпты, быстрая оценка.
"""
import json
import time
from io import BytesIO
from pathlib import Path

from config import GEMINI_API_KEY
from gemini_client import get_vision_json
from PIL import Image


# Промпт с обоснованием по каждому критерию (для риелторов)
SCORE_PROMPT = """Ты — опытный риелтор-оценщик. Оцени комнату на фото по шкале 1-10.
Критерии: cleanliness (чистота), repair_condition (ремонт), modernity (дизайн), lighting (свет), clutter (захламлённость).
Для каждого критерия дай оценку (число 1-10) и краткое обоснование на русском (1-2 предложения).
Ответь ТОЛЬКО JSON без markdown:
{
  "cleanliness": N, "cleanliness_justification": "текст",
  "repair_condition": N, "repair_condition_justification": "текст",
  "modernity": N, "modernity_justification": "текст",
  "lighting": N, "lighting_justification": "текст",
  "clutter": N, "clutter_justification": "текст",
  "overall_score": N, "summary": "краткое резюме"
}"""


def _retry(fn, max_attempts=4, backoff=2):
    """Повтор при 429 / временных ошибках."""
    last_err = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource" in err_str:
                wait = backoff ** attempt
                time.sleep(wait)
                last_err = e
                continue
            raise
    raise last_err


def _load_image_bytes(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def score_room(image_path: str) -> dict:
    """
    Оценка комнаты по фото. 1 вызов API, ~10-30 сек.
    """
    api_key = GEMINI_API_KEY or ""
    if not api_key or api_key == "YOUR_API_KEY":
        raise ValueError("Укажи GEMINI_API_KEY в .env")

    image_bytes = _load_image_bytes(image_path)

    def _call():
        text = get_vision_json(api_key, image_bytes, SCORE_PROMPT)
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    result = _retry(_call)
    # Дополняем overall_score если нет
    scores = [result.get(k) for k in ["cleanliness", "repair_condition", "modernity", "lighting", "clutter"] if k in result]
    if "overall_score" not in result and scores:
        result["overall_score"] = round(sum(s for s in scores if isinstance(s, (int, float))) / len(scores), 1)
    return result


def run_quick(image_path: str) -> dict:
    """Быстрый режим: только оценка (1 API вызов)."""
    score = score_room(image_path)
    return {"score": score, "mode": "quick", "report": _format_report(score)}


def run_full(
    image_path: str,
    staging_prompt: str,
    output_path: str,
    staging_config=None,
    use_database: bool = False,
) -> dict:
    """
    Полный пайплайн: оценка → стейджинг → оценка → (опционально) поиск мебели в БД.
    При ошибке стейджинга возвращает хотя бы оценку.
    """
    from virtual_staging import StagingConfig, virtual_stage

    result = {"score_before": None, "score_after": None, "staged_image": None, "report": "", "mode": "full"}
    config = staging_config or StagingConfig()

    # 1. Оценка до
    result["score_before"] = score_room(image_path)

    # 2. Staging
    try:
        virtual_stage(image_path, staging_prompt, output_path, config=config)
        result["staged_image"] = output_path

        # 3. Оценка после
        result["score_after"] = score_room(output_path)

        # 4. Отчёт
        sb = result["score_before"]
        sa = result["score_after"]
        m_before = sb.get("modernity", 0)
        m_after = sa.get("modernity", 0)
        result["report"] = (
            f"Оценка до: {sb.get('overall_score', 0)}/10 (дизайн {m_before}/10)\n"
            f"Оценка после: {sa.get('overall_score', 0)}/10 (дизайн {m_after}/10)\n"
            f"Изменения: {staging_prompt}"
        )

        # 5. Поиск в БД (опционально)
        if use_database:
            try:
                from main_pipeline import extract_furniture_from_prompt
                from database_integration import estimate_staging_cost, get_connection_params
                params = get_connection_params()
                if params.get("password"):
                    furniture = extract_furniture_from_prompt(staging_prompt)
                    matches, total = estimate_staging_cost(furniture, style_hint="Scandi")
                    result["furniture_matches"] = matches
                    result["total_cost_kzt"] = total
            except Exception:
                result["furniture_matches"] = []
                result["total_cost_kzt"] = 0
    except Exception as e:
        result["report"] = f"Оценка до: {result['score_before'].get('overall_score', 0)}/10. Стейджинг не выполнен: {e}"
        result["error_staging"] = str(e)

    return result


def _format_report(score: dict) -> str:
    s = score.get("summary", "")
    o = score.get("overall_score", 0)
    return f"Оценка: {o}/10. {s}"
