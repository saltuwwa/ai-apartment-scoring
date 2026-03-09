# 🏡 AI-оценка и виртуальный стейджинг недвижимости

мультимодальные модели и интеграция с PostgreSQL.  
Пайплайн для риелторов: оценка квартиры по фото, виртуальный стейджинг, расчёт стоимости мебели из каталога.

---

## Оглавление

1. [Обзор проекта](#обзор-проекта)
2. [Архитектура: как всё работает под капотом](#архитектура-как-всё-работает-под-капотом)
3. [Роль FastAPI](#роль-fastapi)
4. [Структура файлов](#структура-файлов)
5. [Быстрый старт](#быстрый-старт)
6. [API endpoints](#api-endpoints)
7. [Развёртывание](#развёртывание)

---

## Обзор проекта

Проект состоит из трёх заданий:

| Задание | Название | Что делает |
|---------|----------|------------|
| **1** | AI-scoring | Vision-Language модель (Gemini) анализирует фото комнаты и выдаёт оценки по 5 критериям с обоснованиями |
| **2** | Virtual Staging | Модель редактирует фото: замена/добавление/удаление мебели (OpenAI GPT Image 1.5 или Gemini). Настраиваемые гиперпараметры |
| **3** | PostgreSQL | Каталог мебели с ценами. После стейджинга — подбор аналогов и примерная стоимость обновления |

---

## Архитектура: как всё работает под капотом

### Схема потока данных

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          БРАУЗЕР (static/index.html)                        │
│  Загрузка фото, выбор режима, ввод промпта, галочка "Рассчитать стоимость"  │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │ HTTP POST (FormData)
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI (api_server.py)                              │
│  Принимает запрос → сохраняет файл во temp → вызывает agent → возвращает   │
│  JSON с результатами (оценки, base64-картинка, стоимость мебели)            │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│  agent.py              │  │  virtual_staging.py   │  │ database_integration.py│
│  Оркестратор пайплайна │  │  Редактирование фото  │  │ Поиск мебели в БД     │
└───────────┬────────────┘  └───────────┬───────────┘  └───────────┬───────────┘
            │                          │                          │
            ▼                          ▼                          ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│  gemini_client.py     │  │  OpenAI API / Gemini  │  │  PostgreSQL           │
│  Vision → JSON        │  │  images.edit()        │  │  furniture_catalog    │
└───────────────────────┘  └───────────────────────┘  └───────────────────────┘
```

---

### Фмча 1: AI-оценка (под капотом)

1. **Пользователь** загружает фото комнаты и нажимает «Оценить».
2. **static/app.js** отправляет `POST /api/score` с файлом в `FormData`.
3. **api_server.py** сохраняет файл во временную папку, вызывает `agent.run_quick(path)`.
4. **agent.py** → `score_room()`: загружает изображение в bytes, вызывает `gemini_client.get_vision_json(api_key, image_bytes, SCORE_PROMPT)`.
5. **gemini_client.py**: создаёт `genai.Client`, отправляет изображение + промпт в Gemini (модели: gemini-2.5-flash, gemini-2.0-flash и т.д.), запрашивает `response_mime_type="application/json"`.
6. **Gemini API** возвращает JSON вида:
   ```json
   {"cleanliness": 8, "cleanliness_justification": "...", "repair_condition": 7, ...}
   ```
7. Цепочка возвращается наверх: agent → api_server → браузер отображает таблицу.

---

### Фича 2: Виртуальный стейджинг (под капотом)

1. **Пользователь** загружает фото, вводит промпт (напр. "Replace sofa with modern gray sofa"), настраивает гиперпараметры, нажимает «Запустить стейджинг».
2. **api_server.py** получает `POST /api/full-with-image` с полями: `file`, `prompt`, `input_fidelity`, `quality`, `size`, `use_db`.
3. **agent.run_full()** выполняет по шагам:
   - **Оценка ДО**: `score_room(image_path)` → Gemini, получает оценки.
   - **Стейджинг**: вызывает `virtual_staging.virtual_stage(image_path, prompt, output_path, config)`.
4. **virtual_staging.py**:
   - Загружает изображение, делает квадрат 1024×1024 (требование DALL-E / GPT Image).
   - Если есть `OPENAI_API_KEY` → `_stage_openai()`: `client.images.edit(image=..., prompt=..., input_fidelity=..., quality=..., size=...)`.
   - Иначе → `_stage_gemini()`: `gemini_client.get_image_edit()`.
   - Сохраняет результат в `output_path`.
5. **Оценка ПОСЛЕ**: снова `score_room(output_path)`.
6. **agent** возвращает: `score_before`, `score_after`, `report`, путь к staged-изображению.
7. **api_server** читает результат в base64, добавляет в JSON, отдаёт браузеру.
8. **Браузер** показывает «До» и «После» с оценками.

---

### Фича 3: PostgreSQL (под капотом)

1. Если галочка **«Рассчитать стоимость мебели»** включена, `agent.run_full(..., use_database=True)` после стейджинга вызывает логику БД.
2. **main_pipeline.extract_furniture_from_prompt(prompt)** извлекает описание мебели из промпта:
   - "Replace X with Y" → берётся часть после "with" (новая мебель).
   - "Add X" → часть после "Add".
3. **database_integration.estimate_staging_cost(furniture_descriptions)**:
   - Для каждого описания вызывает `find_furniture_by_description()`.
   - В `find_furniture_by_description()`: подключается к PostgreSQL через psycopg2, выполняет `SELECT` по `furniture_catalog` с `LIKE` по `description`, `style`, `model_name`, `color`.
   - Суммирует `price_kzt` по найденным позициям.
4. Результат (`furniture_matches`, `total_cost_kzt`) добавляется в ответ API и показывается пользователю.

---

## Роль FastAPI

**FastAPI** — это веб-фреймворк (бэкенд), который:

1. **Принимает HTTP-запросы** от браузера (фото, промпт, параметры).
2. **Маршрутизирует** их по endpoint'ам: `/`, `/api/score`, `/api/full-with-image`, `/api/db-status`, `/api/model-info`.
3. **Валидирует** входные данные (тип файла, обязательные поля).
4. **Вызывает** бизнес-логику (agent, virtual_staging, database_integration).
5. **Возвращает** JSON с результатами и раздаёт статику (HTML, CSS, JS).
6. **Обрабатывает ошибки** (400, 500) с понятными сообщениями.

Без FastAPI пришлось бы писать свой HTTP-сервер вручную. FastAPI даёт асинхронность, автодокументацию (`/docs`), типобезопасность.

---

## Структура файлов

```
image gen/
├── api_server.py          # FastAPI: роуты, вызов agent, раздача static
├── run_server.py          # Запуск: uvicorn api_server:app
├── agent.py               # Оркестратор: score_room, run_full, retry
├── ai_scoring.py          # Задание 1: детальный промпт (опционально)
├── virtual_staging.py     # Задание 2: StagingConfig, OpenAI/Gemini edit
├── gemini_client.py       # Клиент Gemini: get_vision_json, get_image_edit
├── database_integration.py# Задание 3: PostgreSQL, find_furniture, estimate_cost
├── main_pipeline.py       # extract_furniture_from_prompt, полный CLI-пайплайн
├── config.py              # Загрузка .env, переменные окружения
├── init_furniture_db.sql   # DDL + данные для furniture_catalog
├── static/
│   ├── index.html         # HTML: форма, табы, результаты
│   ├── style.css          # Стили
│   └── app.js             # Логика: fetch API, отрисовка результатов
├── requirements.txt
├── .env.example            # Шаблон .env (без секретов)
├── .gitignore
├── Dockerfile
├── DEPLOY.md               # Инструкции по развёртыванию
├── virtual_staging_experiments.ipynb  # Эксперименты с гиперпараметрами
└── ai_scoring.ipynb        # Демо AI-оценки
```

---

## Быстрый старт

### 1. Установка

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # затем заполни ключи в .env
```

### 2. Переменные окружения (.env)

| Переменная | Описание |
|------------|----------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) — для оценки и fallback стейджинга |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/) — для GPT Image 1.5 (стейджинг) |
| `POSTGRES_*` | Для задания 3: host, port, db, user, password |

### 3. PostgreSQL (задание 3)

```bash
createdb real_estate
psql -d real_estate -f init_furniture_db.sql
```

Или через pgAdmin: создать БД `real_estate`, в Query Tool выполнить содержимое `init_furniture_db.sql`.

### 4. Запуск

```bash
python run_server.py
```

Открой http://localhost:8000

---

## API endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/` | Главная страница (index.html) |
| GET | `/api/model-info` | Информация о модели (Gemini) |
| GET | `/api/db-status` | Проверка подключения к PostgreSQL |
| POST | `/api/score` | Задание 1: оценка по фото |
| POST | `/api/full-with-image` | Задания 2+3: стейджинг + опционально расчёт стоимости |
| GET | `/health` | Health check |

---

## Подготовка к Git push

1. **Проверь `.gitignore`** — `.env` и `venv/` не должны попасть в репозиторий.
2. **Создай `.env` из шаблона:**  
   `cp .env.example .env` (и заполни ключи локально).
3. **Команды для первого push:**
   ```bash
   git add .
   git status    # убедись, что .env и venv не в списке
   git commit -m "Initial: AI-оценка, стейджинг, PostgreSQL"
   git remote add origin <URL_твоего_репо>
   git push -u origin main
   ```

---

## Развёртывание

См. [DEPLOY.md](DEPLOY.md) — локальный запуск, Docker, облако (Railway, Render, Neon для БД).

---

## Гиперпараметры стейджинга

| Параметр | Значения | Влияние |
|----------|----------|---------|
| `input_fidelity` | low, high | low — сильнее изменения; high — сохранить детали |
| `quality` | low, medium, high, auto | Качество результата |
| `size` | auto, 1024x1024, 1536x1024, 1024x1536 | Размер выходного изображения |

Из командной строки:
```bash
python virtual_staging.py room.jpg "Replace sofa with gray sofa" out.jpg --input_fidelity high --quality medium
```

---

## Модели

- **AI-оценка:** Gemini 2.5 Flash / 2.0 Flash (Vision-Language)
- **Стейджинг:** OpenAI GPT Image 1.5 (или Gemini Image Gen)
- **БД:** PostgreSQL, таблица `furniture_catalog`
