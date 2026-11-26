"""QQ official bot menu: read and write the local document.

**Nothing here calls the platform.** Uploading a menu needs an AppID/Secret and a live
endpoint; what this pair of routes makes possible is authoring and checking the document
where the operator can see it, with the same validator that a future upload would use.

Both routes are ADMIN: a menu is what every user of the bot sees, so editing it is a
deployment-level change, not a preference.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from soapbot.adapters.qq_menu import MenuError, MenuStore, menu_path
from soapbot.api.auth import require_role
from soapbot.api.config_write import _audit, _caller_label
from soapbot.config import settings
from soapbot.security.principal import Role

router = APIRouter(
    prefix="/api/config/qq-menu",
    tags=["config"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _store() -> MenuStore:
    return MenuStore(menu_path(settings.config_dir))


class MenuDocument(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    """Untyped on purpose: the validator owns the shape and reports *every* problem at
    once. Modelling it here would split the rules across two places and answer with
    Pydantic's first error, which is not what an operator editing a tree needs."""


@router.get("")
async def read_menu() -> dict[str, Any]:
    store = _store()
    return {"document": store.load(), "path": str(store.path), "note": "本地骨架：尚未上传到官方接口"}


@router.put("")
async def write_menu(body: MenuDocument, request: Request) -> dict[str, Any]:
    store = _store()
    try:
        saved = store.save(body.model_dump())
    except MenuError as exc:
        # 422 with the whole list: the panel renders them next to the editor, and one
        # round trip per mistake is how an operator gives up on a form.
        raise HTTPException(
            status_code=422,
            detail={"message": "菜单未通过校验", "problems": exc.problems},
        ) from exc
    # Field names and item count only: a menu's replies are user-visible text, and the
    # audit log is read by people who do not need to see them again.
    _audit(_caller_label(request), "allow", "qq_menu.write", ["items"])
    return {"saved": True, "document": saved, "path": str(store.path)}


@router.post("/validate")
async def validate_menu(body: MenuDocument) -> dict[str, Any]:
    """Check without writing — the editor calls this as the operator types."""
    from soapbot.adapters.qq_menu import validate

    problems = validate(body.model_dump())
    return {"ok": not problems, "problems": problems}
