from sqlalchemy import BigInteger, Column, MetaData, String, Table, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()

t_settings = Table(
    "t_settings",
    metadata,
    Column("s_setting", String(20), primary_key=True),
    Column("s_val", String(20)),
)

t_chat_settings = Table(
    "t_chat_settings",
    metadata,
    Column("n_chat_id", BigInteger, primary_key=True),
    Column("s_setting", String(20), primary_key=True),
    Column("s_value", String(1000)),
)


class Database:
    def __init__(self, url: str) -> None:
        kwargs = {"pool_pre_ping": True}
        if url.endswith(":memory:"):
            # в памяти SQLite каждое соединение — отдельная БД, нужно одно общее
            kwargs = {"poolclass": StaticPool}
        self._engine: AsyncEngine = create_async_engine(url, **kwargs)

    async def create_all(self) -> None:
        """Только для тестов: в боевой БД таблицы уже существуют."""
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def get_setting(self, name: str) -> str | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(t_settings.c.s_val).where(t_settings.c.s_setting == name))
            return result.scalar_one_or_none()

    async def set_setting(self, name: str, value: str) -> None:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(t_settings).where(t_settings.c.s_setting == name).values(s_val=value)
            )
            if result.rowcount == 0:
                await conn.execute(insert(t_settings).values(s_setting=name, s_val=value))

    async def set_chat_setting(self, chat_id: int, name: str, value: str) -> None:
        async with self._engine.begin() as conn:
            await self._upsert_chat_setting(conn, chat_id, name, value)

    @staticmethod
    async def _upsert_chat_setting(conn, chat_id: int, name: str, value: str) -> None:
        result = await conn.execute(
            update(t_chat_settings)
            .where(t_chat_settings.c.n_chat_id == chat_id, t_chat_settings.c.s_setting == name)
            .values(s_value=value)
        )
        if result.rowcount == 0:
            await conn.execute(
                insert(t_chat_settings).values(n_chat_id=chat_id, s_setting=name, s_value=value)
            )

    async def get_chat_ids_with_setting(self, name: str, value: str) -> list[int]:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(t_chat_settings.c.n_chat_id).where(
                    t_chat_settings.c.s_setting == name, t_chat_settings.c.s_value == value
                )
            )
            return [row[0] for row in result]

    async def migrate_chat(self, old_id: int, new_id: int) -> None:
        """Переносит настройки чата на новый ID; уже существующие значения нового чата сохраняются."""
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(t_chat_settings.c.s_setting, t_chat_settings.c.s_value).where(
                        t_chat_settings.c.n_chat_id == old_id
                    )
                )
            ).all()
            existing = {
                row[0]
                for row in await conn.execute(
                    select(t_chat_settings.c.s_setting).where(t_chat_settings.c.n_chat_id == new_id)
                )
            }
            for name, value in rows:
                if name not in existing:
                    await conn.execute(
                        insert(t_chat_settings).values(n_chat_id=new_id, s_setting=name, s_value=value)
                    )
            await conn.execute(delete(t_chat_settings).where(t_chat_settings.c.n_chat_id == old_id))

    async def close(self) -> None:
        await self._engine.dispose()
