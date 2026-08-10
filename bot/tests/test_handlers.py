"""Обработчики: карточка, кнопки, отказы, продолжение разговора."""

from dataclasses import dataclass, field
from typing import Any

from anfinances_bot.agent.runner import AgentReply, AgentUnavailableError
from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.speech import SpeechUnavailableError
from anfinances_bot.telegram.handlers import (
    Session,
    handle_callback,
    handle_user_text,
    handle_user_voice,
)


@dataclass
class _Sent:
    text: str
    markup: Any = None


@dataclass
class _Message:
    text: str
    sent: list[_Sent] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None) -> None:
        self.sent.append(_Sent(text, reply_markup))


@dataclass
class _Callback:
    data: str
    message: _Message
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "") -> None:
        self.answered.append(text)


class _Deps:
    def __init__(self, reply: Any) -> None:
        self._reply = reply
        self.seen: list[tuple[str, list[dict[str, Any]]]] = []

    async def resolve(
        self, text: str, history: list[dict[str, Any]]
    ) -> AgentReply:
        self.seen.append((text, list(history)))
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


async def test_created_transaction_gets_card() -> None:
    message = _Message("кофе 300")
    deps = _Deps(
        AgentReply(
            text="Записала: Еда → Кофейни — 300 ₽",
            created_transaction_id="tx-1",
        )
    )
    await handle_user_text(message, deps, Session())
    assert "Кофейни" in message.sent[0].text
    assert message.sent[0].markup is not None


async def test_pending_accounts_get_buttons() -> None:
    message = _Message("потратила 20 евро")
    deps = _Deps(
        AgentReply(
            text="С какого счёта?",
            pending_accounts=[
                AccountRead(id="e-1", name="EUR A", currency_code="EUR")
            ],
        )
    )
    session = Session()
    await handle_user_text(message, deps, session)
    assert message.sent[0].markup is not None
    # Кнопка присылает id — имя для агента берём отсюда.
    assert session.pending_accounts[0].name == "EUR A"


async def test_plain_answer_has_no_markup() -> None:
    message = _Message("сколько осталось")
    deps = _Deps(AgentReply(text="Всего 15 000 ₽"))
    await handle_user_text(message, deps, Session())
    assert message.sent[0].markup is None


async def test_site_down_is_reported_honestly() -> None:
    message = _Message("кофе 300")
    deps = _Deps(AnfinancesUnavailableError("нет сети"))
    await handle_user_text(message, deps, Session())
    assert "не смогла записать" in message.sent[0].text.casefold()


async def test_model_down_suggests_web() -> None:
    message = _Message("кофе 300")
    deps = _Deps(AgentUnavailableError("недоступна"))
    await handle_user_text(message, deps, Session())
    assert "через сайт" in message.sent[0].text.casefold()


async def test_api_error_text_is_surfaced() -> None:
    message = _Message("кофе 300")
    deps = _Deps(AnfinancesError("Сумма должна быть больше нуля."))
    await handle_user_text(message, deps, Session())
    assert "больше нуля" in message.sent[0].text


async def test_history_carries_the_previous_turn() -> None:
    """«А на сбере?» без истории — бессмысленный вопрос."""
    session = Session()
    deps = _Deps(AgentReply(text="145,34 ₽"))
    await handle_user_text(_Message("сколько на альфе"), deps, session)
    await handle_user_text(_Message("а на сбере"), deps, session)

    _, history = deps.seen[1]
    assert history[0] == {"role": "user", "content": "сколько на альфе"}
    assert history[1] == {"role": "assistant", "content": "145,34 ₽"}


async def test_history_is_trimmed() -> None:
    session = Session()
    deps = _Deps(AgentReply(text="ок"))
    for _ in range(20):
        await handle_user_text(_Message("привет"), deps, session)
    assert len(session.history) <= Session.MAX_HISTORY


async def test_failed_turn_is_not_remembered() -> None:
    """Ответа не было — незачем засорять им контекст."""
    session = Session()
    deps = _Deps(AgentUnavailableError("недоступна"))
    await handle_user_text(_Message("кофе 300"), deps, session)
    assert session.history == []


async def test_delete_button_removes_transaction() -> None:
    callback = _Callback("del:tx-1", _Message(""))
    deps = _Deps(AgentReply(text="Операция удалена."))
    await handle_callback(callback, deps, Session())
    text, _ = deps.seen[0]
    assert "tx-1" in text
    assert "удали" in text.casefold()


async def test_fix_button_asks_what_to_change() -> None:
    session = Session()
    callback = _Callback("fix:tx-1", _Message(""))
    deps = _Deps(AgentReply(text="неважно"))
    await handle_callback(callback, deps, session)
    assert deps.seen == []
    assert session.pending_fix_id == "tx-1"
    assert "исправить" in callback.message.sent[0].text.casefold()


async def test_next_message_after_fix_names_the_transaction() -> None:
    session = Session(pending_fix_id="tx-1")
    deps = _Deps(AgentReply(text="Исправила."))
    await handle_user_text(_Message("это был транспорт"), deps, session)

    text, _ = deps.seen[0]
    assert "tx-1" in text
    assert "это был транспорт" in text
    assert session.pending_fix_id is None


async def test_account_button_sends_the_name_not_the_id() -> None:
    session = Session(
        pending_accounts=[
            AccountRead(id="a-2", name="Сбер", currency_code="RUB")
        ]
    )
    callback = _Callback("acc:a-2", _Message(""))
    deps = _Deps(AgentReply(text="Записала", created_transaction_id="tx-2"))
    await handle_callback(callback, deps, session)

    text, _ = deps.seen[0]
    assert "Сбер" in text
    assert session.pending_accounts == []


async def test_unknown_callback_is_ignored_quietly() -> None:
    callback = _Callback("мусор", _Message(""))
    deps = _Deps(AgentReply(text="неважно"))
    await handle_callback(callback, deps, Session())
    assert deps.seen == []


async def test_voice_failure_asks_for_text() -> None:
    message = _Message("")

    async def _failing(_: Any) -> str:
        raise SpeechUnavailableError("нет сети")

    await handle_user_voice(
        message, _Deps(AgentReply(text="")), Session(), _failing
    )
    assert "текстом" in message.sent[0].text.casefold()


async def test_voice_success_goes_through_text_path() -> None:
    message = _Message("")
    deps = _Deps(AgentReply(text="Записала", created_transaction_id="tx-1"))

    async def _ok(_: Any) -> str:
        return "кофе 300"

    await handle_user_voice(message, deps, Session(), _ok)
    assert "Услышала" in message.sent[0].text
    assert message.sent[1].markup is not None
