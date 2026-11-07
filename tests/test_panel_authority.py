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


def test_shell_metacharacters_in_a_task_name_are_never_emitted_as_a_command(
    monkeypatch,
) -> None:
    """A hint is pasted into a shell by a human, so it needs its own defence.

    The automatic restart passes the name as argv and is safe, but
    ``SOAPBOT_SERVICE_NAME="Soapbot & calc"`` used to come back in the API response as
    ``schtasks /End /TN Soapbot & calc && ...`` — a second command, run with the
    operator's rights. Refusing to print a command is the only safe option for a name
    cmd.exe cannot express.
    """
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint,
        "os",
        SimpleNamespace(name="nt", environ={"SOAPBOT_SERVICE_NAME": "Soapbot & calc"}),
    )

    hint = service_hint.restart_hint()

    assert "calc" not in hint
    assert "schtasks" not in hint
    assert "&&" not in hint


def test_task_name_with_spaces_is_quoted(monkeypatch) -> None:
    """Windows task names may contain spaces; quoting keeps them one argument."""
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint,
        "os",
        SimpleNamespace(name="nt", environ={"SOAPBOT_SERVICE_NAME": "Soapbot Bot"}),
    )

    assert service_hint.restart_hint() == (
        'schtasks /End /TN "Soapbot Bot" && schtasks /Run /TN "Soapbot Bot"'
    )


def test_linux_service_name_is_shell_quoted(monkeypatch) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint,
        "os",
        SimpleNamespace(name="posix", environ={"SOAPBOT_SERVICE_NAME": "demo; id"}),
    )

    assert service_hint.restart_hint() == "systemctl restart 'demo; id'"


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_blank_service_name_falls_back(monkeypatch, empty_value: str) -> None:
    monkeypatch.setattr(service_hint, "in_container", lambda: False)
    monkeypatch.setattr(
        service_hint, "os", SimpleNamespace(name="posix", environ={"SOAPBOT_SERVICE_NAME": empty_value})
    )

    assert service_hint.restart_hint() == "systemctl restart soapbot"
