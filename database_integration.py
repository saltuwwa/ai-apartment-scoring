"""
Задание 3: Интеграция с PostgreSQL — связь мебели с каталогом и расчёт стоимости.
Сопоставляет описание мебели с добавленной на этапе Virtual Staging с реальными ценами в БД.
"""
import json
from typing import Optional

from config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)


def get_connection_params() -> dict:
    """Возвращает параметры подключения к PostgreSQL."""
    return {
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
    }


def find_furniture_by_description(
    description: str,
    style_hint: Optional[str] = None,
    category_hint: Optional[str] = None,
) -> list[dict]:
    """
    Ищет мебель в каталоге по текстовому описанию (для сопоставления с результатом VL-модели).
    
    Использует полнотекстовый поиск по description, style, color, model_name.
    
    Args:
        description: Описание мебели ("минималистичный серый диван", "желтый сканди диван")
        style_hint: Подсказка стиля (Scandi, Modern, Classic)
        category_hint: Подсказка категории (Диван, Стол, Стул)
    
    Returns:
        Список совпадений из furniture_catalog
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor

    params = get_connection_params()
    if not params["password"]:
        raise ValueError(
            "PostgreSQL not configured. Set POSTGRES_* in .env. "
            "Run: createdb real_estate && psql -d real_estate -f init_furniture_db.sql"
        )

    conn = psycopg2.connect(**params)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Поиск по ключевым словам в description, style, model_name, color
            words = [w.strip().lower() for w in description.split() if len(w.strip()) > 2]
            conditions = []
            args = []

            for word in words:
                pattern = f"%{word}%"
                conditions.append(
                    "(LOWER(description) LIKE %s OR LOWER(style) LIKE %s "
                    "OR LOWER(model_name) LIKE %s OR LOWER(color) LIKE %s)"
                )
                args.extend([pattern] * 4)

            where_clause = " OR ".join(conditions) if conditions else "TRUE"
            if style_hint:
                where_clause += " AND LOWER(style) LIKE %s"
                args.append(f"%{style_hint.lower()}%")
            if category_hint:
                where_clause += " AND LOWER(category) LIKE %s"
                args.append(f"%{category_hint.lower()}%")

            query = f"""
                SELECT id, category, subcategory, model_name, style, color,
                       price_kzt, description, brand
                FROM furniture_catalog
                WHERE {where_clause}
                ORDER BY price_kzt ASC
                LIMIT 5
            """
            cur.execute(query, args)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def estimate_staging_cost(
    furniture_descriptions: list[str],
    style_hint: Optional[str] = None,
) -> tuple[list[dict], float]:
    """
    Оценивает стоимость добавленной мебели.
    
    Args:
        furniture_descriptions: Список описаний ("серый сканди диван", "белый журнальный столик")
        style_hint: Общий стиль (Scandi, Modern)
    
    Returns:
        (список найденных позиций, общая стоимость в тенге)
    """
    total_cost = 0.0
    matches = []

    for desc in furniture_descriptions:
        items = find_furniture_by_description(desc, style_hint=style_hint)
        if items:
            best = items[0]
            matches.append(best)
            total_cost += float(best["price_kzt"])
        else:
            matches.append({"model_name": desc, "price_kzt": None, "found": False})

    return matches, total_cost


def generate_report(
    score_before: dict,
    score_after: dict,
    added_furniture: list[str],
    matches: list[dict],
    total_cost_kzt: float,
) -> str:
    """
    Формирует итоговый отчёт по результатам пайплайна.
    
    Пример:
    "Квартира преобразилась! Оценка дизайна выросла с 4 до 8. 
     Добавленная мебель: Серый Диван (Сканди). Примерная стоимость обновления: 150 000 тг."
    """
    modernity_before = score_before.get("modernity", 0)
    modernity_after = score_after.get("modernity", 0)
    overall_before = score_before.get("overall_score", 0)
    overall_after = score_after.get("overall_score", 0)

    lines = []
    lines.append("🏡 Итоговый отчёт: AI-оценка и виртуальный стейджинг")
    lines.append("=" * 50)
    lines.append(f"Оценка ДО виртуального стейджинга:")
    lines.append(f"  • Дизайн (modernity): {modernity_before}/10")
    lines.append(f"  • Общая оценка: {overall_before}/10")
    lines.append("")
    lines.append(f"Оценка ПОСЛЕ виртуального стейджинга:")
    lines.append(f"  • Дизайн (modernity): {modernity_after}/10")
    lines.append(f"  • Общая оценка: {overall_after}/10")
    lines.append("")

    if modernity_after > modernity_before or overall_after > overall_before:
        lines.append("✨ Квартира преобразилась!")
        lines.append(
            f"   Оценка дизайна выросла с {modernity_before} до {modernity_after}. "
            f"Общая оценка: с {overall_before} до {overall_after}."
        )
    else:
        lines.append("📷 Результаты виртуального стейджинга зафиксированы.")

    lines.append("")
    lines.append("🛋 Добавленная/заменённая мебель:")

    for i, desc in enumerate(added_furniture):
        if i < len(matches) and matches[i].get("price_kzt") is not None:
            m = matches[i]
            lines.append(
                f"  • {m.get('model_name', desc)} ({m.get('style', '')}) — "
                f"{float(m.get('price_kzt', 0)):,.0f} ₸"
            )
        else:
            lines.append(f"  • {desc} — (не найдено в каталоге)")

    lines.append("")
    lines.append(f"💰 Примерная стоимость обновления: {total_cost_kzt:,.0f} тг.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python database_integration.py <furniture_description>")
        print('Example: python database_integration.py "минималистичный серый диван"')
        sys.exit(1)

    desc = " ".join(sys.argv[1:])
    items = find_furniture_by_description(desc)
    print(json.dumps(items, ensure_ascii=False, indent=2))
