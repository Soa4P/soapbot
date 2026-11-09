"""Every ``soapbot <subcommand>`` the documentation tells operators to run must exist.

This is not hypothetical. ``UPDATING.md`` told operators to run ``soapbot migrate`` in
five places — including a troubleshooting entry for the error it produces — while
``cli.py`` had no such subcommand. Following the upgrade guide printed the help text and
exited 1, at the exact moment the operator was least able to debug it.

``tests/test_cli_token.py`` records the same defect one iteration earlier: the ``token``
command exists *because* ``.env.example`` told operators to run it while the parser had no
such subcommand. Two occurrences is a pattern, so the pattern gets a test.

What counts as a subcommand
---------------------------
``soapbot <word>`` appears in prose in several shapes, and only one of them is a command:

* ``soapbot migrate --status`` — a command. ``migrate`` must be accepted.
* ``docker compose exec soapbot cat /data/init_token.txt`` — ``soapbot`` is a *container
  name* here, and ``cat`` is the program run inside it. Not a command.
* ``soapbot README 声明 MIT`` — a project name in prose. Not a command.

The filter below drops the second and third shapes by requiring that the word be the
first token after ``soapbot`` in a code span or a line that starts with it, and by
excluding the words that only ever appear as container arguments. The exclusion list is
deliberately explicit: a silent regex tweak that starts matching prose again would make
this test fail for the wrong reason, and a test that fails for the wrong reason gets
deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from soapbot import cli

ROOT = Path(__file__).resolve().parents[1]

#: Documents that tell an operator what to type. ``docs/`` is included wholesale because
#: the upgrade path is documented in several files and a new one should not need this list
#: edited.
DOCUMENTS = (ROOT / "UPDATING.md", ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))

#: Words that follow ``soapbot`` but are not subcommands: container names take a program
#: argument, and prose mentions the project by name. Each entry is here because it actually
#: occurs — not as a guess.
NOT_SUBCOMMANDS = frozenset(
    {
        "cat",
        "sh",
        "id",
        "README",
        "声明",
        "只",
        "是",
        "的",
    }
)

#: ``soapbot <word>`` where the word looks like a subcommand.
#:
#: ``[ \t]+`` and not ``\s+``: ``\s`` matches newlines, so a line ending in ``soapbot``
#: followed by a line starting with ``sudo`` would be read as the subcommand ``sudo``.
#: That is how this scanner first reported a command nobody had written.
PATTERN = re.compile(r"\bsoapbot[ \t]+([a-z][a-z0-9-]*)\b")


def _documented_subcommands() -> set[str]:
    found: set[str] = set()
    for path in DOCUMENTS:
        if not path.is_file():
            continue
        for match in PATTERN.finditer(path.read_text(encoding="utf-8")):
            word = match.group(1)
            if word not in NOT_SUBCOMMANDS:
                found.add(word)
    return found


def _accepted_subcommands() -> set[str]:
    """The subcommands the parser registers, read from the parser itself."""
    parser = cli.build_parser()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            return set(action.choices)
    return set()


def test_the_scanner_finds_the_commands_we_know_about() -> None:
    """A scanner that silently matches nothing would make the real test vacuous."""
    found = _documented_subcommands()
    assert {"migrate", "doctor", "token", "setup", "start"} <= found, (
        f"scanner found only {sorted(found)}; the pattern or the document list is wrong"
    )


def test_every_documented_subcommand_is_accepted_by_the_parser() -> None:
    """The defect this file exists for: a guide that names a command that does not exist."""
    documented = _documented_subcommands()
    accepted = _accepted_subcommands()
    missing = documented - accepted
    assert not missing, (
        f"documentation tells operators to run {sorted(missing)}, but the parser only "
        f"accepts {sorted(accepted)}. Either implement the command or stop documenting it."
    )


def test_the_parser_rejects_a_subcommand_nobody_documented() -> None:
    """The other direction: a command that exists but is undocumented is also a defect.

    Weaker than the check above — a command can be legitimately internal — so it only
    asserts that the accepted set is not wildly larger than the documented one.
    """
    accepted = _accepted_subcommands()
    documented = _documented_subcommands()
    undocumented = accepted - documented
    assert not undocumented, (
        f"the parser accepts {sorted(undocumented)} but no document mentions them; "
        "an operator cannot discover a command that is not written down."
    )


@pytest.mark.parametrize("command", ["migrate", "doctor", "token", "setup", "start", "version"])
def test_a_documented_command_parses_with_its_flags(command: str) -> None:
    """Parsing must not raise for the documented form (``--help`` exits 0)."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([command, "--help"])
    assert exc.value.code == 0
