import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd


RuleField = Literal["merchant", "description", "both"]
RuleMatchType = Literal["contains", "exact"]
RuleDirection = Literal["any", "income", "expense"]

DEFAULT_USER_RULES_PATH = Path("models") / "user_rules.json"


@dataclass(frozen=True)
class CategoryRule:
    """Правило категоризации по текстовым шаблонам."""

    pattern: str
    category: str
    field: RuleField = "both"
    match_type: RuleMatchType = "contains"
    direction: RuleDirection = "any"
    source: str = "builtin"


def _build_builtin_rules() -> list[CategoryRule]:
    """
    Набор приоритетных встроенных правил (MVP).

    Порядок важен: сверху более специфичные правила, ниже более общие.
    """
    raw_rules: list[tuple[str, str, RuleField, RuleDirection]] = [
        # Доходы
        ("зарплата", "salary", "description", "income"),
        ("salary", "salary", "description", "income"),
        ("employer", "salary", "merchant", "income"),
        ("тинькофф", "salary", "both", "income"),
        ("tinkoff", "salary", "both", "income"),
        # Продукты
        ("пятерочка", "groceries", "merchant", "any"),
        ("pyaterochka", "groceries", "merchant", "any"),
        ("магнит", "groceries", "merchant", "any"),
        ("magnit", "groceries", "merchant", "any"),
        ("перекресток", "groceries", "merchant", "any"),
        ("perekrestok", "groceries", "merchant", "any"),
        ("лента", "groceries", "merchant", "any"),
        ("lenta", "groceries", "merchant", "any"),
        ("дикси", "groceries", "merchant", "any"),
        ("dixy", "groceries", "merchant", "any"),
        ("вкусвилл", "groceries", "merchant", "any"),
        ("vkusvill", "groceries", "merchant", "any"),
        ("lidl", "groceries", "merchant", "any"),
        ("rimi", "groceries", "merchant", "any"),
        # Транспорт
        ("яндекс go", "taxi", "both", "expense"),
        ("yandex go", "taxi", "both", "expense"),
        ("яндексgo", "taxi", "both", "expense"),
        ("yandexgo", "taxi", "both", "expense"),
        ("такси", "taxi", "description", "expense"),
        ("taxi", "taxi", "description", "expense"),
        ("bolt", "taxi", "merchant", "expense"),
        # Топливо / АЗС
        ("азс", "fuel", "merchant", "expense"),
        ("lukoil", "fuel", "merchant", "expense"),
        ("лукойл", "fuel", "merchant", "expense"),
        ("газпромнефть", "fuel", "merchant", "expense"),
        ("rosneft", "fuel", "merchant", "expense"),
        ("роснефть", "fuel", "merchant", "expense"),
        ("tatneft", "fuel", "merchant", "expense"),
        ("татнефть", "fuel", "merchant", "expense"),
        ("shell", "fuel", "merchant", "expense"),
        # Маркетплейсы / шопинг
        ("wildberries", "shopping", "merchant", "expense"),
        ("вайлдберриз", "shopping", "merchant", "expense"),
        ("ozon", "shopping", "merchant", "expense"),
        ("озон", "shopping", "merchant", "expense"),
        ("amazon", "shopping", "merchant", "expense"),
        ("zara", "shopping", "merchant", "expense"),
        ("h&m", "shopping", "merchant", "expense"),
        # Подписки
        ("netflix", "subscriptions", "merchant", "expense"),
        ("spotify", "subscriptions", "merchant", "expense"),
        ("youtube", "subscriptions", "merchant", "expense"),
        ("subscription", "subscriptions", "description", "expense"),
        # Кафе и рестораны
        ("starbucks", "food", "merchant", "expense"),
        ("kfc", "food", "merchant", "expense"),
        ("mcdonald", "food", "merchant", "expense"),
        ("coffee", "food", "description", "expense"),
        # Развлечения
        ("cinema", "entertainment", "merchant", "expense"),
        ("entertainment", "entertainment", "description", "expense"),
        # Платежи/переводы банка
        ("тинькофф", "bank_payments", "both", "expense"),
        ("tinkoff", "bank_payments", "both", "expense"),
    ]

    return [
        CategoryRule(pattern=pattern, category=category, field=field, direction=direction)
        for pattern, category, field, direction in raw_rules
    ]


BUILTIN_RULES = _build_builtin_rules()


# Базовый транслит RU -> LAT (приближенный, достаточный для матчинг-задач).
_RU_TO_LAT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

# Приближенный LAT -> RU (для задач fuzzy-матчинга в MVP).
_LAT_TO_RU_MULTI: dict[str, str] = {
    "sch": "щ",
    "sh": "ш",
    "ch": "ч",
    "zh": "ж",
    "kh": "х",
    "ts": "ц",
    "yu": "ю",
    "ya": "я",
    "yo": "ё",
}

_LAT_TO_RU_SINGLE: dict[str, str] = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "й",
    "z": "з",
}


def normalize_text(value: Any) -> str:
    """Нормализация текста для устойчивого матчинг-поиска."""
    if pd.isna(value):
        return ""

    text = str(value).strip().lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"_", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def transliterate_ru_to_lat(text: str) -> str:
    """Преобразует кириллицу в латиницу для сравнения вариантов написания."""
    normalized = normalize_text(text)
    return "".join(_RU_TO_LAT.get(char, char) for char in normalized)


def transliterate_lat_to_ru(text: str) -> str:
    """Преобразует латиницу в приближенную кириллицу для сравнения вариантов написания."""
    normalized = normalize_text(text)
    result: list[str] = []

    index = 0
    while index < len(normalized):
        matched = False

        for latin_chunk, cyrillic_chunk in _LAT_TO_RU_MULTI.items():
            if normalized.startswith(latin_chunk, index):
                result.append(cyrillic_chunk)
                index += len(latin_chunk)
                matched = True
                break

        if matched:
            continue

        current = normalized[index]
        result.append(_LAT_TO_RU_SINGLE.get(current, current))
        index += 1

    return "".join(result)


def build_text_variants(text: str) -> set[str]:
    """Возвращает набор нормализованных вариантов строки для мультиязычного матчинга."""
    base = normalize_text(text)
    if not base:
        return {""}

    ru_to_lat = normalize_text(transliterate_ru_to_lat(base))
    lat_to_ru = normalize_text(transliterate_lat_to_ru(base))

    return {variant for variant in {base, ru_to_lat, lat_to_ru} if variant}


def load_user_rules(rules_path: str | Path = DEFAULT_USER_RULES_PATH) -> list[CategoryRule]:
    """Загружает пользовательские правила из JSON; при ошибке возвращает пустой список."""
    path = Path(rules_path)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    user_rules: list[CategoryRule] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        pattern = str(item.get("pattern", "")).strip()
        category = str(item.get("category", "")).strip()
        field = str(item.get("field", "both")).strip().lower()
        match_type = str(item.get("match_type", "contains")).strip().lower()
        direction = str(item.get("direction", "any")).strip().lower()

        if not pattern or not category:
            continue
        if field not in {"merchant", "description", "both"}:
            field = "both"
        if match_type not in {"contains", "exact"}:
            match_type = "contains"
        if direction not in {"any", "income", "expense"}:
            direction = "any"

        user_rules.append(
            CategoryRule(
                pattern=pattern,
                category=category,
                field=field,
                match_type=match_type,
                direction=direction,
                source="user",
            )
        )

    return user_rules


def save_user_rule(
    pattern: str,
    category: str,
    field: RuleField = "both",
    match_type: RuleMatchType = "contains",
    direction: RuleDirection = "any",
    rules_path: str | Path = DEFAULT_USER_RULES_PATH,
) -> bool:
    """
    Сохраняет пользовательское правило и возвращает True, если добавлено новое правило.

    В случае дубликата (same pattern/category/field/match_type/direction) запись не дублируется.
    """
    normalized_pattern = normalize_text(pattern)
    normalized_category = str(category).strip()

    if not normalized_pattern or not normalized_category:
        return False

    path = Path(rules_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_payload: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_payload = [item for item in loaded if isinstance(item, dict)]
        except json.JSONDecodeError:
            existing_payload = []

    candidate = {
        "pattern": normalized_pattern,
        "category": normalized_category,
        "field": field,
        "match_type": match_type,
        "direction": direction,
        "created_at": datetime.now(UTC).isoformat(),
    }

    duplicate_found = any(
        normalize_text(item.get("pattern", "")) == candidate["pattern"]
        and str(item.get("category", "")).strip() == candidate["category"]
        and str(item.get("field", "both")).strip().lower() == candidate["field"]
        and str(item.get("match_type", "contains")).strip().lower() == candidate["match_type"]
        and str(item.get("direction", "any")).strip().lower() == candidate["direction"]
        for item in existing_payload
    )
    if duplicate_found:
        return False

    existing_payload.append(candidate)
    path.write_text(json.dumps(existing_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _direction_matches(direction: RuleDirection, amount: Any) -> bool:
    if direction == "any":
        return True

    if pd.isna(amount):
        return False

    value = float(amount)
    if direction == "income":
        return value > 0
    return value < 0


def _extract_text_by_field(field: RuleField, merchant: str, description: str) -> str:
    if field == "merchant":
        return merchant
    if field == "description":
        return description
    return f"{merchant} {description}".strip()


def _rule_matches(rule: CategoryRule, merchant: str, description: str, amount: Any) -> bool:
    if not _direction_matches(rule.direction, amount):
        return False

    candidate_text = _extract_text_by_field(rule.field, merchant, description)
    text_variants = build_text_variants(candidate_text)

    rule_pattern_variants = build_text_variants(rule.pattern)
    for text_variant in text_variants:
        for pattern_variant in rule_pattern_variants:
            if not text_variant or not pattern_variant:
                continue

            if rule.match_type == "exact" and text_variant == pattern_variant:
                return True
            if rule.match_type == "contains" and pattern_variant in text_variant:
                return True

    return False


def _pick_category(
    merchant: str,
    description: str,
    amount: Any,
    rules: list[CategoryRule],
) -> tuple[str, str]:
    for rule in rules:
        if _rule_matches(rule=rule, merchant=merchant, description=description, amount=amount):
            return rule.category, rule.source

    return "uncategorized", "none"


def categorize_transactions(
    dataframe: pd.DataFrame,
    rules_path: str | Path = DEFAULT_USER_RULES_PATH,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Проставляет category для транзакций по user+builtin правилам.

    Возвращает:
      - DataFrame с колонками category и category_source
      - Метаданные категоризации: coverage_ratio, coverage_percent, categorized_rows, total_rows
    """
    categorized = dataframe.copy()

    if "merchant" not in categorized.columns:
        categorized["merchant"] = ""
    if "description" not in categorized.columns:
        categorized["description"] = ""
    if "amount" not in categorized.columns:
        categorized["amount"] = pd.NA

    categorized["merchant"] = categorized["merchant"].fillna("").astype(str)
    categorized["description"] = categorized["description"].fillna("").astype(str)

    user_rules = load_user_rules(rules_path=rules_path)
    all_rules = [*user_rules, *BUILTIN_RULES]

    result_pairs = categorized.apply(
        lambda row: _pick_category(
            merchant=row.get("merchant", ""),
            description=row.get("description", ""),
            amount=row.get("amount", pd.NA),
            rules=all_rules,
        ),
        axis=1,
    )

    categorized["category"] = [item[0] for item in result_pairs]
    categorized["category_source"] = [item[1] for item in result_pairs]

    total_rows = int(categorized.shape[0])
    categorized_rows = int((categorized["category"] != "uncategorized").sum())
    coverage_ratio = (categorized_rows / total_rows) if total_rows > 0 else 0.0

    metadata = {
        "rules_total": len(all_rules),
        "rules_user": len(user_rules),
        "rules_builtin": len(BUILTIN_RULES),
        "total_rows": total_rows,
        "categorized_rows": categorized_rows,
        "coverage_ratio": coverage_ratio,
        "coverage_percent": round(coverage_ratio * 100, 2),
    }

    return categorized, metadata
