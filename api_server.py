"""
API-сервер для модуля оценки недвижимости.
Задания 1–3: AI-оценка, виртуальный стейджинг с гиперпараметрами, PostgreSQL.
"""
import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from agent import run_quick, run_full
from virtual_staging import StagingConfig

app = FastAPI(title="Оценка недвижимости для риелторов", version="2.0")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Кто оценивает (Vision-Language модель)
MODEL_INFO = {"name": "Gemini 2.5 Flash", "type": "Vision-Language (VL) модель", "provider": "Google AI"}


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/api/model-info")
def model_info():
    """Информация о модели, которая выполняет оценку."""
    return MODEL_INFO


@app.get("/api/db-status")
def db_status():
    """Проверка подключения к PostgreSQL (Задание 3)."""
    try:
        from database_integration import get_connection_params
        params = get_connection_params()
        if not params.get("password"):
            return {"ok": False, "message": "PostgreSQL не настроен. Добавьте POSTGRES_* в .env"}
        import psycopg2
        conn = psycopg2.connect(**params)
        conn.close()
        return {"ok": True, "message": "Подключение успешно"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/score")
async def score_photo(file: UploadFile = File(...)):
    """
    Задание 1: AI-оценка квартиры по фото.
    Vision-Language модель (Gemini) анализирует фото и возвращает оценки с обоснованиями.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Нужно изображение (jpg, png)")
    ext = Path(file.filename or "img").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
        f.write(await file.read())
        path = f.name
    try:
        r = run_quick(path)
        return {
            "score": r["score"],
            "report": r["report"],
            "overall": r["score"].get("overall_score", 0),
            "model_info": MODEL_INFO,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        Path(path).unlink(missing_ok=True)


@app.post("/api/full-with-image")
async def full_pipeline_with_image(
    file: UploadFile = File(...),
    prompt: str = Form("Replace the old sofa with a modern gray scandinavian sofa"),
    input_fidelity: str = Form("low"),
    quality: str = Form("high"),
    size: str = Form("auto"),
    use_db: str = Form("false"),
):
    """
    Задания 2+3: Полный пайплайн с гиперпараметрами стейджинга.
    - input_fidelity: low / high (сила изменений)
    - quality: low / medium / high / auto
    - size: auto / 1024x1024 / 1536x1024 / 1024x1536
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Нужно изображение (jpg, png)")
    ext = Path(file.filename or "img").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
        f.write(await file.read())
        path = f.name
    out_path = tempfile.mktemp(suffix=".jpg")
    config = StagingConfig(
        input_fidelity=input_fidelity or "low",
        quality=quality or "high",
        size=size or "auto",
    )
    use_database = str(use_db).lower() in ("true", "1", "on")
    try:
        r = run_full(path, prompt or "", out_path, staging_config=config, use_database=use_database)
        staged_b64 = None
        if Path(out_path).exists():
            with open(out_path, "rb") as f:
                staged_b64 = base64.b64encode(f.read()).decode()
            Path(out_path).unlink(missing_ok=True)
        result = {
            "score_before": r["score_before"],
            "score_after": r.get("score_after"),
            "report": r["report"],
            "overall_before": r["score_before"].get("overall_score", 0),
            "overall_after": r.get("score_after", {}).get("overall_score", 0) if r.get("score_after") else None,
            "staged_image_base64": staged_b64,
            "error_staging": r.get("error_staging"),
            "model_info": MODEL_INFO,
        }
        if r.get("furniture_matches") is not None:
            result["furniture_matches"] = r["furniture_matches"]
            result["total_cost_kzt"] = r.get("total_cost_kzt", 0)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        Path(path).unlink(missing_ok=True)


@app.get("/health")
def health():
    return {"ok": True}
