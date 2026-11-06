"""The restart hint the panel shows must match the deployment it is running on.

The previous hint hard-coded ``SoapbotPanel`` while the Windows installer registers
``SoapbotBot``, so a successful save looked like a failed one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import soapbot.api.service_hint as service_hint


def test_windows_default_names_the_task_the_installer_creates(monkeypatch) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(service_hint, "os", SimpleNamespace(name="nt", environ={}))

    assert service_hint.restart_hint() == (
        "schtasks /End /TN SoapbotBot && schtasks /Run /TN SoapbotBot"
    )


def test_service_name_overrides_the_default(monkeypatch) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint,
        "os",
        SimpleNamespace(name="nt", environ={"SOAPBOT_SERVICE_NAME": "MyBotTask"}),
    )

    assert "/TN MyBotTask" in service_hint.restart_hint()


def test_linux_uses_systemctl(monkeypatch) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(service_hint, "os", SimpleNamespace(name="posix", environ={}))

    assert service_hint.restart_hint() == "systemctl restart soapbot"


def test_container_uses_compose(monkeypatch) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: True)

    assert service_hint.restart_hint() == "docker compose restart soapbot"


async def test_access_matrix_carries_the_hint(monkeypatch) -> None:
    """The panel reads it from /api/access, not from a second endpoint."""
    from soapbot.api.admin import access_matrix

    # ``admin`` imported the function by name, so patching the module attribute would
    # not affect the already-bound reference.
    monkeypatch.setattr("soapbot.api.admin.restart_hint", lambda: "systemctl restart demo")

    payload = await access_matrix({})

    assert payload["restart_hint"] == "systemctl restart demo"
    assert "trust_protocol_roles" in payload


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_blank_service_name_falls_back(monkeypatch, empty_value: str) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint, "os", SimpleNamespace(name="posix", environ={"SOAPBOT_SERVICE_NAME": empty_value})
    )

    assert service_hint.restart_hint() == "systemctl restart soapbot"
