"""Запуск веб-сервера: uvicorn api_server:app --reload --host 0.0.0.0 --port 8000"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
