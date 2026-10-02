"""Агентный цикл: параметры запроса и обработка отказов."""

import logging
from typing import Any

import pytest

from anfinances_bot.agent.runner import AgentRunner, AgentUnavailableError
from anfinances_bot.anfinances.schemas import AccountRead


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self) -> None:
        self.input_tokens = 100
        self.output_tokens = 20
        self.cache_read_input_tokens = 900
        self.cache_creation_input_tokens = 0


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]
        self.stop_reason = "end_turn"
        self.usage = _Usage()


class _FakeToolBox:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self.last_created_id: str | None = None
        self.pending_accounts: list[AccountRead] = []
        self.armed = 0

    def arm_pending_import(self) -> None:
        self.armed += 1


class _FakeToolRunner:
    """Изображает два захода агента: вызов инструмента и ответ."""

    def __init__(self, box: _FakeToolBox, created_id: str | None) -> None:
        self._box = box
        self._created_id = created_id
        self._left = 0

    def __aiter__(self) -> "_FakeToolRunner":
        self._left = 2
        return self

    async def __anext__(self) -> _Message:
        if self._left == 0:
            raise StopAsyncIteration
        self._left -= 1
        if self._created_id is not None:
            self._box.last_created_id = self._created_id
        return _Message("Записала: Еда → Кофейни, 300 ₽")


class _FakeMessages:
    def __init__(
        self,
        box: _FakeToolBox,
        created_id: str | None = "tx-1",
        fail: bool = False,
    ) -> None:
        self.kwargs: dict[str, Any] = {}
        self._box = box
        self._created_id = created_id
        self._fail = fail
        self._error: Exception = RuntimeError("модель недоступна")

    def tool_runner(self, **kwargs: Any) -> _FakeToolRunner:
        self.kwargs = kwargs
        if self._fail:
            raise self._error
        return _FakeToolRunner(self._box, self._created_id)


class _FakeBeta:
    def __init__(self, messages: _FakeMessages) -> None:
        self.messages = messages


class _FakeAnthropic:
    def __init__(self, messages: _FakeMessages) -> None:
        self.beta = _FakeBeta(messages)


def _pair(
    created_id: str | None = "tx-1", fail: bool = False
) -> tuple[AgentRunner, _FakeMessages, _FakeToolBox]:
    box = _FakeToolBox()
    messages = _FakeMessages(box, created_id, fail)
    return AgentRunner(_FakeAnthropic(messages), box), messages, box


def _text_of(message: dict[str, Any]) -> str:
    """Собрать текст из блоков сообщения."""
    return "\n".join(
        block["text"]
        for block in message["content"]
        if block.get("type") == "text"
    )


async def test_uses_opus_with_adaptive_thinking() -> None:
    runner, messages, _ = _pair()
    await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert messages.kwargs["model"] == "claude-opus-5-5"
    assert messages.kwargs["thinking"] == {"type": "adaptive"}
    # Простая фраза — низкое усилие: на среднем бот казался зависшим.
    assert messages.kwargs["output_config"] == {"effort": "low"}


async def test_documents_get_medium_effort() -> None:
    """Выписку разбирать вдумчиво: ошибка в строке дороже секунд."""
    runner, messages, _ = _pair()
    await runner.run("разбери", [], [], "Europe/Moscow", pdfs=["JVBERi0="])
    assert messages.kwargs["output_config"] == {"effort": "medium"}


async def test_pasted_statement_text_gets_medium_effort() -> None:
    runner, messages, _ = _pair()
    statement = "\n".join(f"2026-09-{d:02d};-300;Кофе" for d in range(1, 29))
    await runner.run(statement * 5, [], [], "Europe/Moscow")
    assert messages.kwargs["output_config"] == {"effort": "medium"}


async def test_returns_text_and_created_id() -> None:
    runner, _, _ = _pair()
    reply = await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert "Кофейни" in reply.text
    assert reply.created_transaction_id == "tx-1"


async def test_model_failure_raises_agent_unavailable() -> None:
    runner, _, _ = _pair(fail=True)
    with pytest.raises(AgentUnavailableError):
        await runner.run("кофе 300", [], [], "Europe/Moscow")


async def test_system_blocks_are_passed() -> None:
    runner, messages, _ = _pair()
    await runner.run("кофе 300", [], [], "Asia/Tashkent")
    system = messages.kwargs["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "Asia/Tashkent" in system[-1]["text"]


async def test_current_moment_goes_into_message_not_prefix() -> None:
    """«Вчера» без сегодняшней даты не разрешить, но кэш дороже."""
    runner, messages, _ = _pair()
    await runner.run("вчера кофе 300", [], [], "Asia/Tashkent")

    content = _text_of(messages.kwargs["messages"][-1])
    assert "вчера кофе 300" in content
    assert "Сейчас" in content
    # Дата меняется каждый день — в кэшируемом префиксе ей не место.
    for block in messages.kwargs["system"]:
        assert "Сейчас" not in block["text"]


async def test_history_is_passed_before_the_new_message() -> None:
    runner, messages, _ = _pair()
    history: list[dict[str, Any]] = [
        {"role": "user", "content": "сколько на альфе"},
        {"role": "assistant", "content": "145,34 ₽"},
    ]
    await runner.run("а на сбере", [], [], "Europe/Moscow", history=history)

    sent = messages.kwargs["messages"]
    assert sent[:2] == history
    assert "а на сбере" in _text_of(sent[-1])


async def test_stale_created_id_does_not_leak_into_next_reply() -> None:
    """Хвост прошлой операции показал бы карточку не к тому ответу."""
    runner, _, box = _pair(created_id=None)
    box.last_created_id = "tx-старый"
    reply = await runner.run("сколько я потратила", [], [], "Europe/Moscow")
    assert reply.created_transaction_id is None


async def test_image_goes_before_the_question() -> None:
    """Модель читает картинку в контексте вопроса, а не после него."""
    runner, messages, _ = _pair()
    await runner.run(
        "разнеси этот чек",
        [],
        [],
        "Europe/Moscow",
        images=[("image/jpeg", "УУУ")],
    )
    blocks = messages.kwargs["messages"][-1]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[-1]["type"] == "text"


async def test_no_images_means_no_image_blocks() -> None:
    runner, messages, _ = _pair()
    await runner.run("кофе 300", [], [], "Europe/Moscow")
    blocks = messages.kwargs["messages"][-1]["content"]
    assert all(b["type"] == "text" for b in blocks)


async def test_pdf_goes_as_a_document_block() -> None:
    """Без блока модель видит только имя файла, а не его содержимое."""
    runner, messages, _ = _pair()
    await runner.run(
        "разбери выписку",
        [],
        [],
        "Europe/Moscow",
        pdfs=["ПДФ64"],
    )
    blocks = messages.kwargs["messages"][-1]["content"]
    documents = [b for b in blocks if b["type"] == "document"]
    assert len(documents) == 1
    assert documents[0]["source"]["media_type"] == "application/pdf"
    assert documents[0]["source"]["data"] == "ПДФ64"


async def test_documents_and_images_go_together() -> None:
    runner, messages, _ = _pair()
    await runner.run(
        "сведи всё",
        [],
        [],
        "Europe/Moscow",
        images=[("image/png", "КАРТ")],
        pdfs=["П1", "П2"],
    )
    kinds = [b["type"] for b in messages.kwargs["messages"][-1]["content"]]
    assert kinds == ["image", "document", "document", "text"]


async def test_billing_error_says_what_to_do() -> None:
    """«Модель недоступна» прятало «кончились деньги на счету»."""
    box = _FakeToolBox()
    messages = _FakeMessages(box, fail=True)
    messages._error = Exception(  # type: ignore[attr-defined]
        "Error code: 400 - Your credit balance is too low"
    )
    runner = AgentRunner(_FakeAnthropic(messages), box)

    with pytest.raises(AgentUnavailableError) as caught:
        await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert "баланс" in caught.value.reason.casefold()


async def test_rate_limit_asks_to_wait() -> None:
    box = _FakeToolBox()
    messages = _FakeMessages(box, fail=True)
    messages._error = Exception("429 rate limit exceeded")  # type: ignore[attr-defined]
    runner = AgentRunner(_FakeAnthropic(messages), box)

    with pytest.raises(AgentUnavailableError) as caught:
        await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert "подожди" in caught.value.reason.casefold()


async def test_unknown_failure_keeps_the_general_wording() -> None:
    runner, _, _ = _pair(fail=True)
    with pytest.raises(AgentUnavailableError) as caught:
        await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert "модель недоступна" in caught.value.reason.casefold()


async def test_prefix_is_cached_for_an_hour() -> None:
    """Между её сообщениями проходит больше пяти минут."""
    runner, messages, _ = _pair()
    await runner.run("кофе 300", [], [], "Europe/Moscow")
    cache = messages.kwargs["system"][-1]["cache_control"]
    assert cache == {"type": "ephemeral", "ttl": "1h"}


async def test_attachment_message_is_cached() -> None:
    """Иначе выписка оплачивается заново на каждом шаге агента."""
    runner, messages, _ = _pair()
    await runner.run(
        "разбери",
        [],
        [],
        "Europe/Moscow",
        pdfs=["ПДФ"],
    )
    last = messages.kwargs["messages"][-1]["content"][-1]
    assert last["cache_control"] == {"type": "ephemeral", "ttl": "5m"}


async def test_plain_question_is_cached_too() -> None:
    """За короткой фразой стоят сорок прошлых сообщений.

    Их пересылают заново на каждом заходе агента, и платить за них
    по полной цене дороже, чем один раз записать в кэш.
    """
    runner, messages, _ = _pair()
    await runner.run("сколько осталось", [], [], "Europe/Moscow")
    last = messages.kwargs["messages"][-1]["content"][-1]
    assert last["cache_control"] == {"type": "ephemeral", "ttl": "5m"}


async def test_spend_is_counted_across_all_turns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Счёт складывается из всех заходов, а не из последнего ответа.

    Последний ответ самый дешёвый: в нём нет ни инструментов, ни
    выписки. Судить по нему — значит не видеть расхода вовсе.
    """
    runner, _, _ = _pair()
    with caplog.at_level(logging.INFO, logger="anfinances_bot.agent"):
        await runner.run("кофе 300", [], [], "Europe/Moscow")

    line = "\n".join(record.getMessage() for record in caplog.records)
    assert "заходов 2" in line
    assert "из кэша 1800" in line


async def test_each_run_arms_the_pending_import() -> None:
    """Разбор выписки становится заносимым только с её ответом."""
    runner, _, box = _pair()
    await runner.run("да, заноси", [], [], "Europe/Moscow")
    assert box.armed == 1
