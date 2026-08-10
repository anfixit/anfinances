"""Белый список: чужие не доходят до обработчика."""

from dataclasses import dataclass, field
from typing import Any

from anfinances_bot.telegram.access import AllowlistMiddleware


@dataclass
class _User:
    id: int


@dataclass
class _Event:
    from_user: _User | None
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.answers.append(text)


async def _handler(event: Any, data: dict[str, Any]) -> str:
    return "обработано"


async def test_allowed_user_passes() -> None:
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=_User(id=111))
    assert await middleware(_handler, event, {}) == "обработано"
    assert event.answers == []


async def test_foreign_user_blocked() -> None:
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=_User(id=999))
    assert await middleware(_handler, event, {}) is None
    assert len(event.answers) == 1


async def test_event_without_user_blocked() -> None:
    """Без отправителя пропускать нельзя — это не личный чат."""
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=None)
    assert await middleware(_handler, event, {}) is None


async def test_several_allowed_ids() -> None:
    middleware = AllowlistMiddleware(frozenset({111, 222}))
    for user_id in (111, 222):
        event = _Event(from_user=_User(id=user_id))
        assert await middleware(_handler, event, {}) == "обработано"


async def test_blocked_event_without_answer_does_not_crash() -> None:
    """У некоторых типов событий нет .answer — не должно падать."""

    @dataclass
    class _Bare:
        from_user: _User

    middleware = AllowlistMiddleware(frozenset({111}))
    assert await middleware(_handler, _Bare(_User(id=999)), {}) is None
