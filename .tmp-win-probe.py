"""Diagnose why only cmd builtins produce output through the SCM trick.

`echo`/`ver` write; `whoami`, `where`, `powershell` do not. That smells like PATH or the
process environment rather than permissions, so this asks the box directly: print %PATH%,
then call the same binaries by absolute path and by full powershell path.
"""

import importlib.util
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location("wx", ".tmp-win-exec.py")
wx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wx)

probes = [
    "echo PATH=%PATH%",
    "echo SYSTEMROOT=%SystemRoot%",
    r"C:\Windows\System32\whoami.exe",
    r"%SystemRoot%\System32\where.exe cmd",
    r'"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Write-Output PS-OK"',
]

for probe in probes:
    try:
        print(f"{probe}\n  -> {wx.run(probe, timeout=45)!r}")
    except Exception as exc:
        print(f"{probe}\n  !! {type(exc).__name__}: {str(exc)[:120]}")
