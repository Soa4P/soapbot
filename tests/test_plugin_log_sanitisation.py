"""Plugin-authored text must not be able to redraw the host's log (S-PLUG-11).

Four channels carry a plugin's words into log output:

* the ``log.write`` surface (in-process) — pinned in test_runtime_integrity_signals.py;
* the isolated worker's ``log`` frames and the resident worker's ``stderr`` drain —
  pinned in test_plugin_ipc_hardening.py via ``plugin_log_line`` / ``stderr_sink_for``;
* ``ctx.log``, the plain stdlib logger handed to an in-process plugin — pinned here.

The fourth was the easy one to miss because it is "just logging": but a plugin calling
``ctx.log.info("...\\nlevel=ERROR host compromised")`` used to get exactly that, raw,
into the operator's log — and ``ctx.log.info("token=%s", value)`` passes the secret
through ``args``, where a format-string rewrite would never see it. The sanitiser
therefore rewrites the *formatted* record and clears ``args``.
"""

from __future__ import annotations

import logging

from soapbot.plugins.context import PluginRecordSanitiser


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="soapbot.plugin.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args or None,
        exc_info=None,
    )


def test_a_formatted_token_is_masked_even_when_passed_through_args() -> None:
    """The secret travels in ``args``, not in the format string.

    The redactor masks the whole ``key=value`` pair (the key name goes with it) — that
    is deliberate: keeping ``token=`` visible with an empty value would advertise which
    credential shape the plugin handles.
    """
    record = _record("token=%s", "abcdef123456")

    PluginRecordSanitiser().filter(record)

    assert "abcdef123456" not in record.getMessage()
    assert record.getMessage() == "***REDACTED***"


def test_a_newline_cannot_forge_a_second_line() -> None:
    record = _record("step 1\nlevel=ERROR host compromised")

    PluginRecordSanitiser().filter(record)

    assert "\n" not in record.getMessage()
    assert "step 1" in record.getMessage()


def test_normal_text_survives_unchanged() -> None:
    record = _record("cache refreshed: 12 entries")

    PluginRecordSanitiser().filter(record)

    assert record.getMessage() == "cache refreshed: 12 entries"


def test_the_filter_returns_true_and_clears_args() -> None:
    """Returning True keeps the record flowing; clearing args is what makes the
    rewritten message the one that gets rendered."""
    sanitiser = PluginRecordSanitiser()
    record = _record("value=%s", 42)

    assert sanitiser.filter(record) is True
    assert record.args is None
    assert record.getMessage() == "value=42"
