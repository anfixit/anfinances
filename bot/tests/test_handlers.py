"""Обработчики: карточка, кнопки, отказы, продолжение разговора."""

from dataclasses import dataclass, field
from typing import Any

from anfinances_bot.agent.runner import AgentReply, AgentUnavailableError
from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.documents import Attachment, DocumentUnreadableError
from anfinances_bot.speech import SpeechUnavailableError
from anfinances_bot.telegram.handlers import (
    Session,
    handle_callback,
    handle_user_attachments,
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
        self.images: list[tuple[str, str]] | None = None
        self.pdfs: list[str] | None = None

    async def resolve(
        self,
        text: str,
        history: list[dict[str, Any]],
        images: list[tuple[str, str]] | None = None,
        pdfs: list[str] | None = None,
    ) -> AgentReply:
        self.images = images
        self.pdfs = pdfs
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


@dataclass(frozen=True)
class _FrozenMessage:
    """Как Message в aiogram: присвоить полю нельзя.

    Прежний код после расшифровки писал `message.text = text`, и на
    настоящем сообщении это падало ValidationError уже после ответа
    «Услышала» — голос распознавался, а трата не записывалась.
    """

    text: str
    sent: list[_Sent] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None) -> None:
        self.sent.append(_Sent(text, reply_markup))


async def test_voice_does_not_mutate_the_message() -> None:
    message = _FrozenMessage("")
    deps = _Deps(AgentReply(text="Записала", created_transaction_id="tx-1"))

    async def _ok(_: Any) -> str:
        return "кофе 300 с альфы"

    await handle_user_voice(message, deps, Session(), _ok)

    # Расшифровка обязана дойти до агента, а не осесть в ответе.
    text, _ = deps.seen[0]
    assert "кофе 300 с альфы" in text
    assert message.sent[-1].markup is not None


@dataclass
class _PhotoMessage(_Message):
    caption: str | None = None


async def test_csv_text_reaches_the_agent() -> None:
    message = _PhotoMessage("", caption="выписка за август")
    deps = _Deps(AgentReply(text="Занесено операций: 2."))

    async def _reader(_: Any) -> list[Attachment]:
        return [Attachment(name="vypiska.csv", text="дата;сумма\n01.08;-300")]

    await handle_user_attachments(message, deps, Session(), _reader)

    text, _ = deps.seen[0]
    assert "vypiska.csv" in text
    assert "01.08;-300" in text
    assert "выписка за август" in text


async def test_pdf_and_image_go_as_blocks_not_text() -> None:
    """PDF и скриншот читает модель — в текст их не разворачиваем."""
    message = _PhotoMessage("")
    deps = _Deps(AgentReply(text="Занесено"))

    async def _reader(_: Any) -> list[Attachment]:
        return [
            Attachment(name="statement.pdf", pdf="ПДФ64"),
            Attachment(name="shot.jpg", image=("image/jpeg", "КАРТ64")),
        ]

    await handle_user_attachments(message, deps, Session(), _reader)

    assert deps.pdfs == ["ПДФ64"]
    assert deps.images == [("image/jpeg", "КАРТ64")]


async def test_whole_album_goes_in_one_call() -> None:
    """Четыре файла — один запрос, иначе их не свести между собой."""
    message = _PhotoMessage("")
    deps = _Deps(AgentReply(text="Занесено"))

    async def _reader(_: Any) -> list[Attachment]:
        return [Attachment(name=f"file{i}.pdf", pdf=f"П{i}") for i in range(4)]

    await handle_user_attachments(message, deps, Session(), _reader)

    assert len(deps.seen) == 1
    assert deps.pdfs == ["П0", "П1", "П2", "П3"]


async def test_empty_batch_is_reported() -> None:
    message = _PhotoMessage("")

    async def _reader(_: Any) -> list[Attachment]:
        return []

    await handle_user_attachments(
        message, _Deps(AgentReply(text="")), Session(), _reader
    )
    assert "не нашла" in message.sent[-1].text.casefold()


async def test_attachment_bodies_do_not_stay_in_history() -> None:
    """Base64 и тело выписки уезжали бы в модель на каждом сообщении."""
    session = Session()
    deps = _Deps(AgentReply(text="Занесено"))

    async def _reader(_: Any) -> list[Attachment]:
        return [
            Attachment(name="big.csv", text="строка;" * 5000),
            Attachment(name="shot.png", image=("image/png", "X" * 5000)),
        ]

    await handle_user_attachments(_PhotoMessage(""), deps, session, _reader)
    assert len(session.history[0]["content"]) < 150


async def test_unreadable_batch_is_reported() -> None:
    message = _PhotoMessage("")

    async def _failing(_: Any) -> list[Attachment]:
        raise DocumentUnreadableError("PDF больше 30 МБ.")

    await handle_user_attachments(
        message, _Deps(AgentReply(text="")), Session(), _failing
    )
    assert "30 МБ" in message.sent[0].text


async def test_caption_is_remembered_but_body_is_not() -> None:
    """В подписи она объясняет, какой счёт какой — это терять нельзя."""
    session = Session()
    deps = _Deps(AgentReply(text="Занесено"))
    note = "Альфа — это счёт 6806, сейчас баланс 212,27"

    async def _reader(_: Any) -> list[Attachment]:
        return [Attachment(name="big.csv", text="строка;" * 5000)]

    await handle_user_attachments(
        _PhotoMessage("", caption=note), deps, session, _reader
    )

    remembered = session.history[0]["content"]
    assert note in remembered
    assert "строка;строка;" not in remembered


async def test_history_keeps_a_real_conversation() -> None:
    """Шести обменов на живой разговор не хватало."""
    session = Session()
    deps = _Deps(AgentReply(text="ок"))
    for i in range(15):
        await handle_user_text(_Message(f"сообщение {i}"), deps, session)

    kept = [h["content"] for h in session.history]
    assert "сообщение 5" in kept
    assert len(session.history) <= Session.MAX_HISTORY
