# Stage I — Тесты, CI/CD и деплой PFM

Документ фиксирует актуальную эксплуатационную конфигурацию Personal Finance Manager (PFM):
- unit/e2e тесты в `tests/`,
- CI в GitHub Actions,
- production-ready рекомендации по деплою Streamlit-приложения,
- Stage H возможности экспорта (CSV/XLSX/PDF) и sync API,
- связь с требованиями безопасности Stage G.

## 1) Текущее состояние проекта

Актуальные ключевые артефакты:
- UI: `app.py` (Streamlit)
- Импорт/парсинг: `io_utils.py`
- Категоризация: `categorizer.py`
- Аналитика: `analytics.py`
- Аномалии/антифрод: `anomaly.py`
- Инсайты: `insights.py`
- Безопасное хранение: `secure_store.py`
- Аутентификация: `auth.py`
- Экспорт: `export_utils.py`
- Sync API контракт/обработчики: `sync_api.py`
- Тесты: `tests/`
- CI: `.github/workflows/ci.yml`

## 2) Локальная проверка перед деплоем

Для нового окружения сначала обязательно установить зависимости:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Запуск тестов (основной путь проекта):

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

> Примечание: CI использует тот же подход через `unittest discover`, поэтому локальная проверка воспроизводит pipeline.

## 3) CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml`

Запускается:
- при `push` в `main`/`master`,
- при `pull_request`.

Фактические шаги pipeline:
1. Checkout репозитория.
2. Настройка Python 3.13.
3. Установка зависимостей из `requirements.txt`.
4. Запуск `python -m unittest discover -s tests -p "test_*.py" -v`.

Результат: единая проверка unit + e2e тестов импортов/категоризации/аналитики/экспорта/sync/security.

## 4) Рекомендуемый деплой: Streamlit Community Cloud

Почему это основной путь:
- нативный runtime для `app.py`,
- минимальная операционная сложность,
- быстрый rollout/rollback через Git.

Шаги:
1. Запушить актуальный код в GitHub.
2. В Streamlit Community Cloud создать приложение из репозитория.
3. Указать:
   - **Main file path**: `app.py`
   - **Python version**: 3.13 (или ближайшую доступную в платформе)
4. Настроить секреты/чувствительные настройки через secrets manager платформы.
5. Выполнить deploy и пройти smoke checklist (раздел 9).

Обязательные замечания:
- не хранить секреты в репозитории,
- использовать только HTTPS-доступ,
- хранение пользовательских данных выполнять только в зашифрованном виде (реализовано в коде Stage G/H).

## 5) Альтернативные варианты деплоя

### 5.1 VM (Windows/Linux)

Подходит для полного контроля инфраструктуры.

Минимальный запуск:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Рекомендации для production:
- reverse proxy (Nginx/Caddy/Traefik) + TLS,
- firewall и ограничение входящих портов,
- бэкапы `models/` и проверка восстановления,
- ограничение прав доступа к файловой системе на `models/`.

### 5.2 Heroku

Возможен контейнерный/Buildpack деплой со стартом Streamlit web-процесса:

```bash
streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
```

> Реализация зависит от выбранного стека Heroku и runtime ограничений.

### 5.3 Vercel

Vercel ориентирован на frontend/serverless. Для постоянного Streamlit-процесса практичнее Streamlit Cloud или VM. Использование Vercel требует дополнительной архитектурной адаптации.

## 6) Stage H: экспорт (CSV/XLSX/PDF) — эксплуатационные требования

Реализация: `export_utils.py`

Используется единый контракт:
- `ExportResult.artifacts`
- `ExportResult.warnings`
- `ExportResult.errors`
- `ExportResult.metadata`

Операционные особенности:
- детерминированные имена файлов через slug (`report_slug`),
- для CSV создаётся отдельный файл на таблицу: `<report_slug>__<table_slug>.csv`,
- для XLSX создаётся единый файл `<report_slug>.xlsx` с листами по таблицам,
- для PDF создаётся `<report_slug>.pdf` с текстовым summary/preview,
- форматирование выполняется без сайд-эффектов для исходных DataFrame.

Что проверить после деплоя:
- экспорт нескольких таблиц одновременно,
- корректная обработка пустых/некорректных таблиц (warnings/errors),
- корректные MIME-типы и бинарная выдача файлов.

## 7) Stage H: sync API — эксплуатационные требования

Реализация: `sync_api.py`

Ключевые свойства контракта:
- версионирование схемы: `SYNC_SCHEMA_VERSION = 1`,
- аутентификация обязательна (email/password + проверка `user_id`),
- идемпотентный upsert в push по ключу `(user_id, device_id, client_revision)`,
- шифрование payload в состоянии синхронизации: AES-256-GCM,
- детерминированные validation errors для тестируемости.

Хранилище sync состояния:
- файл: `models/sync_state.json`,
- в записи сохраняются зашифрованные данные (`nonce_b64`, `ciphertext_b64`) и `payload_hash`.

Минимальный контракт запросов:

### Push
Обязательные поля:
- `schema_version` (должен быть `1`),
- `user_id`,
- `device_id`,
- `client_revision` (целое `>= 0`),
- `payload`.

### Pull
Обязательные поля:
- `schema_version` (должен быть `1`),
- `user_id`,
- `since_revision` (целое `>= -1`).

Ответы:
- success/failure через `SyncApiResult` (`status_code`, `body`, `errors`),
- для pull возвращаются только записи пользователя с `client_revision > since_revision`.

## 8) OAuth/Open Banking

OAuth/Open Banking остаются опциональным будущим расширением и не являются обязательными для текущего production-деплоя Stage H.

## 9) Обязательный smoke checklist после деплоя

1. Приложение открывается без ошибок.
2. Импорт CSV/XLSX выполняется стабильно.
3. Категоризация и аналитика работают на фильтрованном датасете.
4. Экспорт CSV/XLSX/PDF работает и формирует ожидаемые артефакты.
5. Sync push/pull проходит базовый multi-device сценарий.
6. Авторизация и безопасное хранение данных работают корректно.
7. UI локализация RU (по умолчанию) и EN переключается без пропусков.

## 10) Связанные документы

- Безопасность и приватность: `deployment/security_and_privacy.md`
- Зависимости runtime: `requirements.txt`
- CI workflow: `.github/workflows/ci.yml`
