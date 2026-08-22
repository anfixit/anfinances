"""Бизнес-логика получателей.

Правила:
- Имя уникально без учёта регистра: «Пятёрочка» и «ПЯТЕРОЧКА» —
  один получатель, потому что в выписках регистр пляшет.
- Получатель заводится сам, как только имя впервые встретилось в
  операции: заставлять заводить его вручную — верный способ, чтобы
  им никогда не пользовались.
- Категория последней операции запоминается и подставляется в
  следующий раз. Это и есть смысл всей затеи: выписку разносит
  таблица, а не модель.
- Удаление — настоящее, не архив: у получателя нет истории, которую
  надо беречь, а операции просто теряют ссылку.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.domains.payees.models import Payee
from app.domains.payees.repository import PayeeRepository
from app.domains.payees.schemas import PayeeCreate, PayeeUpdate

__all__ = ["NEW_PAYEE_WINDOW", "PayeeService", "payee_key"]

# Сколько получатель считается новым. Месяц: за меньший срок
# подписка не успеет списаться второй раз и не будет замечена.
NEW_PAYEE_WINDOW = timedelta(days=31)


def payee_key(name: str) -> str:
    """Свёрнутое имя, по которому получатели считаются одним.

    casefold, а не lower: он единственный правильно сворачивает
    регистр во всех алфавитах. Внутренние пробелы схлопываются —
    в выписках между словами то один пробел, то три.
    """
    return " ".join(name.split()).casefold()


def _aware(value: datetime) -> datetime:
    """Дата из БД в UTC-осознанном виде.

    PostgreSQL отдаёт время с зоной, SQLite в тестах — без. Сравнивать
    их напрямую нельзя, а падать из-за профиля базы — тем более.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class PayeeService:
    def __init__(self, repo: PayeeRepository) -> None:
        self._repo = repo

    async def list_payees(self, user_id: uuid.UUID) -> list[Payee]:
        return await self._repo.list_all(user_id)

    async def get_payee(
        self, payee_id: uuid.UUID, user_id: uuid.UUID
    ) -> Payee:
        payee = await self._repo.get(payee_id, user_id)
        if payee is None:
            raise NotFoundError("Получатель не найден.")
        return payee

    async def create_payee(
        self, user_id: uuid.UUID, data: PayeeCreate
    ) -> Payee:
        name = " ".join(data.name.split())
        if await self._repo.get_by_key(user_id, payee_key(name)) is not None:
            raise AlreadyExistsError(f"Получатель «{name}» уже есть.")
        return await self._repo.add(
            Payee(user_id=user_id, name=name, name_key=payee_key(name))
        )

    async def ensure(self, user_id: uuid.UUID, name: str) -> Payee:
        """Найти получателя по имени или завести нового.

        Вызывается при записи операции: имя приходит из выписки или
        из фразы, и требовать, чтобы получатель уже существовал,
        значило бы ронять запись из-за справочника.
        """
        cleaned = " ".join(name.split())
        key = payee_key(cleaned)
        existing = await self._repo.get_by_key(user_id, key)
        if existing is not None:
            return existing
        return await self._repo.add(
            Payee(user_id=user_id, name=cleaned, name_key=key)
        )

    async def update_payee(
        self, payee_id: uuid.UUID, user_id: uuid.UUID, data: PayeeUpdate
    ) -> Payee:
        payee = await self.get_payee(payee_id, user_id)
        if data.name is not None:
            name = " ".join(data.name.split())
            key = payee_key(name)
            clash = await self._repo.get_by_key(user_id, key)
            if clash is not None and clash.id != payee.id:
                raise AlreadyExistsError(
                    f"Получатель «{name}» уже есть — слейте их."
                )
            payee.name = name
            payee.name_key = key
        return payee

    async def merge_payees(
        self, source_id: uuid.UUID, target_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        """Слить одного получателя в другого.

        Один магазин приезжает из разных выписок под разными именами
        («WILDBERRIES» и «Wildberries RU»). Переименование тут не
        поможет — имена заняты обоими, поэтому операции перевешиваем
        и лишнюю запись убираем.
        """
        if source_id == target_id:
            raise NotFoundError("Получатели совпадают — сливать нечего.")
        source = await self.get_payee(source_id, user_id)
        target = await self.get_payee(target_id, user_id)
        moved = await self._repo.reassign(source.id, target.id)
        if target.last_category_id is None:
            target.last_category_id = source.last_category_id
        await self._repo.delete(source)
        return moved

    async def delete_payee(
        self, payee_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        payee = await self.get_payee(payee_id, user_id)
        await self._repo.delete(payee)

    async def new_payees(
        self, user_id: uuid.UUID, now: datetime
    ) -> list[tuple[Payee, datetime]]:
        """Получатели, впервые встретившиеся за последний месяц.

        Считаем по дате первой операции, а не по дате заведения
        записи: выписку заносят задним числом, и запись появляется
        сегодня для траты трёхлетней давности.
        """
        seen = await self._repo.first_seen(user_id)
        since = now - NEW_PAYEE_WINDOW
        rows = [
            (payee, _aware(seen[payee.id]))
            for payee in await self._repo.list_all(user_id)
            if payee.id in seen and _aware(seen[payee.id]) >= since
        ]
        rows.sort(key=lambda row: row[1], reverse=True)
        return rows
