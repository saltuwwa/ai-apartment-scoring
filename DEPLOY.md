# Развёртывание — Задание 3

## Локальный запуск

```bash
# 1. Создать venv
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Настроить .env (GEMINI_API_KEY, OPENAI_API_KEY)
# 4. Запустить
python run_server.py
```

Сайт: http://localhost:8000

---

## PostgreSQL (каталог мебели)

### Локально

```bash
# Установить PostgreSQL, затем:
createdb real_estate
psql -d real_estate -f init_furniture_db.sql
```

В `.env`:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=real_estate
POSTGRES_USER=postgres
POSTGRES_PASSWORD=ваш_пароль
```

### Облачные БД (бесплатные тарифы)

- **Neon** (https://neon.tech) — PostgreSQL как сервис
- **Supabase** (https://supabase.com) — PostgreSQL + хостинг
- **Railway** (https://railway.app) — PostgreSQL в одном клике

После создания БД скопируйте строку подключения и задайте переменные в .env.

---

## Облачное развёртывание приложения

### Docker

```bash
docker build -t realestate-app .
docker run -p 8000:8000 --env-file .env realestate-app
```

### Railway

1. Подключите GitHub-репозиторий
2. Добавьте переменные: GEMINI_API_KEY, OPENAI_API_KEY
3. Опционально: создайте PostgreSQL-добавку и привяжите
4. Деплой автоматически по push

### Render

1. New → Web Service, подключите репо
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
4. Environment: добавьте GEMINI_API_KEY, OPENAI_API_KEY

### Fly.io

```bash
fly launch
fly secrets set GEMINI_API_KEY=... OPENAI_API_KEY=...
fly deploy
```
