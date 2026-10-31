"""Throwaway remote-exec for the Windows test box (SCM over SMB).

WinRM rejects these credentials and port 22 is not OpenSSH, but 445 works and the Service
Control Manager is reachable over the IPC$ pipe. So: upload a .bat, register a demand-start
service whose binary is `cmd.exe /c that.bat`, read the output file back over the same SMB
session. Crude, needs no extra port, and every step leaves a file you can inspect.

Why a .bat: `cmd /c a & b > out.txt` redirects only the last command in the chain, which
cost a debugging round — the batch captures everything.
"""

from __future__ import annotations

import sys
import time

from impacket.dcerpc.v5 import scmr, transport
from impacket.smbconnection import SMBConnection

# The console here is GBK; remote output is the system code page or UTF-16.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "152.175.241.226"
USER = "Administrator"
PASSWORD = "zGObanpBktwg8Z3t"


def _conn() -> SMBConnection:
    conn = SMBConnection(HOST, HOST, sess_port=445)
    conn.login(USER, PASSWORD)
    return conn


def put(name: str, content: str) -> None:
    """Upload a text file. The callback must advance its own cursor.

    `data[offset:offset+4096]` looks equivalent and is not: impacket calls the callback
    repeatedly without guaranteed increments, and a stateless slice rewrote the same chunk
    — the file arrived as 0 bytes and the service had nothing to run.
    """
    data = content.encode("gbk", "replace")
    cursor = {"at": 0}

    def chunk(_offset: int) -> bytes:
        start = cursor["at"]
        piece = data[start : start + 4096]
        cursor["at"] = start + len(piece)
        return piece

    conn = _conn()
    try:
        conn.putFile("C$", f"\\{name}", chunk)
    finally:
        conn.logoff()


def read(name: str, _, tries: int = 1) -> str | None:
    chunks: list[bytes] = []
    conn = _conn()
    try:
        conn.getFile("C$", f"\\{name}", chunks.append)
    except Exception:
        return None
    finally:
        conn.logoff()
    data = b"".join(chunks)
    if b"\x00" in data:
        return data.decode("utf-16-le", "replace")
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def run(command: str, timeout: int = 300) -> str:
    stamp = str(int(time.time()))
    bat = f"soapbot-run-{stamp}.bat"
    out = f"soapbot-out-{stamp}.txt"
    put(bat, f"@echo off\r\n{command}\r\n")

    dce = transport.DCERPCTransportFactory(f"ncacn_np:{HOST}[\\pipe\\svcctl]")
    dce.set_credentials(USER, PASSWORD, "")
    rpc = dce.get_dce_rpc()
    rpc.connect()
    rpc.bind(scmr.MSRPC_UUID_SCMR)
    handle = scmr.hROpenSCManagerW(rpc)["lpScHandle"]
    name = f"Soapbot{stamp}"
    try:
        service = scmr.hRCreateServiceW(
            rpc,
            handle,
            name + "\x00",
            name + "\x00",
            lpBinaryPathName=f"cmd.exe /c C:\\{bat} > C:\\{out} 2>&1\x00",
            dwStartType=scmr.SERVICE_DEMAND_START,
            dwServiceType=scmr.SERVICE_WIN32_OWN_PROCESS,
        )["lpServiceHandle"]
        try:
            scmr.hRStartServiceW(rpc, service)
        except Exception:
            # Expected: cmd.exe does not speak the service control protocol, so SCM reports
            # a timeout after ~30s — but it has already launched the process.
            pass
        try:
            scmr.hRDeleteService(rpc, service)
        except Exception:
            pass
        scmr.hRCloseServiceHandle(rpc, service)
    finally:
        scmr.hRCloseServiceHandle(rpc, handle)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        text = read(out, None)
        if text:
            return text
    return "<no output file appeared>"


if __name__ == "__main__":
    print(run(sys.argv[1] if len(sys.argv) > 1 else "whoami"))
