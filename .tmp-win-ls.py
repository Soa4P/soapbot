"""What is actually on the Windows box now."""

import sys

from impacket.smbconnection import SMBConnection

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = SMBConnection("152.175.241.226", "152.175.241.226", sess_port=445)
conn.login("Administrator", "zGObanpBktwg8Z3t")
for path in ("soapbot-deploy.ps1", "soapbot-setup\\*", "soapbot\\pyproject.toml"):
    print(f"--- {path} ---")
    try:
        for entry in conn.listPath("C$", "\\" + path):
            name = entry.get_longname()
            if name in (".", ".."):
                continue
            print(("DIR  " if entry.is_directory() else "FILE ") + f"{name}  {entry.get_filesize()}")
    except Exception as exc:
        print("!!!", type(exc).__name__, str(exc)[:70])
conn.logoff()
