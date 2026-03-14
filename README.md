# Personal Finance Manager (PFM)

## 1. О проекте

**Personal Finance Manager (PFM)** — веб-приложение на **Streamlit** для анализа банковских транзакций.

Цель проекта:

- загружать банковские операции из CSV/XLSX;
- нормализовать и очищать данные;
- автоматически категоризировать транзакции;
- строить понятную финансовую аналитику;
- выявлять аномальные операции;
- формировать инсайты и рекомендации;
- экспортировать отчёты (CSV/XLSX/PDF);
- поддерживать безопасное хранение и синхронизацию между устройствами.

Проект реализует MVP-архитектуру с акцентом на:

- **детерминированность** (воспроизводимые результаты);
- **точность денег** (minor units + Decimal, без float-арифметики в расчётах);
- **безопасность** (AES-GCM, PBKDF2, идемпотентные API-контракты);
- **локализацию** (полная RU/EN i18n через ключи).

---

## 2. Основные возможности

1. **Импорт транзакций**: CSV/XLS/XLSX/XLSM, автоопределение кодировки/разделителя, алиасы колонок EN/RU.
2. **Нормализация**:
   - суммы в `minor units` (копейки/центы);
   - генерация `transaction_id`, если отсутствует;
   - валидация обязательных полей.
3. **Категоризация**:
   - встроенные правила + пользовательские правила;
   - поддержка транслитерации RU/LAT.
4. **Аналитика**:
   - расходы по категориям;
   - месячный тренд;
   - сравнение периодов;
   - топ мерчантов;
   - recurring-платежи;
   - контроль бюджетов.
5. **Мультивалютность**:
   - ручные курсы;
   - конвертация в базовую валюту;
   - consolidated view с покрытием конвертации.
6. **Антифрод (MVP)**:
   - rule-based флаги: high amount, rare merchant, country switch;
   - ручной feedback (ok/fraud) с upsert.
7. **Инсайты**:
   - подписки;
   - рост категорий MoM;
   - рекомендация по накоплениям.
8. **Безопасность и аккаунты**:
   - email/password auth;
   - PBKDF2-хеширование;
   - AES-GCM шифрование пользовательских транзакций.
9. **Экспорт и интеграции**:
   - CSV/XLSX/PDF;
   - унифицированный экспортный контракт.
10. **Sync API**:
  - versioned schema;
  - authenticated push/pull;
  - encrypted payload at-rest;
  - идемпотентность по `(user_id, device_id, client_revision)`.

---

## 3. Технологии и зависимости

- Python 3.13+
- Streamlit
- Pandas
- Altair
- openpyxl
- cryptography

`requirements.txt`:

- `altair`
- `pandas>=2.2,<3.0`
- `streamlit>=1.36,<2.0`
- `cryptography>=46.0.5,<47.0`
- `openpyxl>=3.1,<4.0`

---

## 4. Быстрый старт

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

После запуска:

1. Зарегистрируйтесь/войдите.
2. При необходимости включите consent на хранение PII.
3. Загрузите CSV/XLSX.
4. Просмотрите категоризацию, аналитику, аномалии, инсайты.
5. Скачайте экспортные артефакты.
---
## Формат файла транзакций

Приложение поддерживает импорт транзакций в **двух форматах суммы**:  
- `MAJOR` — стандартные денежные единицы (рубли с копейками)  
- `MINOR` — минимальные единицы валюты (копейки)

---

## Формат MAJOR (рубли с копейками)

Используется, когда поле `amount` содержит значения вида:

- `-1299.00`
- `-12.99`

Пример файла:

```csv
date,amount,currency,merchant,description,account,transaction_id
2026-01-05,-1299.00,RUB,Netflix,Monthly subscription,Card ****1234,TXN-0001
2026-01-07,-459.50,RUB,Пятёрочка,Groceries,Card ****1234,TXN-0002
2026-01-10,85000.00,RUB,Employer,Salary,Main account,TXN-0003
2026-01-11,-1200.00,RUB,Яндекс Go,Taxi,Card ****1234,TXN-0004
```
## 2. Формат MINOR (сумма в копейках)

Используй этот формат, когда `amount` уже указан в **минимальных единицах валюты**.

Используется, когда поле `amount` содержит значения вида:
- `-129900`
- `-1299`
Пример файла:
```csv
date,amount,currency,merchant,description,account,transaction_id
2026-01-05,-129900,RUB,Netflix,Monthly subscription,Card ****1234,TXN-1001
2026-01-07,-45950,RUB,Пятёрочка,Groceries,Card ****1234,TXN-1002
2026-01-10,8500000,RUB,Employer,Salary,Main account,TXN-1003
2026-01-11,-120000,RUB,Яндекс Go,Taxi,Card ****1234,TXN-1004
```
---

## Минимальный обязательный формат

Минимально допустимый вариант:
```csv
date,amount
2026-01-05,-1299.00
```
Но **лучше всегда добавлять `currency`**, чтобы не было путаницы между форматами, например:

- `12.99`
- `1299 RUB`
---

## 5. Архитектура и поток данных

1. **UI (`app.py`)** принимает файл/команды пользователя.
2. **`io_utils.py`** импортирует и нормализует транзакции.
3. **`categorizer.py`** присваивает категории.
4. **`analytics.py`** строит агрегаты и мультивалютные представления.
5. **`anomaly.py`** размечает подозрительные операции.
6. **`insights.py`** генерирует actionable-сообщения.
7. **`secure_store.py`** шифрует/дешифрует данные пользователя.
8. **`export_utils.py`** формирует бинарные артефакты отчётов.
9. **`sync_api.py`** обрабатывает push/pull синхронизацию.
10. **`i18n.py`** предоставляет все UI/системные тексты по ключам.

---

## 6. Контракты данных

### 6.1 Import contract (`io_utils.ImportResult`)
- `dataframe: pd.DataFrame | None`
- `warnings: list[str]`
- `errors: list[str]`
- `metadata: dict[str, Any]`

### 6.2 Export contract (`export_utils.ExportResult`)
- `artifacts: list[ExportArtifact]`
- `warnings: list[str]`
- `errors: list[str]`
- `metadata: dict[str, Any]`

### 6.3 Sync API contract (`sync_api.SyncApiResult`)
- `success: bool`
- `status_code: int`
- `body: dict[str, Any]`

---

## 7. Безопасность

- Пароли не хранятся в открытом виде: **PBKDF2-HMAC-SHA256**.
- Для шифрования данных транзакций используется **AES-256-GCM**.
- Nonce генерируется через `os.urandom`.
- Для AES-GCM применяется `AAD` (доп.аутентифицированные данные).
- Sync payload хранится в зашифрованном виде.
- Поддержан явный consent на хранение PII и удаление аккаунта/данных.

---

## 8. Локализация

- Полная RU/EN локализация через `i18n.py`.
- Все пользовательские строки берутся по ключам `tr(key, lang, **kwargs)`.
- Язык по умолчанию: `ru`, переключается в UI.

---

## 9. Структура проекта

- `app.py` — Streamlit UI и orchestration.
- `io_utils.py` — импорт/парсинг/нормализация транзакций.
- `categorizer.py` — rule-based категоризация + user rules.
- `analytics.py` — агрегаторы и мультивалютная логика.
- `anomaly.py` — antifraud-правила и feedback-журнал.
- `insights.py` — генерация финансовых инсайтов.
- `auth.py` — email/password auth, consent, аккаунты.
- `secure_store.py` — AES-хранилище пользовательских транзакций.
- `export_utils.py` — экспорт CSV/XLSX/PDF.
- `sync_api.py` — sync API push/pull.
- `i18n.py` — словарь переводов и helper `tr`.
- `models/` — user data и state-файлы.
- `tests/` — unit/e2e тесты.
- `deployment/` — инструкции по CI/CD и безопасности.

---

## 10. Подробный справочник функций

Ниже — описание функций каждого модуля.

---

## 10.1 `io_utils.py` (импорт и нормализация)

### Dataclass

- `ImportResult` — унифицированный результат импорта.
- `ParsedAmount` — промежуточный результат парсинга суммы.

### Публичные функции

- `import_transactions(uploaded_file, default_currency="RUB", language="ru", amount_mode="auto") -> ImportResult`  
  Универсально импортирует CSV/XLSX, маппит колонки, нормализует дату/сумму/валюту, возвращает `ImportResult`.

### Внутренние функции

- `_read_uploaded_bytes(uploaded_file) -> bytes | None` — безопасно читает байты файла.
- `_read_dataframe(raw, filename) -> tuple[pd.DataFrame | None, dict, Exception | None]` — пытается прочитать Excel/CSV.
- `_detect_delimiter(text) -> str | None` — определяет разделитель (`; , \t |`).
- `_normalize_column_name(name) -> str` — нормализует имя колонки для alias matching.
- `_map_columns(df, language) -> tuple[pd.DataFrame, list[str]]` — приводит колонки к целевым именам (`date`, `amount`, ...).
- `_parse_amount_candidate(value, assume_major_for_plain_int) -> ParsedAmount` — парсит сумму с учётом форматов RF/EU/US.
- `_detect_plain_integer_mode(amount_series) -> bool` — автоопределяет интерпретацию целых сумм (major/minor).
- `_resolve_plain_int_mode(amount_series, amount_mode) -> tuple[bool, str]` — фиксирует режим интерпретации.
- `_normalize_currency(value, default_currency) -> str` — нормализует код валюты до ISO-like 3 букв.
- `_normalize_text(value) -> str` — безопасная нормализация текстового поля.
- `_normalize_date_series(date_series) -> pd.Series` — парсит даты (UTC + dayfirst fallback).
- `_normalize_amount_series(amount_series, amount_mode) -> tuple[pd.Series, str]` — нормализует суммы в minor.
- `_normalize_dataframe(...) -> tuple[pd.DataFrame, list[str], dict]` — финальная нормализация и метаданные.
- `_get_filename(uploaded_file) -> str` — извлекает имя файла.

---

## 10.2 `categorizer.py` (категоризация)

### Dataclass

- `CategoryRule` — правило категоризации (`pattern`, `category`, `field`, `match_type`, `direction`, `source`).

### Публичные функции

- `normalize_text(value) -> str` — нормализует строку для устойчивого match.
- `transliterate_ru_to_lat(text) -> str` — RU→LAT транслитерация.
- `transliterate_lat_to_ru(text) -> str` — LAT→RU приближённая транслитерация.
- `build_text_variants(text) -> set[str]` — формирует варианты строки для мультиязычного сравнения.
- `load_user_rules(rules_path=...) -> list[CategoryRule]` — загружает user rules из JSON.
- `save_user_rule(pattern, category, field="both", match_type="contains", direction="any", rules_path=...) -> bool` — сохраняет правило с защитой от дубликатов.
- `categorize_transactions(dataframe, rules_path=...) -> tuple[pd.DataFrame, dict]` — применяет `user + builtin` правила, возвращает DataFrame с `category`, `category_source` и metadata.

### Внутренние функции

- `_build_builtin_rules() -> list[CategoryRule]` — формирует встроенные приоритетные правила.
- `_direction_matches(direction, amount) -> bool` — проверяет направление операции (income/expense/any).
- `_extract_text_by_field(field, merchant, description) -> str` — выбирает источник текста для match.
- `_rule_matches(rule, merchant, description, amount) -> bool` — проверяет совпадение транзакции с правилом.
- `_pick_category(merchant, description, amount, rules) -> tuple[str, str]` — выбирает первую подходящую категорию.

---

## 10.3 `analytics.py` (агрегаторы и FX)

### Dataclass

- `PeriodComparison` — результат сравнения двух периодов.
- `CurrencyConversionResult` — результат FX-конвертации.

### Публичные функции

- `parse_major_amount_to_minor(value) -> int` — перевод major→minor через Decimal.
- `minor_to_major(minor_value) -> float` — безопасный minor→major для UI.
- `convert_transactions_to_base_currency(dataframe, base_currency, rates_major_to_base, language="ru") -> CurrencyConversionResult`  
  Конвертирует `amount` в `amount_base` по контракту курса `1 source = X base`.
- `filter_transactions(dataframe, currency=ALL_FILTER_VALUE, account=ALL_FILTER_VALUE) -> pd.DataFrame` — общий фильтр по валюте/аккаунту.
- `aggregate_expenses_by_category(dataframe, amount_column="amount") -> pd.DataFrame` — расходы по категориям.
- `aggregate_monthly_expenses(dataframe, amount_column="amount") -> pd.DataFrame` — месячный тренд расходов.
- `compare_expenses_with_previous_period(dataframe, months=3, amount_column="amount") -> PeriodComparison` — сравнение текущего/предыдущего окна.
- `aggregate_top_merchants(dataframe, limit=10, amount_column="amount") -> pd.DataFrame` — топ мерчантов по расходам.
- `detect_recurring_expenses(dataframe, min_occurrences=3, min_interval_days=20, max_interval_days=40, amount_column="amount") -> pd.DataFrame`  
  Детерминированно ищет регулярные списания.
- `calculate_budget_usage(dataframe, budgets_minor, amount_column="amount") -> pd.DataFrame` — использование бюджета по категориям.

### Внутренние функции

- `_month_start_utc(series) -> pd.Series` — нормализует даты к началу месяца в UTC.
- `_ensure_required_columns(dataframe) -> pd.DataFrame` — гарантирует минимальный набор колонок.
- `_prepare_amount_column(prepared, amount_column) -> pd.DataFrame` — приводит выбранную amount-колонку к numeric.
- `_normalize_rates(base_currency, rates_major_to_base) -> tuple[dict[str, Decimal], list[str]]` — валидирует/нормализует курсы.

---

## 10.4 `anomaly.py` (MVP antifraud)

### Dataclass / Types

- `FeedbackVerdict = Literal["ok", "fraud"]`
- `AnomalyThresholds` — параметры rule-based детекции.
- `UserStats` — агрегированная статистика пользователя.
- `AnomalyDetectionResult` — результат детекции.

### Публичные функции

- `build_user_stats(dataframe, amount_column="amount") -> UserStats` — строит baseline-статистику по расходам.
- `detect_anomalies(dataframe, user_stats=None, thresholds=None, amount_column="amount") -> AnomalyDetectionResult`  
  Проставляет флаги `high_amount`, `rare_merchant`, `country_switch`.
- `load_anomaly_feedback(feedback_path=...) -> list[dict]` — читает журнал ручной валидации.
- `save_anomaly_feedback(transaction_id, verdict, feedback_path=..., reasons=None, comment="", context=None) -> bool`  
  Идемпотентно сохраняет feedback (upsert по `transaction_id`).
- `summarize_feedback(feedback_entries, transaction_ids=None) -> dict[str, int]` — строит компактную сводку feedback.

### Внутренние функции

- `_normalize_text(value) -> str` — нормализует текст.
- `_ensure_columns(dataframe) -> pd.DataFrame` — добавляет/очищает необходимые поля.
- `_prepare_amount_column(prepared, amount_column) -> pd.DataFrame` — нормализует amount-колонку.
- `_merchant_display(row) -> str` — вычисляет fallback-отображение мерчанта.
- `_safe_ratio(numerator, denominator) -> Decimal` — безопасное отношение без деления на ноль.

---

## 10.5 `insights.py` (инсайты)

### Dataclass

- `InsightsThresholds` — пороги для генерации инсайтов.
- `FinancialInsight` — контракт одного инсайта.
- `InsightsResult` — итоговый результат генерации.

### Публичные функции

- `generate_financial_insights(dataframe, amount_column="amount", currency="RUB", thresholds=None, language="ru") -> InsightsResult`  
  Генерирует список инсайтов (подписки, рост категорий, savings summary).

### Внутренние функции

- `_minor_to_major(minor_value) -> float` — minor→major.
- `_format_major(minor_value, currency) -> str` — форматирует сумму для сообщений.
- `_month_start_utc(series) -> pd.Series` — UTC-привязка к началу месяца.
- `_prepare_dataframe(dataframe, amount_column) -> pd.DataFrame` — подготовка к аналитике.
- `_detect_subscription_insights(...) -> list[FinancialInsight]` — инсайты по recurring-подпискам.
- `_detect_growth_insights(...) -> list[FinancialInsight]` — инсайты по росту категорий MoM.
- `_build_savings_summary(insights, thresholds, currency, language) -> FinancialInsight | None` — финальный инсайт с рекомендацией по накоплениям.

---

## 10.6 `auth.py` (аккаунты и аутентификация)

### Dataclass

- `AuthResult` — результат регистрации/логина.

### Публичные функции

- `normalize_email(email) -> str` — нормализует email.
- `is_valid_email(email) -> bool` — проверяет базовый email-формат.
- `validate_password_policy(password, language="ru") -> tuple[bool, str]` — проверяет политику пароля.
- `load_users(users_path=...) -> list[dict]` — загружает пользователей.
- `register_user(email, password, users_path=..., language="ru") -> AuthResult` — регистрация пользователя.
- `login_user(email, password, users_path=..., language="ru") -> AuthResult` — вход пользователя.
- `derive_user_encryption_key(user_id, password, users_path=...) -> bytes | None` — получает пользовательский AES-ключ.
- `get_user_by_id(user_id, users_path=...) -> dict | None` — возвращает публичный профиль по id.
- `update_user_consent(user_id, consent_pii_storage, users_path=...) -> bool` — обновляет consent.
- `delete_user_account(user_id, users_path=...) -> bool` — удаляет пользователя.

### Внутренние функции

- `_hash_password(password, salt, iterations=...) -> bytes` — PBKDF2-хеш.
- `_users_payload_path(users_path=...) -> Path` — путь к файлу пользователей.
- `_save_users(users, users_path=...) -> None` — сохраняет users JSON.
- `_public_user_record(record) -> dict` — безопасное представление без hash/salt.
- `_find_user_by_email(users, email) -> dict | None` — поиск по email.
- `_find_user_by_id(users, user_id) -> dict | None` — поиск по user_id.

---

## 10.7 `secure_store.py` (шифрованное хранилище)

### Dataclass

- `SecureStoreResult` — результат операции secure store.

### Публичные функции

- `is_aes_available() -> bool` — проверка доступности AES через `cryptography`.
- `encrypt_dataframe(dataframe, user_id, encryption_key, base_dir=..., language="ru") -> SecureStoreResult`  
  Шифрует и сохраняет DataFrame в файл пользователя.
- `decrypt_dataframe(user_id, encryption_key, base_dir=..., language="ru") -> SecureStoreResult`  
  Загружает и расшифровывает пользовательские транзакции.
- `delete_user_secure_data(user_id, base_dir=...) -> bool` — удаляет зашифрованный payload.

### Внутренние функции

- `_user_payload_path(user_id, base_dir=...) -> Path` — путь к файлу шифрованных данных.
- `_encode(value: bytes) -> str` — bytes→base64.
- `_decode(value: str) -> bytes` — base64→bytes.
- `_serialize_dataframe(dataframe) -> str` — сериализация DataFrame в JSON.
- `_deserialize_dataframe(payload_json) -> pd.DataFrame` — обратная десериализация JSON в DataFrame.

---

## 10.8 `export_utils.py` (экспорт)

### Dataclass

- `ExportArtifact` — один бинарный файл экспорта.
- `ExportResult` — итог экспорта (artifacts/warnings/errors/metadata).

### Публичные функции

- `export_report_tables(report_name, tables, formats=("csv", "xlsx", "pdf"), generated_at=None, language="ru") -> ExportResult`  
  Формирует набор файлов экспорта по унифицированному контракту Stage H.

### Внутренние функции

- `_slugify(value) -> str` — нормализует текст для детерминированного имени файла.
- `_sanitize_dataframe(dataframe) -> pd.DataFrame` — подготавливает данные к экспорту (даты в string UTC).
- `_normalize_tables(tables, language) -> tuple[dict[str, pd.DataFrame], list[str]]` — валидирует таблицы.
- `_build_csv_artifacts(report_slug, tables) -> list[ExportArtifact]` — CSV-артефакты.
- `_build_xlsx_artifact(report_slug, tables) -> ExportArtifact` — единый XLSX.
- `_pdf_escape(text) -> str` — экранирует PDF-текст.
- `_build_simple_pdf(lines) -> bytes` — минималистичный PDF-генератор.
- `_build_pdf_artifact(report_slug, tables) -> ExportArtifact` — PDF-артефакт.

---

## 10.9 `sync_api.py` (синхронизация между устройствами)

### Dataclass

- `SyncApiResult` — результат обработки запроса sync API.

### Публичные функции

- `push_sync_payload(request, email, password, users_path=..., sync_state_path=..., language="en") -> SyncApiResult`  
  Push endpoint: валидирует, аутентифицирует, шифрует payload и делает upsert.
- `pull_sync_payload(request, email, password, users_path=..., sync_state_path=..., language="en") -> SyncApiResult`  
  Pull endpoint: возвращает расшифрованные записи `client_revision > since_revision`.

### Внутренние функции

- `_state_path(sync_state_path=...) -> Path` — путь к sync state файлу.
- `_load_state(sync_state_path=...) -> list[dict]` — загрузка state.
- `_save_state(records, sync_state_path=...) -> None` — сохранение state.
- `_normalize_text(value, max_length) -> str` — нормализация ограниченной длины.
- `_sha256_hex(data) -> str` — SHA-256 хеш payload.
- `_validate_push_request(request, language) -> list[str]` — детерминированная валидация push.
- `_validate_pull_request(request, language) -> list[str]` — детерминированная валидация pull.
- `_authenticate(email, password, user_id, users_path, language) -> tuple[bool, str]` — auth и проверка соответствия `user_id`.
- `_derive_storage_key(user_id, password, users_path) -> bytes | None` — ключ шифрования sync payload.
- `_encrypt_payload(payload_json, key, aad) -> tuple[str, str]` — AES-GCM шифрование payload.
- `_decrypt_payload(nonce_b64, ciphertext_b64, key, aad) -> dict | None` — AES-GCM дешифрование payload.

---

## 10.10 `i18n.py` (локализация)

### Публичные функции

- `normalize_language(language) -> str` — нормализует язык и применяет fallback.
- `tr(key, lang=None, **kwargs) -> str` — получает локализованную строку по ключу с форматированием.

### Данные модуля

- `DEFAULT_LANGUAGE = "ru"`
- `SUPPORTED_LANGUAGES = ("ru", "en")`
- `TRANSLATIONS: dict[str, dict[str, str]]` — полный словарь UI/системных текстов.

---

## 10.11 `app.py` (Streamlit UI и orchestration)

`app.py` связывает все модули в единый пользовательский сценарий.

### Внутренние функции UI-слоя

- `_t(key, **kwargs) -> str` — short alias над `tr()` с текущим языком.
- `_user_rules_path(user_id) -> Path` — user-specific путь к rules.
- `_anomaly_feedback_path(user_id) -> Path` — user-specific путь к feedback.
- `_set_authenticated_session(user, encryption_key) -> None` — инициализация auth-сессии.
- `_clear_authenticated_session() -> None` — сброс auth-сессии.
- `_get_session_encryption_key() -> bytes | None` — извлечение AES-ключа из session state.
- `_render_language_switcher() -> None` — переключатель RU/EN.
- `_render_auth_panel() -> dict | None` — регистрация, вход, consent, удаление аккаунта.
- `_insights_to_dataframe(insights_result, currency) -> pd.DataFrame` — преобразование инсайтов в табличный экспорт.
- `_minor_series_to_major(series) -> pd.Series` — UI-конвертация minor→major.
- `_render_export_section(report_name, export_tables, scope_key) -> None` — рендер и выдача export artifacts.
- `_render_dashboard_blocks(analytics_df, amount_column, display_currency, budget_scope_key, anomaly_feedback_path) -> None`  
  Рендерит все аналитические блоки: category, trend, merchants, recurring, budget, insights, anomaly, export.

---

## 11. Тестирование

Тесты расположены в `tests/`:

- `test_io_utils.py`
- `test_categorizer.py`
- `test_analytics.py`
- `test_anomaly.py`
- `test_insights.py`
- `test_export_utils.py`
- `test_sync_api.py`
- `test_secure_store.py`
- `test_auth.py`
- `test_i18n.py`
- `test_e2e_bank_statements.py`

Запуск:

```bash
python -m pytest
```

Fallback:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 12. Планы развития

- OAuth/Open Banking интеграции (опционально, без блокировки текущего MVP).
- Расширение синхронизации до сетевого API/хранилища.
- ML-слой поверх `models/` для smarter категоризации и риск-скоринга.
- Расширение экспортов (архивы, брендированные PDF-отчёты).

## 12. Планы развития

Проект уже реализует MVP системы аналитики транзакций (PFM) с безопасным хранением данных, базовой категоризацией, аналитикой и обнаружением аномалий.  
Дальнейшее развитие направлено на повышение автоматизации, качества аналитики и удобства пользователя.

---

### 12.1 Интеграции и импорт данных

Расширение способов получения транзакций.

- OAuth / Open Banking интеграции (где доступны API банков).
- Импорт данных из банковских CSV/Excel форматов различных банков.
- Поддержка форматов экспортов популярных банковских приложений.
- Импорт из платёжных сервисов (например:
  - Apple Pay
  - Google Pay
  - PayPal).
- Автоматическая нормализация форматов транзакций при импорте.

Цель: минимизировать ручную подготовку данных.

---

### 12.2 Расширение аналитики финансов

Углубление возможностей анализа транзакций.

- Детальные отчёты по категориям расходов.
- Анализ динамики расходов по месяцам.
- Определение регулярных платежей (подписок).
- Выявление резких изменений в структуре расходов.
- Анализ топ-категорий и топ-мерчантов.

Дополнительно:

- прогноз расходов на следующий месяц
- анализ сезонности расходов

---

### 12.3 Бюджетирование и финансовое планирование

Добавление инструментов управления личным бюджетом.

- настройка месячных бюджетов по категориям
- отслеживание превышения бюджета
- предупреждения о перерасходе
- планирование накоплений
Пример:

- Еда — бюджет 30 000 RUB
- Транспорт — бюджет 8 000 RUB
- Развлечения — бюджет 10 000 RUB

### 12.4 Финансовые цели (Savings Goals)

Добавление механизма финансовых целей.

Пользователь сможет:

- создавать цели накоплений
- отслеживать прогресс
- автоматически распределять свободные средства

Пример:
- Цель: накопить 300 000 RUB 
- Срок: 12 месяцев
---
---

### 12.5 Улучшение обнаружения аномалий

Развитие модуля `anomaly.py`.

Сейчас используется rule-based логика.

Планируется:

- анализ необычно больших транзакций
- обнаружение нетипичных мерчантов
- обнаружение аномальной частоты операций
- анализ географических отклонений транзакций

Дополнительно возможно внедрение ML-алгоритмов:

- Isolation Forest
- Local Outlier Factor

Цель: повысить качество обнаружения подозрительных операций.

---

### 12.6 ML-модели для категоризации и аналитики

Добавление ML-слоя поверх `models/`.

Планируется:

- автоматическая категоризация транзакций
- обучение на истории пользователя
- улучшение классификации мерчантов
- построение персональных финансовых рекомендаций

Пример задачи:
merchant + description → category
Возможные технологии:

- scikit-learn
- lightweight NLP модели

---

### 12.7 Улучшение пользовательских инсайтов

Развитие модуля `insights.py`.

Будут добавлены:

- персональные рекомендации по оптимизации расходов
- советы по сокращению ненужных подписок
- рекомендации по накоплениям
- анализ финансового поведения пользователя

Пример инсайта:


Ваши расходы на такси выросли на 35% по сравнению с прошлым месяцем.
Рекомендуется проверить альтернативные варианты транспорта.
---

### 12.8 Расширение синхронизации данных

Развитие `sync_api`.

Планируется:

- синхронизация между устройствами
- облачное хранилище зашифрованных данных
- версия истории изменений (revision history)
- офлайн-режим с последующей синхронизацией

Цель: обеспечить безопасную синхронизацию данных пользователя.

---

### 12.9 Улучшение визуализации данных

Добавление расширенного аналитического дашборда.

Планируется:

- интерактивные графики расходов
- графики динамики категорий
- диаграммы распределения расходов
- финансовая сводка по месяцам

Возможные технологии:

- Plotly
- Altair

---

### 12.10 Улучшение экспортов и отчётности

Развитие модуля `export_utils`.

Планируется:

- расширение форматов экспорта
- брендированные PDF-отчёты
- архивы отчётов за период
- автоматическая генерация финансовых сводок

Поддерживаемые форматы:

- CSV
- XLSX
- PDF
- ZIP архивы

---

### 12.11 Улучшение безопасности

Дополнительные меры защиты данных пользователя.

Планируется:

- двухфакторная аутентификация
- защита сессий
- автоматическая блокировка при подозрительной активности
- расширение криптографических механизмов хранения данных

---

### 12.12 Масштабирование архитектуры

Подготовка проекта к возможному росту.

Планируется:

- выделение backend API
- переход к микросервисной архитектуре
- масштабируемое хранение данных
- контейнеризация (Docker)

---

### Итоговая цель развития

Превратить проект из MVP PFM-системы в полноценную платформу управления личными финансами с:

- автоматической аналитикой транзакций
- интеллектуальной категоризацией
- системой финансовых рекомендаций
- безопасным хранением данных
- синхронизацией между устройствами.

---

## 13. Лицензирование и ответственность

Проект обрабатывает чувствительные финансовые данные. Перед эксплуатацией в production рекомендуется:

- провести security review;
- настроить защищённый деплой (TLS, секреты, ротация ключей, бэкапы);
- проверить юридические требования по PII и банковским данным в целевой юрисдикции.
