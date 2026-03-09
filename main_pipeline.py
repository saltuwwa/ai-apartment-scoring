"""
Основной пайплайн: AI-оценка + Виртуальный стейджинг + Расчёт стоимости.
Объединяет все три модуля в единый сценарий.
"""
import json
import sys
from pathlib import Path

from ai_scoring import score_apartment
from virtual_staging import StagingConfig, virtual_stage
from database_integration import (
    estimate_staging_cost,
    generate_report,
    get_connection_params,
)


def run_full_pipeline(
    image_path: str,
    staging_prompt: str,
    output_image_path: str = "staged_result.jpg",
    use_database: bool = True,
) -> dict:
    """
    Запускает полный пайплайн:
    1. AI-оценка исходного фото
    2. Виртуальный стейджинг (редактирование)
    3. AI-оценка результата
    4. Поиск мебели в БД и расчёт стоимости
    5. Итоговый отчёт
    
    Args:
        image_path: Путь к исходному фото
        staging_prompt: Описание изменений (на английском)
                       Пример: "Replace the old sofa with a modern yellow scandinavian sofa"
        output_image_path: Путь для сохранения результата
        use_database: Подключаться ли к PostgreSQL для расчёта стоимости
    
    Returns:
        dict с полными результатами
    """
    results = {"score_before": None, "score_after": None, "staged_image": None}

    # 1. AI-Scoring ДО
    print("📊 Этап 1: AI-оценка исходного фото...")
    results["score_before"] = score_apartment(image_path)
    print(json.dumps(results["score_before"], ensure_ascii=False, indent=2))

    # 2. Virtual Staging
    print("\n🎨 Этап 2: Виртуальный стейджинг...")
    staged = virtual_stage(image_path, staging_prompt, output_image_path)
    results["staged_image"] = output_image_path
    print(f"   Сохранено: {output_image_path}")

    # 3. AI-Scoring ПОСЛЕ
    print("\n📊 Этап 3: AI-оценка после стейджинга...")
    results["score_after"] = score_apartment(output_image_path)
    print(json.dumps(results["score_after"], ensure_ascii=False, indent=2))

    # 4. Описание добавленной мебели: из промпта или через VL-анализ до/после
    furniture_descriptions = extract_furniture_from_prompt(staging_prompt)
    # Опционально: VL-модель анализирует до/после и возвращает список мебели
    furniture_descriptions = extract_furniture_via_vision(
        image_path, output_image_path, furniture_descriptions
    )
    results["added_furniture"] = furniture_descriptions

    # 5. Поиск в БД и расчёт стоимости
    if use_database:
        try:
            params = get_connection_params()
            if params.get("password"):
                print("\n🗄 Этап 4: Поиск мебели в каталоге...")
                matches, total_cost = estimate_staging_cost(
                    furniture_descriptions,
                    style_hint="Scandi",  # можно извлечь из промпта
                )
                results["furniture_matches"] = matches
                results["total_cost_kzt"] = total_cost
                report = generate_report(
                    results["score_before"],
                    results["score_after"],
                    furniture_descriptions,
                    matches,
                    total_cost,
                )
            else:
                report = generate_report(
                    results["score_before"],
                    results["score_after"],
                    furniture_descriptions,
                    [],
                    0,
                )
        except Exception as e:
            print(f"\n⚠ База данных недоступна: {e}")
            report = generate_report(
                results["score_before"],
                results["score_after"],
                furniture_descriptions,
                [],
                0,
            )
    else:
        report = generate_report(
            results["score_before"],
            results["score_after"],
            furniture_descriptions,
            [],
            0,
        )

    results["report"] = report
    print("\n" + report)
    return results


def extract_furniture_via_vision(
    before_path: str,
    after_path: str,
    fallback: list[str],
) -> list[str]:
    """
    Использует VL-модель для описания добавленной/заменённой мебели (до/после).
    При ошибке возвращает fallback (из промпта).
    """
    try:
        from config import GEMINI_API_KEY
        from gemini_client import get_vision_compare

        if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY":
            return fallback

        ext = Path(before_path).suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(before_path, "rb") as f:
            before_bytes = f.read()
        with open(after_path, "rb") as f:
            after_bytes = f.read()

        prompt = """Compare these two room photos (BEFORE and AFTER virtual staging).
List ONLY the furniture items that were ADDED or REPLACED. One short description per line, in Russian or English.
Example: minimalistic gray scandinavian sofa
If nothing changed, reply: none"""

        text = get_vision_compare(
            GEMINI_API_KEY, before_bytes, after_bytes, prompt, mime
        ).strip().lower()
        if "none" in text or not text:
            return fallback
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("-")]
        return lines[:5] if lines else fallback
    except Exception:
        return fallback


def extract_furniture_from_prompt(prompt: str) -> list[str]:
    """
    Извлекает описание мебели из промпта стейджинга.
    Упрощённая эвристика: ищем "Replace X with Y" или "Add X".
    В продакшене лучше использовать VL-модель для анализа фото.
    """
    prompt_lower = prompt.lower()
    descriptions = []

    if "replace" in prompt_lower and " with " in prompt_lower:
        # "Replace the old sofa with a modern yellow scandinavian sofa"
        try:
            parts = prompt.split(" with ", 1)
            if len(parts) == 2:
                new_item = parts[1].strip().rstrip(".")
                descriptions.append(new_item)
        except Exception:
            pass

    if "add" in prompt_lower:
        # "Add a modern gray scandinavian sofa"
        try:
            idx = prompt_lower.find("add ")
            rest = prompt[idx + 4 :].strip()
            if "add to" in prompt_lower:
                rest = rest.split("add to")[0].strip()
            if rest:
                descriptions.append(rest.rstrip("."))
        except Exception:
            pass

    if not descriptions:
        descriptions.append(prompt[:80])

    return descriptions


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python main_pipeline.py <image_path> <staging_prompt> [output_path]")
        print()
        print("Example:")
        print('  python main_pipeline.py room.jpg "Replace the old sofa with a modern yellow scandinavian sofa" staged.jpg')
        sys.exit(1)

    image_path = sys.argv[1]
    staging_prompt = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "staged_result.jpg"

    if not Path(image_path).exists():
        print(f"Error: Image not found: {image_path}")
        sys.exit(1)

    run_full_pipeline(image_path, staging_prompt, output_path)
