"""UI and TitanConfig overrides stored in the `settings` table (M2.T3)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.config import TitanConfig, deep_merge
from titan_core.errors import ErrorCode, TitanError
from titan_db.models.settings import Setting
from titan_db.transaction import transaction

META_KEY = "_meta"
TITAN_SECTIONS = frozenset(TitanConfig.model_fields)


class SettingsDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    values: dict[str, Any]


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> SettingsDocument:
        rows = (await self._session.execute(select(Setting))).scalars().all()
        values: dict[str, Any] = {}
        version = 1
        for row in rows:
            if row.key == META_KEY:
                version = int(row.value.get("version", 1))
            else:
                values[row.key] = row.value
        return SettingsDocument(version=version, values=values)

    async def patch(self, merge_patch: dict[str, Any], *, expected_version: int) -> SettingsDocument:
        current = await self.get()
        if current.version != expected_version:
            raise TitanError(
                ErrorCode.VERSION_MISMATCH,
                f"Settings version is {current.version}, not {expected_version}.",
            )
        merged = _merge_patch(current.values, merge_patch)
        self._validate_titan_sections(merged)
        async with transaction(self._session):
            await self._upsert_rows(merged, version=current.version + 1)
        return await self.get()

    async def titan_overrides(self) -> dict[str, Any]:
        """Nested dict suitable for `load_config(db_settings=...)`."""
        doc = await self.get()
        return {key: value for key, value in doc.values.items() if key in TITAN_SECTIONS}

    def _validate_titan_sections(self, values: dict[str, Any]) -> None:
        subset = {key: value for key, value in values.items() if key in TITAN_SECTIONS}
        if not subset:
            return
        merged = deep_merge(TitanConfig().model_dump(), subset)
        TitanConfig.model_validate(merged)

    async def _upsert_rows(self, values: dict[str, Any], *, version: int) -> None:
        for key, value in values.items():
            stmt = insert(Setting).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Setting.key],
                set_={"value": stmt.excluded.value},
            )
            await self._session.execute(stmt)
        meta = insert(Setting).values(key=META_KEY, value={"version": version})
        meta = meta.on_conflict_do_update(
            index_elements=[Setting.key],
            set_={"value": meta.excluded.value},
        )
        await self._session.execute(meta)


def _merge_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7396 JSON Merge Patch for top-level settings keys."""
    out = dict(base)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out
