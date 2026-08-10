"""Выбор счёта для операции (решение Р-6).

Цена ошибки со счётом выше, чем с категорией: неправильная категория
портит отчёт и это заметно, неправильный счёт разводит баланс с
реальностью и обнаруживается через неделю. Поэтому когда уверенности
нет — спрашиваем кнопками, а не угадываем.
"""

from dataclasses import dataclass

from anfinances_bot.anfinances.schemas import AccountRead

__all__ = ["AccountResolution", "resolve_account"]


@dataclass(frozen=True)
class AccountResolution:
    """Либо счёт выбран, либо надо показать ``candidates`` кнопками."""

    account: AccountRead | None
    candidates: list[AccountRead]


def resolve_account(
    accounts: list[AccountRead],
    *,
    named: str | None,
    currency_code: str | None,
    history_account_id: str | None,
    default_names: dict[str, str],
) -> AccountResolution:
    """Разрешить счёт по пяти правилам сверху вниз.

    Первое сработавшее правило выигрывает. Если не сработало ни одно —
    возвращаем кандидатов, чтобы спросить пользователя кнопками.

    ``default_names`` — умолчания по валютам: ``{"RUB": "Альфа", ...}``.
    Одного умолчания на всё не хватает: у владельца счета в трёх
    валютах, и рублёвое умолчание не помогло бы ни сумам, ни долларам.
    """
    # 1. Счёт назван во фразе: «со сбера», «альфа картой», «наличными».
    #    Сначала точное имя, потом единственное вхождение подстроки.
    #    Неоднозначную подстроку не разрешаем: «Капитал» подходит трём
    #    счетам, и взять первый попавшийся — тихо ошибиться.
    if named:
        picked = _by_name(accounts, named)
        if picked is not None:
            return AccountResolution(picked, [])

    in_currency = [
        a
        for a in accounts
        if currency_code is None or a.currency_code == currency_code
    ]

    # 2. В этой валюте счёт ровно один — гадать не о чем.
    if len(in_currency) == 1:
        return AccountResolution(in_currency[0], [])

    # 3. История по категории указывает на счёт нужной валюты.
    if history_account_id is not None:
        for account in in_currency:
            if account.id == history_account_id:
                return AccountResolution(account, [])

    # 4. Умолчание для валюты операции. Имя сверяется целиком:
    #    «Альфа» не должна цеплять «Альфа Бизнес».
    if currency_code is not None:
        wanted = default_names.get(currency_code)
        if wanted:
            needle = wanted.casefold()
            for account in in_currency:
                if account.name.casefold() == needle:
                    return AccountResolution(account, [])

    # 5. Ничего не помогло — пусть выберет пользователь.
    return AccountResolution(None, in_currency)


def _by_name(accounts: list[AccountRead], named: str) -> AccountRead | None:
    """Найти счёт по названному имени: точное, затем однозначное."""
    needle = named.casefold()

    for account in accounts:
        if account.name.casefold() == needle:
            return account

    matches = [a for a in accounts if needle in a.name.casefold()]
    return matches[0] if len(matches) == 1 else None
