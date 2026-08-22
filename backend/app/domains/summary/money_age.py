"""Возраст денег: сколько дней пролежал рубль, прежде чем его потратили.

Четвёртое правило ВНБ измеряется числом, а не галочкой «покрыто /
не покрыто». Галочка не растёт: она либо есть, либо нет, и по ней
не видно, стало ли лучше за месяц.

Считается так же, как в YNAB: доходы и расходы выстраиваются в
очередь по времени, каждый расход оплачивается самым старым ещё не
потраченным доходом (FIFO), и возраст — это средневзвешенная
задержка между приходом рубля и его тратой. Берутся последние
несколько расходов: месячной давности показатель ничего не говорит
о сегодняшних привычках.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

__all__ = ["AGE_WINDOW", "Flow", "age_of_money"]

# Сколько последних расходов усредняем. Десять — как в YNAB: меньше
# скачет от одной крупной покупки, но ещё отражает этот месяц.
AGE_WINDOW = 10


@dataclass(frozen=True, slots=True)
class Flow:
    """Движение денег: положительное — приход, отрицательное — расход."""

    at: datetime
    amount: Decimal


def age_of_money(flows: list[Flow], window: int = AGE_WINDOW) -> int | None:
    """Средний возраст потраченных денег в днях.

    None — если тратить было нечего или не из чего: у новой базы
    возраст не «ноль дней», его просто ещё нет.
    """
    incoming: deque[tuple[datetime, Decimal]] = deque()
    ages: list[tuple[Decimal, Decimal]] = []

    for flow in sorted(flows, key=lambda f: f.at):
        if flow.amount > 0:
            incoming.append((flow.at, flow.amount))
            continue

        need = -flow.amount
        while need > 0 and incoming:
            came_at, available = incoming[0]
            used = min(need, available)
            days = Decimal((flow.at - came_at).days)
            # Взвешиваем суммой: крупная покупка со старых денег
            # значит больше, чем мелкая со свежих.
            ages.append((used, days))
            need -= used
            if used == available:
                incoming.popleft()
            else:
                incoming[0] = (came_at, available - used)

    if not ages:
        return None

    recent = ages[-window:]
    total = sum((amount for amount, _ in recent), start=Decimal(0))
    if total == 0:
        return None
    weighted = sum((amount * days for amount, days in recent), Decimal(0))
    return int(weighted / total)
