"""Агентный цикл: параметры запроса и обработка отказов."""

from typing import Any

import pytest

from anfinances_bot.agent.runner import AgentRunner, AgentUnavailableError
from anfinances_bot.anfinances.schemas import AccountRead


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]
        self.stop_reason = "end_turn"


class _FakeToolBox:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self.last_created_id: str | None = None
        self.pending_accounts: list[AccountRead] = []


class _FakeToolRunner:
    """Изображает вызов инструмента внутри until_done()."""

    def __init__(self, box: _FakeToolBox, created_id: str | None) -> None:
        self._box = box
        self._created_id = created_id

    async def until_done(self) -> _Message:
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

    def tool_runner(self, **kwargs: Any) -> _FakeToolRunner:
        self.kwargs = kwargs
        if self._fail:
            raise RuntimeError("модель недоступна")
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
    assert messages.kwargs["model"] == "claude-opus-5"
    assert messages.kwargs["thinking"] == {"type": "adaptive"}
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
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
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
