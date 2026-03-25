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
    # ==================== ДОХОДЫ ====================
    ("зарплата", "salary", "both", "income"),
    ("salary", "salary", "both", "income"),
    ("employer", "salary", "merchant", "income"),
    ("тинькофф", "salary", "both", "income"),
    ("tinkoff", "salary", "both", "income"),
    ("перевод от", "transfer_income", "both", "income"),
    ("поступление", "income", "both", "income"),
    ("возврат", "refund", "both", "income"),
    ("пенсия", "income", "both", "income"),
    ("стипендия", "income", "both", "income"),
    ("дивиденды", "income", "both", "income"),
    ("кэшбэк", "income", "both", "income"),
    ("перевод от", "income", "both", "income"),
    ("перевод для", "transfer", "both", "expense"),
    ("перевод с карты", "transfer", "both", "expense"),
    ("перевод на карту", "income", "both", "income"),
    ("поступление", "income", "both", "income"),
    ("возврат", "refund", "both", "income"),
    ("пополнение", "income", "both", "income"),
    ("внесение наличных", "cash_in", "merchant", "income"),
    ("+", "income", "description", "income"),


    # ==================== ПРОДУКТЫ ====================
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
    ("spar", "groceries", "merchant", "any"),
    ("ашан", "groceries", "merchant", "any"),
    ("auchan", "groceries", "merchant", "any"),
    ("метро", "groceries", "merchant", "any"),
    ("metro", "groceries", "merchant", "any"),
    ("окей", "groceries", "merchant", "any"),
    ("okey", "groceries", "merchant", "any"),
    ("bristol", "groceries", "merchant", "any"),
    ("бристоль", "groceries", "merchant", "any"),
    ("красное&белое", "groceries", "merchant", "any"),
    ("krasnoe&beloe", "groceries", "merchant", "any"),
    ("магнолия", "groceries", "merchant", "any"),
    ("magnoliya", "groceries", "merchant", "any"),
    ("кулкливер", "groceries", "merchant", "any"),
    ("kuulklever", "groceries", "merchant", "any"),
    ("малинка", "groceries", "merchant", "any"),
    ("malinka", "groceries", "merchant", "any"),
    ("карусель", "groceries", "merchant", "any"),
    ("carousel", "groceries", "merchant", "any"),
    ("верный", "groceries", "merchant", "any"),
    ("verniy", "groceries", "merchant", "any"),
    ("фикс прайс", "shopping", "merchant", "any"),   # всё же шопинг
    ("fixprice", "shopping", "merchant", "any"),
    ("семья", "groceries", "merchant", "any"),
    ("семья", "groceries", "merchant", "any"),
    ("светофор", "groceries", "merchant", "any"),
    ("svetofor", "groceries", "merchant", "any"),
    ("маяк", "groceries", "merchant", "any"),
    ("радуга", "groceries", "merchant", "any"),
    ("мясновъ", "groceries", "merchant", "any"),
    ("табрис", "groceries", "merchant", "any"),
    ("табрис", "groceries", "merchant", "any"),
    ("озон", "shopping", "merchant", "any"),   # ozon тоже шопинг
    ("wildberries", "shopping", "merchant", "any"),
    ("вайлдберриз", "shopping", "merchant", "any"),
    ("ozon", "shopping", "merchant", "any"),
    ("яндекс маркет", "shopping", "merchant", "any"),
    ("yandex market", "shopping", "merchant", "any"),
    ("алиэкспресс", "shopping", "merchant", "any"),
    ("aliexpress", "shopping", "merchant", "any"),
    ("lamoda", "shopping", "merchant", "any"),
    ("беру", "shopping", "merchant", "any"),
    ("beru", "shopping", "merchant", "any"),
    ("modi", "shopping", "merchant", "any"),
    ("магазин", "shopping", "merchant", "any"),  # общее
    ("супермаркет", "groceries", "merchant", "any"),
    ("продукты", "groceries", "both", "any"),
    ("MAGNOLIYA", "groceries", "merchant", "any"),
    ("KUULKLEVER", "groceries", "merchant", "any"),
    ("MALINKA", "groceries", "merchant", "any"),
    ("KRASNOE&BELOE", "groceries", "merchant", "any"),
    ("MIRATORG", "groceries", "merchant", "any"),
    ("SAMOKAT", "groceries", "merchant", "any"),
    ("SPAR", "groceries", "merchant", "any"),
    ("BRISTOL", "groceries", "merchant", "any"),
    ("FIXPRICE", "shopping", "merchant", "any"),
    ("DIXY", "groceries", "merchant", "any"),
    ("PYATEROCHKA", "groceries", "merchant", "any"),
    ("PEREKRESTOK", "groceries", "merchant", "any"),
    ("LENTA", "groceries", "merchant", "any"),
    ("AUCHAN", "groceries", "merchant", "any"),
    ("OKEY", "groceries", "merchant", "any"),
    ("VERNYI", "groceries", "merchant", "any"),
    ("MAGAZIN DYMOSFERA", "groceries", "merchant", "any"),

    # ==================== КАФЕ И РЕСТОРАНЫ ====================
    ("kfc", "food", "merchant", "expense"),
    ("mcdonald", "food", "merchant", "expense"),
    ("бургер кинг", "food", "merchant", "expense"),
    ("burger king", "food", "merchant", "expense"),
    ("вкусно и точка", "food", "merchant", "expense"),
    ("vkusno i tochka", "food", "merchant", "expense"),
    ("teremok", "food", "merchant", "expense"),
    ("додо пицца", "food", "merchant", "expense"),
    ("dodo pizza", "food", "merchant", "expense"),
    ("starbucks", "food", "merchant", "expense"),
    ("coffee", "food", "both", "expense"),
    ("кофе", "food", "both", "expense"),
    ("шаурма", "food", "merchant", "expense"),
    ("shaurma", "food", "merchant", "expense"),
    ("суши", "food", "merchant", "expense"),
    ("sushi", "food", "merchant", "expense"),
    ("пицца", "food", "merchant", "expense"),
    ("pizza", "food", "merchant", "expense"),
    ("кафе", "food", "merchant", "expense"),
    ("ресторан", "food", "merchant", "expense"),
    ("кофейня", "food", "merchant", "expense"),
    ("бар", "food", "merchant", "expense"),
    ("столовая", "food", "merchant", "expense"),
    ("кулинария", "food", "merchant", "expense"),
    ("суши вок", "food", "merchant", "expense"),
    ("якитория", "food", "merchant", "expense"),
    ("rocks", "food", "merchant", "expense"),
    ("му-му", "food", "merchant", "expense"),
    ("шоколадница", "food", "merchant", "expense"),
    ("chocolatier", "food", "merchant", "expense"),
    ("cinnabon", "food", "merchant", "expense"),
    ("coffee like", "food", "merchant", "expense"),
    ("doubleby", "food", "merchant", "expense"),
    ("чайхона", "food", "merchant", "expense"),
    ("папа джонс", "food", "merchant", "expense"),
    ("papa johns", "food", "merchant", "expense"),
    ("sbarro", "food", "merchant", "expense"),
    ("il patio", "food", "merchant", "expense"),
    ("ростикс", "food", "merchant", "expense"),
    ("rostix", "food", "merchant", "expense"),
    ("wendy's", "food", "merchant", "expense"),
    ("вкусно", "food", "both", "expense"),
    ("MODI", "food", "merchant", "expense"),
    ("MODI_11089", "food", "merchant", "expense"),
    ("STOLLE M BIRUZOVA MOSKVA RUS", "food", "merchant", "expense"),
    ("VKUSNOITOCHKA_29754", "food", "merchant", "expense"),
    ("CHICKO - VKUS KOREI", "food", "merchant", "expense"),
    ("HONGDAE", "food", "merchant", "expense"),
    ("VIET QUAN", "food", "merchant", "expense"),
    ("DVORIK", "food", "merchant", "expense"),
    ("IMPERIYA GREZ_SDK", "food", "merchant", "expense"),
    ("Hirosima Moya Lubov", "food", "merchant", "expense"),
    ("Kvartira8", "food", "merchant", "expense"),
    ("PROVOTOROVA", "food", "merchant", "expense"),
    ("TAKOYAKI", "food", "merchant", "expense"),
    ("GELATERIA PLOMBIR", "food", "merchant", "expense"),
    ("KIMCHI TO GO", "food", "merchant", "expense"),
    ("WAHAHA", "food", "merchant", "expense"),
    ("REST NEBO MURINO", "food", "merchant", "expense"),
    ("Krunchydream", "food", "merchant", "expense"),
    ("SO VOK", "food", "merchant", "expense"),
    ("TA SAMAYA SHAURMA", "food", "merchant", "expense"),
    ("AMBAPIZZA", "food", "merchant", "expense"),
    ("DODO PIZZA", "food", "merchant", "expense"),
    ("KAFE VSPYSHKA", "food", "merchant", "expense"),
    ("BEER MUG", "food", "merchant", "expense"),
    ("SP_BESTCOFFE", "food", "merchant", "expense"),
    ("CYCLO", "food", "merchant", "expense"),
    ("SUSHI BAR", "food", "merchant", "expense"),
    ("CHIZKEECHNAYA", "food", "merchant", "expense"),
    ("QSR 23015", "food", "merchant", "expense"),
    ("COFFEE", "food", "both", "expense"), 
    ("кофе", "food", "both", "expense"),
    ("шаурма", "food", "both", "expense"),
    ("пицца", "food", "both", "expense"),

    # ==================== ТРАНСПОРТ ====================
    ("яндекс go", "taxi", "both", "expense"),
    ("yandex go", "taxi", "both", "expense"),
    ("яндексgo", "taxi", "both", "expense"),
    ("yandexgo", "taxi", "both", "expense"),
    ("такси", "taxi", "both", "expense"),
    ("taxi", "taxi", "both", "expense"),
    ("uber", "taxi", "merchant", "expense"),
    ("gett", "taxi", "merchant", "expense"),
    ("ситимобил", "taxi", "merchant", "expense"),
    ("citymobil", "taxi", "merchant", "expense"),
    ("транспорт", "transport", "category", "expense"),
    ("siticard", "transport", "merchant", "expense"),
    ("московский транспорт", "transport", "merchant", "expense"),
    ("mos. transport", "transport", "merchant", "expense"),
    ("метро", "transport", "merchant", "expense"),
    ("автобус", "transport", "merchant", "expense"),
    ("электричка", "transport", "merchant", "expense"),
    ("аэроэкспресс", "transport", "merchant", "expense"),
    ("тройка", "transport", "merchant", "expense"),
    ("стрелка", "transport", "merchant", "expense"),
    ("подорожник", "transport", "merchant", "expense"),
    ("парковка", "parking", "merchant", "expense"),
    ("parking", "parking", "merchant", "expense"),
    ("штраф", "fines", "both", "expense"),
    ("гибдд", "fines", "both", "expense"),
    ("цппк", "transport", "merchant", "expense"),
    ("YANDEX*4121*GO", "taxi", "merchant", "expense"),
    ("YANDEX*7999*SCOOTERS", "taxi", "merchant", "expense"),
    ("YANDEX*7299*GO_RUNCHARGE", "taxi", "merchant", "expense"),
    ("YandexBank_C2A", "taxi", "merchant", "expense"),
    ("Uber", "taxi", "merchant", "expense"),
    ("Gett", "taxi", "merchant", "expense"),
    ("Citymobil", "taxi", "merchant", "expense"),
    ("Ситимобил", "taxi", "merchant", "expense"),
    ("Mos.Transport", "transport", "merchant", "expense"),
    ("Moskva Metro", "transport", "merchant", "expense"),
    ("SITICARD", "transport", "merchant", "expense"),
    ("Kryukovo", "transport", "merchant", "expense"),
    ("Moskva-Oktyabrskaya", "transport", "merchant", "expense"),
    ("Testovskaya", "transport", "merchant", "expense"),
    ("Komsomolskaya", "transport", "merchant", "expense"),
    ("Pl. Vosstaniya", "transport", "merchant", "expense"),
    ("Parking", "parking", "merchant", "expense"),

    # ==================== ТОПЛИВО / АЗС ====================
    ("азс", "fuel", "merchant", "expense"),
    ("лукойл", "fuel", "merchant", "expense"),
    ("lukoil", "fuel", "merchant", "expense"),
    ("газпромнефть", "fuel", "merchant", "expense"),
    ("rosneft", "fuel", "merchant", "expense"),
    ("роснефть", "fuel", "merchant", "expense"),
    ("tatneft", "fuel", "merchant", "expense"),
    ("татнефть", "fuel", "merchant", "expense"),
    ("shell", "fuel", "merchant", "expense"),
    ("bp", "fuel", "merchant", "expense"),
    ("trassa", "fuel", "merchant", "expense"),
    ("трасса", "fuel", "merchant", "expense"),

    # ==================== МАРКЕТПЛЕЙСЫ / ШОПИНГ ====================
    ("wildberries", "shopping", "merchant", "expense"),
    ("вайлдберриз", "shopping", "merchant", "expense"),
    ("ozon", "shopping", "merchant", "expense"),
    ("озон", "shopping", "merchant", "expense"),
    ("amazon", "shopping", "merchant", "expense"),
    ("aliexpress", "shopping", "merchant", "expense"),
    ("алиэкспресс", "shopping", "merchant", "expense"),
    ("lamoda", "shopping", "merchant", "expense"),
    ("беру", "shopping", "merchant", "expense"),
    ("beru", "shopping", "merchant", "expense"),
    ("яндекс маркет", "shopping", "merchant", "expense"),
    ("yandex market", "shopping", "merchant", "expense"),
    ("goods", "shopping", "merchant", "expense"),
    ("modi", "shopping", "merchant", "expense"),
    ("zara", "shopping", "merchant", "expense"),
    ("h&m", "shopping", "merchant", "expense"),
    ("mango", "shopping", "merchant", "expense"),
    ("stradivarius", "shopping", "merchant", "expense"),
    ("bershka", "shopping", "merchant", "expense"),
    ("pull&bear", "shopping", "merchant", "expense"),
    ("adidas", "shopping", "merchant", "expense"),
    ("nike", "shopping", "merchant", "expense"),
    ("reebok", "shopping", "merchant", "expense"),
    ("puma", "shopping", "merchant", "expense"),
    ("спортмастер", "shopping", "merchant", "expense"),
    ("sportmaster", "shopping", "merchant", "expense"),
    ("decathlon", "shopping", "merchant", "expense"),
    ("детский мир", "shopping", "merchant", "expense"),
    ("дм", "shopping", "merchant", "expense"),
    ("obi", "shopping", "merchant", "expense"),
    ("леруа мерлен", "shopping", "merchant", "expense"),
    ("leroy merlin", "shopping", "merchant", "expense"),
    ("икеа", "shopping", "merchant", "expense"),
    ("ikea", "shopping", "merchant", "expense"),
    ("dns", "electronics", "merchant", "expense"),
    ("м.видео", "electronics", "merchant", "expense"),
    ("mvideo", "electronics", "merchant", "expense"),
    ("эльдорадо", "electronics", "merchant", "expense"),
    ("eldorado", "electronics", "merchant", "expense"),
    ("citilink", "electronics", "merchant", "expense"),
    ("ситилинк", "electronics", "merchant", "expense"),
    ("медиамаркт", "electronics", "merchant", "expense"),
    ("mediamarkt", "electronics", "merchant", "expense"),
    ("холодильник", "electronics", "merchant", "expense"),
    ("220 вольт", "electronics", "merchant", "expense"),
    ("все для дома", "shopping", "category", "expense"),
    ("дом", "shopping", "both", "expense"),
    ("одежда", "clothing", "category", "expense"),
    ("обувь", "clothing", "category", "expense"),
    ("аксессуары", "clothing", "category", "expense"),
    ("электроника", "electronics", "category", "expense"),
    ("OZON", "shopping", "merchant", "expense"),
    ("WILDBERRIES", "shopping", "merchant", "expense"),
    ("LAMODA", "shopping", "merchant", "expense"),
    ("AVITO", "shopping", "merchant", "expense"),
    ("ЮЛА", "shopping", "merchant", "expense"),
    ("DNS", "electronics", "merchant", "expense"),
    ("MVIDEO", "electronics", "merchant", "expense"),
    ("ELDORADO", "electronics", "merchant", "expense"),
    ("CITILINK", "electronics", "merchant", "expense"),
    ("MEDIAMARKT", "electronics", "merchant", "expense"),
    ("LEROYMERLIN", "shopping", "merchant", "expense"),
    ("IKEA", "shopping", "merchant", "expense"),
    ("SPORTMASTER", "shopping", "merchant", "expense"),
    ("DECATHLON", "shopping", "merchant", "expense"),
    ("STOLICHNYJ GARDEROB", "shopping", "merchant", "expense"),
    ("GIG-STROJ", "shopping", "merchant", "expense"),
    ("EVO_CVETOK", "shopping", "merchant", "expense"),
    ("DOMARKET", "shopping", "merchant", "expense"),
    ("SMARTAUDIO", "electronics", "merchant", "expense"),
    ("KUPIVIP", "shopping", "merchant", "expense"),

    # ==================== ПОДПИСКИ ====================
    ("netflix", "subscriptions", "merchant", "expense"),
    ("spotify", "subscriptions", "merchant", "expense"),
    ("youtube", "subscriptions", "merchant", "expense"),
    ("subscription", "subscriptions", "both", "expense"),
    ("apple music", "subscriptions", "merchant", "expense"),
    ("apple tv", "subscriptions", "merchant", "expense"),
    ("icloud", "subscriptions", "merchant", "expense"),
    ("yandex plus", "subscriptions", "merchant", "expense"),
    ("яндекс плюс", "subscriptions", "merchant", "expense"),
    ("ivi", "subscriptions", "merchant", "expense"),
    ("кинопоиск", "subscriptions", "merchant", "expense"),
    ("kinopoisk", "subscriptions", "merchant", "expense"),
    ("premier", "subscriptions", "merchant", "expense"),
    ("okko", "subscriptions", "merchant", "expense"),
    ("amediateka", "subscriptions", "merchant", "expense"),
    ("more.tv", "subscriptions", "merchant", "expense"),
    ("start", "subscriptions", "merchant", "expense"),
    ("wink", "subscriptions", "merchant", "expense"),
    ("vpn", "subscriptions", "merchant", "expense"),

    # ==================== ЗДОРОВЬЕ И КРАСОТА ====================
    ("здоровье", "health", "category", "expense"),
    ("аптека", "health", "merchant", "expense"),
    ("apteka", "health", "merchant", "expense"),
    ("апрель", "health", "merchant", "expense"),
    ("горздрав", "health", "merchant", "expense"),
    ("zdravcity", "health", "merchant", "expense"),
    ("36.6", "health", "merchant", "expense"),
    ("золотое яблоко", "beauty", "merchant", "expense"),
    ("zolotoe yabloko", "beauty", "merchant", "expense"),
    ("лэтуаль", "beauty", "merchant", "expense"),
    ("letual", "beauty", "merchant", "expense"),
    ("рив гош", "beauty", "merchant", "expense"),
    ("rive gauche", "beauty", "merchant", "expense"),
    ("салон красоты", "beauty", "merchant", "expense"),
    ("парикмахерская", "beauty", "merchant", "expense"),
    ("stomatology", "health", "merchant", "expense"),
    ("стоматология", "health", "merchant", "expense"),
    ("клиника", "health", "merchant", "expense"),
    ("medsi", "health", "merchant", "expense"),
    ("APTECHNOE UCHREZHD-IE", "health", "merchant", "expense"),
    ("GBUZ NO KDC", "health", "merchant", "expense"),
    ("APTEKA", "health", "merchant", "expense"),
    ("GORZDRAV", "health", "merchant", "expense"),
    ("ZDRAVCITY", "health", "merchant", "expense"),
    ("36.6", "health", "merchant", "expense"),
    ("MEDSI", "health", "merchant", "expense"),
    ("INVITRO", "health", "merchant", "expense"),
    ("GEMOTEST", "health", "merchant", "expense"),
    ("STOMATOLOGIYA", "health", "merchant", "expense"),
    ("DENTISTRY", "health", "merchant", "expense"),
    ("ZOLOTOE YABLOKO", "beauty", "merchant", "expense"),
    ("LETUAL", "beauty", "merchant", "expense"),
    ("RIVE GAUCHE", "beauty", "merchant", "expense"),
    ("GK PERSONA", "beauty", "merchant", "expense"),
    ("MELODIYA ZDOROVYA", "health", "merchant", "expense"),
    ("PERSONA", "health", "merchant", "expense"),

    # ==================== ПУТЕШЕСТВИЯ ====================
    ("путешествия", "travel", "category", "expense"),
    ("travel", "travel", "both", "expense"),
    ("авиабилеты", "travel", "both", "expense"),
    ("ж/д билеты", "travel", "both", "expense"),
    ("отель", "travel", "merchant", "expense"),
    ("hotel", "travel", "merchant", "expense"),
    ("hostel", "travel", "merchant", "expense"),
    ("туры", "travel", "merchant", "expense"),
    ("russian railways", "travel", "merchant", "expense"),
    ("ржд", "travel", "merchant", "expense"),
    ("аэрофлот", "travel", "merchant", "expense"),
    ("s7", "travel", "merchant", "expense"),
    ("победа", "travel", "merchant", "expense"),
    ("utair", "travel", "merchant", "expense"),
    ("уральские авиалинии", "travel", "merchant", "expense"),
    ("nordwind", "travel", "merchant", "expense"),
    ("azur air", "travel", "merchant", "expense"),
    ("tutu", "travel", "merchant", "expense"),
    ("onetwotrip", "travel", "merchant", "expense"),
    ("booking", "travel", "merchant", "expense"),
    ("ostrovok", "travel", "merchant", "expense"),
    ("airbnb", "travel", "merchant", "expense"),
    ("RUSSIAN RAILWAYS", "travel", "merchant", "expense"),
    ("RZHD", "travel", "merchant", "expense"),
    ("AEROFLOT", "travel", "merchant", "expense"),
    ("S7", "travel", "merchant", "expense"),
    ("POBEDA", "travel", "merchant", "expense"),
    ("UTAIR", "travel", "merchant", "expense"),
    ("TUTU", "travel", "merchant", "expense"),
    ("ONETWOTRIP", "travel", "merchant", "expense"),
    ("BOOKING", "travel", "merchant", "expense"),
    ("OSTROVOK", "travel", "merchant", "expense"),
    ("AIRBNB", "travel", "merchant", "expense"),
    ("SPB ZD2", "travel", "merchant", "expense"),

    # ==================== КОММУНАЛЬНЫЕ УСЛУГИ, СВЯЗЬ ====================
    ("жкх", "utilities", "both", "expense"),
    ("коммунальные", "utilities", "both", "expense"),
    ("квартплата", "utilities", "both", "expense"),
    ("электроэнергия", "utilities", "both", "expense"),
    ("газ", "utilities", "both", "expense"),
    ("вода", "utilities", "both", "expense"),
    ("интернет", "utilities", "both", "expense"),
    ("телефон", "utilities", "both", "expense"),
    ("мтс", "utilities", "merchant", "expense"),
    ("билайн", "utilities", "merchant", "expense"),
    ("мегафон", "utilities", "merchant", "expense"),
    ("tele2", "utilities", "merchant", "expense"),
    ("ростелеком", "utilities", "merchant", "expense"),
    ("дом.ру", "utilities", "merchant", "expense"),
    ("dom.ru", "utilities", "merchant", "expense"),
    ("ттк", "utilities", "merchant", "expense"),
    ("netbynet", "utilities", "merchant", "expense"),
    ("мосэнергосбыт", "utilities", "merchant", "expense"),
    ("мосводоканал", "utilities", "merchant", "expense"),
    ("моэк", "utilities", "merchant", "expense"),
    ("мосгаз", "utilities", "merchant", "expense"),
    ("мособлеирц", "utilities", "merchant", "expense"),
    ("SBERCHAEVYE", "utilities", "merchant", "expense"),
    ("MTS", "utilities", "merchant", "expense"),
    ("BEELINE", "utilities", "merchant", "expense"),
    ("MEGAFON", "utilities", "merchant", "expense"),
    ("TELE2", "utilities", "merchant", "expense"),
    ("ROSTELECOM", "utilities", "merchant", "expense"),
    ("DOM.RU", "utilities", "merchant", "expense"),
    ("TTK", "utilities", "merchant", "expense"),
    ("NETBYNET", "utilities", "merchant", "expense"),
    ("MOSENERGOSBYT", "utilities", "merchant", "expense"),
    ("MOSVODOKANAL", "utilities", "merchant", "expense"),
    ("MOEK", "utilities", "merchant", "expense"),
    ("MOSGAZ", "utilities", "merchant", "expense"),
    ("MOBILNIK", "utilities", "merchant", "expense"),

    # ==================== ОБРАЗОВАНИЕ ====================
    ("образование", "education", "category", "expense"),
    ("education", "education", "both", "expense"),
    ("курсы", "education", "both", "expense"),
    ("университет", "education", "merchant", "expense"),
    ("школа", "education", "merchant", "expense"),
    ("репетитор", "education", "merchant", "expense"),
    ("skillbox", "education", "merchant", "expense"),
    ("skillfactory", "education", "merchant", "expense"),
    ("netology", "education", "merchant", "expense"),
    ("geekbrains", "education", "merchant", "expense"),
    ("яндекс практикум", "education", "merchant", "expense"),
    ("stepik", "education", "merchant", "expense"),
    ("дополнительное", "education", "both", "expense"),

    # ==================== РАЗВЛЕЧЕНИЯ ====================
    ("cinema", "entertainment", "merchant", "expense"),
    ("entertainment", "entertainment", "both", "expense"),
    ("кинотеатр", "entertainment", "merchant", "expense"),
    ("кино", "entertainment", "both", "expense"),
    ("каро", "entertainment", "merchant", "expense"),
    ("синема парк", "entertainment", "merchant", "expense"),
    ("формула кино", "entertainment", "merchant", "expense"),
    ("окко", "entertainment", "merchant", "expense"),
    ("театр", "entertainment", "merchant", "expense"),
    ("концерт", "entertainment", "both", "expense"),
    ("игры", "entertainment", "both", "expense"),
    ("steam", "entertainment", "merchant", "expense"),
    ("playstation", "entertainment", "merchant", "expense"),
    ("xbox", "entertainment", "merchant", "expense"),
    ("epic games", "entertainment", "merchant", "expense"),
    ("nintendo", "entertainment", "merchant", "expense"),
    ("CINEMA", "entertainment", "merchant", "expense"),
    ("KINO", "entertainment", "both", "expense"),
    ("KARO", "entertainment", "merchant", "expense"),
    ("SINEMA PARK", "entertainment", "merchant", "expense"),
    ("FORMULA KINO", "entertainment", "merchant", "expense"),
    ("STEAM", "entertainment", "merchant", "expense"),
    ("PLAYSTATION", "entertainment", "merchant", "expense"),
    ("XBOX", "entertainment", "merchant", "expense"),
    ("EPIC GAMES", "entertainment", "merchant", "expense"),
    ("NINTENDO", "entertainment", "merchant", "expense"),
    ("VK", "entertainment", "merchant", "expense"),
    ("VK.COM", "entertainment", "merchant", "expense"),

    # ==================== ПЛАТЕЖИ, БАНК, КРЕДИТЫ ====================
    ("тинькофф", "bank_payments", "both", "expense"),
    ("tinkoff", "bank_payments", "both", "expense"),
    ("сбербанк", "bank_payments", "both", "expense"),
    ("sberbank", "bank_payments", "both", "expense"),
    ("альфа-банк", "bank_payments", "both", "expense"),
    ("alfa-bank", "bank_payments", "both", "expense"),
    ("втб", "bank_payments", "both", "expense"),
    ("vtb", "bank_payments", "both", "expense"),
    ("открытие", "bank_payments", "both", "expense"),
    ("открытие", "bank_payments", "both", "expense"),
    ("райффайзен", "bank_payments", "both", "expense"),
    ("raiffeisen", "bank_payments", "both", "expense"),
    ("комиссия", "fees", "both", "expense"),
    ("обслуживание", "fees", "both", "expense"),
    ("страхование", "insurance", "both", "expense"),
    ("кредит", "loans", "both", "expense"),
    ("налог", "taxes", "both", "expense"),
    ("пеня", "fines", "both", "expense"),
    ("SBERBANK ONL@IN", "bank_payments", "merchant", "expense"),
    ("TINKOFF", "bank_payments", "merchant", "expense"),
    ("ALFA-BANK", "bank_payments", "merchant", "expense"),
    ("VTB", "bank_payments", "merchant", "expense"),
    ("OTKRITIE", "bank_payments", "merchant", "expense"),
    ("RAIFFEISEN", "bank_payments", "merchant", "expense"),
    ("KOPILKA KARTA-VKLAD", "bank_payments", "merchant", "expense"),
    ("MOBILE BANK: KOMISSIYA", "fees", "merchant", "expense"),
    ("3815 Design Charge", "fees", "merchant", "expense"),

    # ==================== ОБЩИЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ РАСХОДОВ ====================
    ("покупка", "shopping", "both", "expense"),
    ("оплата", "shopping", "both", "expense"),
    ("пополнение", "income", "both", "income"), 
    ("снятие", "cash_out", "both", "expense"),
    ("выдача", "cash_out", "both", "expense"),
    ("списание", "shopping", "both", "expense"),
    ("платеж", "shopping", "both", "expense"),
    ("сервис", "services", "both", "expense"),
    ("услуга", "services", "both", "expense"),

    # ==================== МАРКЕТПЛЕЙСЫ И СЕРВИСЫ ====================
    ("avito", "shopping", "merchant", "any"),
    ("юла", "shopping", "merchant", "any"),
    ("беру", "shopping", "merchant", "any"),
    ("goods", "shopping", "merchant", "any"),
    ("kupivip", "shopping", "merchant", "any"),
    ("toy.ru", "shopping", "merchant", "any"),
    ("м.видео", "electronics", "merchant", "any"),
    ("eldorado", "electronics", "merchant", "any"),
    ("dns", "electronics", "merchant", "any"),
    ("citilink", "electronics", "merchant", "any"),
    ("media markt", "electronics", "merchant", "any"),
    ("technopark", "electronics", "merchant", "any"),
    ("ozon fresh", "groceries", "merchant", "any"),
    ("сбермаркет", "groceries", "merchant", "any"),
    ("sbermarket", "groceries", "merchant", "any"),
    ("самокат", "groceries", "merchant", "any"),
    ("samokat", "groceries", "merchant", "any"),
    ("яндекс лавка", "groceries", "merchant", "any"),
    ("yandex lavka", "groceries", "merchant", "any"),
    ("доставка", "shopping", "both", "any"),

    # ==================== ДОПОЛНИТЕЛЬНЫЕ РЕСТОРАНЫ / ФАСТФУД ====================
    ("роллтон", "food", "merchant", "expense"),
    ("якитория", "food", "merchant", "expense"),
    ("якита", "food", "merchant", "expense"),
    ("суши маркет", "food", "merchant", "expense"),
    ("sushi market", "food", "merchant", "expense"),
    ("tanuki", "food", "merchant", "expense"),
    ("тануки", "food", "merchant", "expense"),
    ("шоколадница", "food", "merchant", "expense"),
    ("кофе хауз", "food", "merchant", "expense"),
    ("coffee house", "food", "merchant", "expense"),
    ("даблби", "food", "merchant", "expense"),
    ("doubleby", "food", "merchant", "expense"),
    ("буше", "food", "merchant", "expense"),
    ("bouchée", "food", "merchant", "expense"),

    # ==================== ТРАНСПОРТНЫЕ КОМПАНИИ, КАРТЫ ====================
    ("тройка", "transport", "merchant", "expense"),
    ("стрелка", "transport", "merchant", "expense"),
    ("подорожник", "transport", "merchant", "expense"),
    ("цппк", "transport", "merchant", "expense"),
    ("аэроэкспресс", "transport", "merchant", "expense"),
    ("аэроэкспресс", "transport", "merchant", "expense"),
    ("московский паркинг", "parking", "merchant", "expense"),
    ("parking russia", "parking", "merchant", "expense"),
    ("штраф гибдд", "fines", "both", "expense"),

    # ==================== ЗДОРОВЬЕ (АПТЕКИ, КЛИНИКИ) ====================
    ("аптека", "health", "merchant", "expense"),
    ("apteka", "health", "merchant", "expense"),
    ("апрель", "health", "merchant", "expense"),
    ("горздрав", "health", "merchant", "expense"),
    ("zdravcity", "health", "merchant", "expense"),
    ("36.6", "health", "merchant", "expense"),
    ("медси", "health", "merchant", "expense"),
    ("medsi", "health", "merchant", "expense"),
    ("инвитро", "health", "merchant", "expense"),
    ("invitro", "health", "merchant", "expense"),
    ("гемотест", "health", "merchant", "expense"),
    ("gemotest", "health", "merchant", "expense"),
    ("стоматология", "health", "merchant", "expense"),
    ("dentistry", "health", "merchant", "expense"),

    # ==================== КРАСОТА ====================
    ("золотое яблоко", "beauty", "merchant", "expense"),
    ("лэтуаль", "beauty", "merchant", "expense"),
    ("рив гош", "beauty", "merchant", "expense"),
    ("салон красоты", "beauty", "merchant", "expense"),
    ("парикмахер", "beauty", "merchant", "expense"),
    ("barbershop", "beauty", "merchant", "expense"),
    ("ногти", "beauty", "merchant", "expense"),
    ("маникюр", "beauty", "merchant", "expense"),
    ("pedicure", "beauty", "merchant", "expense"),

    # ==================== СПОРТ ====================
    ("спортзал", "sports", "merchant", "expense"),
    ("фитнес", "sports", "merchant", "expense"),
    ("gym", "sports", "merchant", "expense"),
    ("world class", "sports", "merchant", "expense"),
    ("x-fit", "sports", "merchant", "expense"),
    ("fitness house", "sports", "merchant", "expense"),
    ("бассейн", "sports", "merchant", "expense"),
    ("pool", "sports", "merchant", "expense"),
    ("йога", "sports", "merchant", "expense"),
    ("yoga", "sports", "merchant", "expense"),

    # ==================== ДОМАШНИЕ ЖИВОТНЫЕ ====================
    ("зоомагазин", "shopping", "merchant", "expense"),
    ("зоо", "shopping", "merchant", "expense"),
    ("pet shop", "shopping", "merchant", "expense"),
    ("ветеринар", "health", "merchant", "expense"),
    ("ветклиника", "health", "merchant", "expense"),
    ("корм", "groceries", "both", "expense"),

    # ==================== ПРОЧЕЕ ====================
    ("LGS", "shopping", "merchant", "expense"),   # магазин LGS (продукты)
    ("OnliPay", "shopping", "merchant", "expense"),
    ("SBSCR_Сервисы Яндекса", "shopping", "merchant", "expense"),
    ("HATIMAKI.RU", "food", "merchant", "expense"),
    ("NN.KASSIR", "entertainment", "merchant", "expense"),
    ("CoolClever", "shopping", "merchant", "expense"),
    ("FUNPAY", "entertainment", "merchant", "expense"),
    ("Kupikod", "shopping", "merchant", "expense"),
    ("TOME TRANSFER LTD", "fees", "merchant", "expense"),
    ("OOO KODEKS", "shopping", "merchant", "expense"),
    ("ATM", "cash_out", "merchant", "expense"),
    ("АВТОМАТ", "cash_out", "merchant", "expense"),
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
