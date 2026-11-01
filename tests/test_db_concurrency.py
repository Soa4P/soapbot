"""Concurrent writers must not fail with ``database is locked``.

Found on a real box, not by reading. Passive mode archives on the same path the
answering write runs on, and a busy group produced ``sqlite3.OperationalError:
database is locked`` — seven times in one log, each one swallowed by a GBK logging
error that hid the real traceback.

The first diagnosis was wrong and worth recording: ``busy_timeout`` and
``journal_mode`` are per-connection pragmas, so it looked like ``init()`` setting them
on one connection and ``NullPool`` discarding them. Setting them on every connection
was measured against a 150-writer burst and changed nothing (17 failures with the
change, 14 without). The pragma was never the problem — SQLite admits one writer, and
``busy_timeout`` makes the losers *block a background thread* while the event loop
keeps starting more of them. The fix is one asyncio lock in front of the write path.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from soapbot.memory.db import Database
from soapbot.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_every_new_connection_has_the_busy_timeout(tmp_path) -> None:
    """The pragma must survive a checkout, not just the connection ``init`` used.

    Kept even though it was not the fix: without it, the *first* competing writer waits
    zero seconds, so the lock in :meth:`Database.write` would be the only thing standing
    between a burst and an immediate failure.
    """
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.db'}")
    await db.init()

    async def read_timeout() -> int:
        async with db.engine.connect() as conn:
            result = await conn.execute(text("PRAGMA busy_timeout"))
            return int(result.scalar_one())

    assert await read_timeout() > 0
    assert await read_timeout() > 0
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_a_burst_of_archives_does_not_raise_locked(tmp_path) -> None:
    """The regression itself, at the scale that produced it.

    150 concurrent archives reproduced 14–17 ``database is locked`` failures before the
    write lock existed. The number is kept deliberately above what a group produces,
    because the failure is a race and a small burst can pass by luck.
    """
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'burst.db'}")
    await db.init()
    store = MemoryStore(db)

    errors: list[str] = []

    async def archive(n: int) -> None:
        try:
            await store.archive_message(
                session_key=f"onebot11:group:{n % 3}",
                role="user",
                content=f"第{n}条 今天群里在聊显卡和内存条的价格",
                adapter="onebot11",
                scene="group",
                group_id=str(n % 3),
                user_id="2",
                user_name="u",
                message_id=f"m{n}",
                trace_id=f"t{n}",
            )
        except Exception as exc:  # the assertion is that this never happens
            errors.append(str(exc)[:80])

    await asyncio.gather(*(archive(i) for i in range(150)))

    assert errors == [], f"{len(errors)} writes failed, first: {errors[0]}"
    async with db.engine.connect() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM messages"))).scalar_one()
    assert count == 150
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_readers_are_not_serialised_behind_writers(tmp_path) -> None:
    """The lock is on writes only. WAL exists so reads do not wait; a read lock would
    trade one bottleneck for another."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'rw.db'}")
    await db.init()
    store = MemoryStore(db)
    await store.archive_message(
        session_key="onebot11:group:1", role="user", content="先写一条", group_id="1"
    )

    async def write(n: int) -> None:
        await store.archive_message(
            session_key="onebot11:group:1",
            role="user",
            content=f"并发写入 {n}",
            group_id="1",
            message_id=f"w{n}",
        )

    async def read() -> int:
        rows = await store.history("onebot11:group:1", limit=50)
        return len(rows)

    writes = [write(i) for i in range(30)]
    reads = [read() for _ in range(30)]
    # Interleaved on purpose: gather runs them in submission order, so a read sits
    # between every two writes. If reads took the write lock, this would serialise and
    # the count assertion below would still pass — the timing assertion is what makes
    # the test about concurrency rather than about correctness alone.
    loop = asyncio.get_running_loop()
    started = loop.time()
    results = await asyncio.gather(*writes, *reads)
    elapsed = loop.time() - started

    assert all(isinstance(r, int) for r in results[30:])
    assert await read() >= 30
    # 60 operations against a local file; a serialised read path takes far longer.
    assert elapsed < 5.0, f"read/write mix took {elapsed:.1f}s — reads are queued"
    await db.engine.dispose()
