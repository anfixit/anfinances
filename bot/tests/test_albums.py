"""Альбом собирается в одну пачку, а не обрабатывается по частям."""

import asyncio

from anfinances_bot.telegram.albums import AlbumBuffer


async def test_single_message_is_a_batch_of_one() -> None:
    buffer = AlbumBuffer(delay=0)
    assert await buffer.collect(None, "одно") == ["одно"]


async def test_album_is_collected_by_the_first_message() -> None:
    buffer = AlbumBuffer(delay=0.05)
    first = asyncio.create_task(buffer.collect("g1", "a"))
    await asyncio.sleep(0.01)
    rest = [await buffer.collect("g1", x) for x in ("b", "c")]

    assert rest == [None, None]
    assert await first == ["a", "b", "c"]


async def test_two_albums_do_not_mix() -> None:
    buffer = AlbumBuffer(delay=0.05)
    one = asyncio.create_task(buffer.collect("g1", "a1"))
    two = asyncio.create_task(buffer.collect("g2", "b1"))
    await asyncio.sleep(0.01)
    await buffer.collect("g1", "a2")
    await buffer.collect("g2", "b2")

    assert await one == ["a1", "a2"]
    assert await two == ["b1", "b2"]


async def test_group_is_forgotten_after_flush() -> None:
    """Иначе следующий альбом с тем же id прилип бы к прошлому."""
    buffer = AlbumBuffer(delay=0)
    assert await buffer.collect("g1", "a") == ["a"]
    assert await buffer.collect("g1", "b") == ["b"]
