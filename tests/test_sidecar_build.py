"""The frozen backend must be reproducible, and its entry must pin its own paths.

Two failure modes are covered statically because building the binary takes about a
minute and must not run in the default suite:

* ``Settings`` derives ``data_dir`` / ``config_template_dir`` from ``__file__``. Under
  ``--onefile`` that path lives in a temporary extraction directory, so the entry has to
  set the four environment variables **before** importing anything that pulls in
  ``soapbot.config``. Measured while building this: the first frozen run started,
  seeded its config, and then died in ``create_async_engine`` because SQLAlchemy's
  dialect is resolved from a URL string no import graph contains.
* the build command itself must keep declaring the panel and the config templates, the
  two trees PyInstaller cannot infer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "desktop" / "sidecar" / "entry.py"
BUILD = ROOT / "desktop" / "sidecar" / "build.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Import a standalone script as a module.

    Registered in ``sys.modules`` **before** execution: ``@dataclass`` resolves its
    annotations through ``sys.modules[cls.__module__]``, which is ``None`` for a module
    that was executed without ever being registered — and `check_desktop.py` defines a
    dataclass at the top.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_build() -> ModuleType:
    return _load_module("sidecar_build", BUILD)


def test_the_entry_pins_every_directory_before_importing_settings() -> None:
    text = ENTRY.read_text(encoding="utf-8")
    for name in (
        "SOAPBOT_DATA_DIR",
        "SOAPBOT_CONFIG_DIR",
        "SOAPBOT_CONFIG_TEMPLATE_DIR",
        "SOAPBOT_ENV_FILE",
    ):
        assert name in text, f"entry.py 没有钉住 {name}"

    # `SettingsConfigDict` reads SOAPBOT_ENV_FILE at class-definition time, so the
    # assignment has to precede the import — not merely exist somewhere in the file.
    pinned = text.index('setdefault("SOAPBOT_ENV_FILE"')
    imported = text.index("from soapbot.cli import")
    assert pinned < imported, "环境变量在 import 之后才设置，对 env_file 无效"


def test_a_double_click_starts_the_server_instead_of_printing_a_version() -> None:
    text = ENTRY.read_text(encoding="utf-8")
    assert 'sys.argv[1:] or ["start"]' in text


def test_the_build_declares_both_data_trees() -> None:
    module = _load_build()
    args = module.command()
    joined = " ".join(args)

    assert args.count("--add-data") == 2
    assert "soapbot/webui/dist" in joined, "面板产物没有被打包进去"
    assert str(Path(module.ROOT) / "config") in joined, "配置模板没有被打包进去"


def test_the_build_covers_imports_resolved_by_name_at_runtime() -> None:
    module = _load_build()
    args = module.command()

    assert "sqlalchemy.dialects.sqlite" in args
    assert "aiosqlite" in args
    for package in ("uvicorn", "soapbot"):
        assert package in args, f"--collect-submodules 漏了 {package}"


def test_the_build_is_onefile_because_tauri_expects_one_binary() -> None:
    args = _load_build().command()
    assert "--onefile" in args
    assert "--onedir" not in args


def test_a_missing_frontend_fails_before_pyinstaller_runs(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """The guard must be cheap and explicit: a 46 MiB binary with a blank panel is worse
    than a build that refuses to start."""
    module = _load_build()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.main() == 2
    assert "webui/dist" in capsys.readouterr().err


def test_the_binary_and_work_directory_are_not_committed() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "desktop/sidecar/dist/" in ignored
    assert "build/" in ignored
    # The directory itself stays: Tauri validates `bundle.resources` during
    # `cargo check`, and CI checks the shell without producing the binary.
    assert "desktop/src-tauri/binaries/*" in ignored
    assert "!desktop/src-tauri/binaries/.gitkeep" in ignored


GATE = ROOT / "scripts" / "check_desktop.py"


def _load_gate() -> ModuleType:
    return _load_module("check_desktop_gate", GATE)


def test_the_real_shell_passes_the_guarded_spawn_rule() -> None:
    gate = _load_gate()
    main = (ROOT / "desktop" / "src-tauri" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )
    assert gate.sidecar_rule_problems(main) == []


def test_a_bare_spawn_outside_the_two_functions_is_rejected() -> None:
    gate = _load_gate()
    problems = gate.sidecar_rule_problems(
        'fn main() { Command::new("python"); }\n// python -m soapbot\n'
    )
    assert any("spawn_decision" in item for item in problems)
    assert any("未受控函数" in item for item in problems)
    assert any("源码树" in item for item in problems)


def test_spawn_calls_are_attributed_to_the_enclosing_function() -> None:
    gate = _load_gate()
    offenders = gate._spawn_calls_outside_allowed(
        'fn start_sidecar() {\n    Command::new("ok");\n}\n'
        'fn elsewhere() {\n    Command::new("bad");\n}\n'
    )
    assert offenders == ['elsewhere: Command::new("bad");']


def test_the_build_stages_the_binary_for_tauri() -> None:
    source = BUILD.read_text(encoding="utf-8")
    assert "shutil.copy2" in source
    assert '"src-tauri"' in source and '"binaries"' in source
