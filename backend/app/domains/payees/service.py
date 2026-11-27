"""Бизнес-логика получателей.

Правила:
- Имя уникально без учёта регистра: «Пятёрочка» и «ПЯТЕРОЧКА» —
  один получатель, потому что в выписках регистр пляшет.
- Невиданное имя в справочник само не попадает: оно ждёт в списке
  кандидатов, пока владелица не подтвердит его. Иначе справочник
  заполняют люди из переводов и слова из назначения платежа.
- Категория последней операции запоминается и подставляется в
  следующий раз. Это и есть смысл всей затеи: выписку разносит
  таблица, а не модель.
- Удаление — настоящее, не архив: у получателя нет истории, которую
  надо беречь, а операции просто теряют ссылку.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.domains.payees.keys import payee_key
from app.domains.payees.models import Payee, PayeeCandidate
from app.domains.payees.repository import PayeeRepository
from app.domains.payees.schemas import PayeeCreate, PayeeUpdate

__all__ = ["PayeeService", "is_marketplace", "payee_key"]

# Маркетплейсы продают всё подряд — категория у них зависит от товара,
# а не от магазина. Помечаются «разными категориями» сами, при первой
# встрече: из выписки они приходят под именами вроде «OZON.RU».
_MARKETPLACES = (
    "ozon",
    "озон",
    "wildberries",
    "вайлдберриз",
    "яндекс маркет",
    "яндекс.маркет",
    "yandex market",
    "market.yandex",
    "aliexpress",
    "алиэкспресс",
    "мегамаркет",
    "megamarket",
)


def is_marketplace(name: str) -> bool:
    folded = name.casefold()
    return any(mark in folded for mark in _MARKETPLACES)


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

    async def remember(
        self, user_id: uuid.UUID, name: str
    ) -> tuple[Payee | None, str]:
        """Сопоставить имя из операции со справочником.

        Возвращает подтверждённого получателя (или None) и очищенное
        имя для снимка в операции. Новый получатель здесь не
        заводится: имя из выписки бывает человеком из перевода или
        словом из назначения платежа, и справочник, куда попадает всё
        подряд, перестаёт быть справочником. Невиданное имя копится
        как кандидат и ждёт, пока владелица его подтвердит.
        """
        cleaned = " ".join(name.split())
        if not cleaned:
            # Пустое имя — «получателя тут нет»: ни запись, ни
            # кандидат из него не получатся.
            return None, ""
        key = payee_key(cleaned)
        existing = await self._repo.get_by_key(user_id, key)
        if existing is not None:
            return existing, existing.name
        candidate = await self._repo.get_candidate(user_id, key)
        now = datetime.now(UTC)
        if candidate is None:
            # Обе даты передаём явно: у колонок есть только
            # server_default, и без значения после flush обращение к
            # ним в async-сессии падает с MissingGreenlet.
            await self._repo.add_candidate(
                PayeeCandidate(
                    user_id=user_id,
                    name=cleaned,
                    name_key=key,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        elif candidate.status != "rejected":
            # Отклонённое имя не трогаем совсем: оно не должно ни
            # возвращаться в очередь, ни расти счётчиком.
            candidate.times_seen += 1
            candidate.last_seen_at = now
        return None, cleaned

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
        if data.varied_categories is not None:
            payee.varied_categories = data.varied_categories
            if data.varied_categories:
                # Отметку ставят именно потому, что память врёт —
                # запомненное стираем сразу.
                payee.last_category_id = None
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
        # Если хоть один из двоих — маркетплейс, то и слитый тоже.
        target.varied_categories = (
            target.varied_categories or source.varied_categories
        )
        if target.varied_categories:
            target.last_category_id = None
        elif target.last_category_id is None:
            target.last_category_id = source.last_category_id
        await self._repo.delete(source)
        return moved

    async def delete_payee(
        self, payee_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Удалить получателя и отклонить его имя.

        Имя на операциях остаётся (снимок), а чтобы следующая выписка
        не завела того же получателя заново и не вернула имя в
        очередь, оно уходит в отклонённые.
        """
        payee = await self.get_payee(payee_id, user_id)
        # Поля забираем до удаления: get_candidate() сбрасывает сессию,
        # и после DELETE на объект полагаться нельзя.
        name = payee.name
        name_key = payee.name_key
        await self._repo.delete(payee)
        candidate = await self._repo.get_candidate(user_id, name_key)
        if candidate is None:
            now = datetime.now(UTC)
            await self._repo.add_candidate(
                PayeeCandidate(
                    user_id=user_id,
                    name=name,
                    name_key=name_key,
                    status="rejected",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            candidate.status = "rejected"

    async def list_candidates(
        self, user_id: uuid.UUID, status: str
    ) -> list[tuple[PayeeCandidate, Decimal]]:
        """Очередь разбора: имя и сумма трат под ним, крупное первым."""
        candidates = await self._repo.list_candidates(user_id, status)
        totals = await self._repo.candidate_totals(
            user_id, [c.name_key for c in candidates]
        )
        rows = [(c, totals.get(c.name_key, Decimal(0))) for c in candidates]
        rows.sort(key=lambda row: row[1], reverse=True)
        return rows

    async def _get_candidate(
        self, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> PayeeCandidate:
        candidate = await self._repo.get_candidate_by_id(candidate_id, user_id)
        if candidate is None:
            raise NotFoundError("Имя не найдено в очереди.")
        return candidate

    async def accept_candidate(
        self,
        candidate_id: uuid.UUID,
        user_id: uuid.UUID,
        payee_id: uuid.UUID | None,
    ) -> Payee:
        """Принять имя: завести получателя или влить в существующего.

        Прежние операции с этим именем перевешиваются на получателя.
        Память категории нового получателя засевается самой свежей из
        них, кроме маркетплейса: у него категория от товара зависит.
        """
        candidate = await self._get_candidate(candidate_id, user_id)
        if payee_id is None:
            taken = await self._repo.get_by_key(user_id, candidate.name_key)
            if taken is not None:
                raise AlreadyExistsError(
                    f"Получатель «{candidate.name}» уже есть."
                )
            payee = await self._repo.add(
                Payee(
                    user_id=user_id,
                    name=candidate.name,
                    name_key=candidate.name_key,
                    varied_categories=is_marketplace(candidate.name),
                )
            )
            _, category_id = await self._repo.reassign_orphans(
                user_id, candidate.name_key, payee.id
            )
            if not payee.varied_categories:
                payee.last_category_id = category_id
        else:
            payee = await self.get_payee(payee_id, user_id)
            await self._repo.reassign_orphans(
                user_id, candidate.name_key, payee.id
            )
        await self._repo.delete_candidate(candidate)
        return payee

    async def reject_candidate(
        self, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        candidate = await self._get_candidate(candidate_id, user_id)
        candidate.status = "rejected"

    async def unreject_candidate(
        self, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        candidate = await self._get_candidate(candidate_id, user_id)
        candidate.status = "pending"
