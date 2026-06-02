"""сид справочника валют

Revision ID: a1c0ffee5eed
Revises: 81077d778841
Create Date: 2026-06-02 07:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c0ffee5eed"
down_revision: str | Sequence[str] | None = "81077d778841"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_currencies = sa.table(
    "currencies",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("symbol", sa.String),
    sa.column("decimals", sa.Integer),
)

_CURRENCIES: list[dict[str, str | int]] = [
    {"code": "RUB", "name": "Российский рубль", "symbol": "₽", "decimals": 2},
    {"code": "USD", "name": "Доллар США", "symbol": "$", "decimals": 2},
    {"code": "EUR", "name": "Евро", "symbol": "€", "decimals": 2},
    {"code": "GBP", "name": "Фунт стерлингов", "symbol": "£", "decimals": 2},
    {"code": "TRY", "name": "Турецкая лира", "symbol": "₺", "decimals": 2},
    {"code": "THB", "name": "Тайский бат", "symbol": "฿", "decimals": 2},
    {
        "code": "KZT",
        "name": "Казахстанский тенге",
        "symbol": "₸",
        "decimals": 2,
    },
    {
        "code": "BYN",
        "name": "Белорусский рубль",
        "symbol": "Br",
        "decimals": 2,
    },
    {"code": "UZS", "name": "Узбекский сум", "symbol": "сўм", "decimals": 2},
    {"code": "GEL", "name": "Грузинский лари", "symbol": "₾", "decimals": 2},
    {"code": "AMD", "name": "Армянский драм", "symbol": "֏", "decimals": 2},
    {
        "code": "AZN",
        "name": "Азербайджанский манат",
        "symbol": "₼",
        "decimals": 2,
    },
    {"code": "KGS", "name": "Киргизский сом", "symbol": "с", "decimals": 2},
    {
        "code": "TJS",
        "name": "Таджикский сомони",
        "symbol": "SM",
        "decimals": 2,
    },
    {"code": "MDL", "name": "Молдавский лей", "symbol": "L", "decimals": 2},
    {"code": "UAH", "name": "Украинская гривна", "symbol": "₴", "decimals": 2},
    {"code": "CNY", "name": "Китайский юань", "symbol": "¥", "decimals": 2},
    {"code": "AED", "name": "Дирхам ОАЭ", "symbol": "د.إ", "decimals": 2},
    {"code": "INR", "name": "Индийская рупия", "symbol": "₹", "decimals": 2},
    {
        "code": "IDR",
        "name": "Индонезийская рупия",
        "symbol": "Rp",
        "decimals": 2,
    },
    {"code": "VND", "name": "Вьетнамский донг", "symbol": "₫", "decimals": 0},
    {
        "code": "MYR",
        "name": "Малайзийский ринггит",
        "symbol": "RM",
        "decimals": 2,
    },
    {
        "code": "SGD",
        "name": "Сингапурский доллар",
        "symbol": "S$",
        "decimals": 2,
    },
    {
        "code": "HKD",
        "name": "Гонконгский доллар",
        "symbol": "HK$",
        "decimals": 2,
    },
    {"code": "JPY", "name": "Японская иена", "symbol": "¥", "decimals": 0},
    {
        "code": "KRW",
        "name": "Южнокорейская вона",
        "symbol": "₩",
        "decimals": 0,
    },
    {
        "code": "CHF",
        "name": "Швейцарский франк",
        "symbol": "CHF",
        "decimals": 2,
    },
    {"code": "PLN", "name": "Польский злотый", "symbol": "zł", "decimals": 2},
    {"code": "CZK", "name": "Чешская крона", "symbol": "Kč", "decimals": 2},
    {
        "code": "HUF",
        "name": "Венгерский форинт",
        "symbol": "Ft",
        "decimals": 0,
    },
    {"code": "SEK", "name": "Шведская крона", "symbol": "kr", "decimals": 2},
    {"code": "NOK", "name": "Норвежская крона", "symbol": "kr", "decimals": 2},
    {"code": "DKK", "name": "Датская крона", "symbol": "kr", "decimals": 2},
    {"code": "RON", "name": "Румынский лей", "symbol": "lei", "decimals": 2},
    {"code": "BGN", "name": "Болгарский лев", "symbol": "лв", "decimals": 2},
    {"code": "RSD", "name": "Сербский динар", "symbol": "дин", "decimals": 2},
    {
        "code": "BAM",
        "name": "Конвертируемая марка БиГ",
        "symbol": "KM",
        "decimals": 2,
    },
    {
        "code": "MKD",
        "name": "Македонский денар",
        "symbol": "ден",
        "decimals": 2,
    },
    {"code": "ALL", "name": "Албанский лек", "symbol": "L", "decimals": 2},
    {"code": "EGP", "name": "Египетский фунт", "symbol": "E£", "decimals": 2},
    {
        "code": "ILS",
        "name": "Израильский шекель",
        "symbol": "₪",
        "decimals": 2,
    },
    {
        "code": "AUD",
        "name": "Австралийский доллар",
        "symbol": "A$",
        "decimals": 2,
    },
    {"code": "CAD", "name": "Канадский доллар", "symbol": "C$", "decimals": 2},
    {"code": "SAR", "name": "Саудовский риял", "symbol": "﷼", "decimals": 2},
    {"code": "QAR", "name": "Катарский риал", "symbol": "QR", "decimals": 2},
    {"code": "OMR", "name": "Оманский риал", "symbol": "ر.ع.", "decimals": 3},
    {
        "code": "BHD",
        "name": "Бахрейнский динар",
        "symbol": ".د.ب",
        "decimals": 3,
    },
    {
        "code": "KWD",
        "name": "Кувейтский динар",
        "symbol": "د.ك",
        "decimals": 3,
    },
]


def upgrade() -> None:
    op.bulk_insert(_currencies, _CURRENCIES)


def downgrade() -> None:
    codes = tuple(c["code"] for c in _CURRENCIES)
    op.execute(_currencies.delete().where(_currencies.c.code.in_(codes)))
