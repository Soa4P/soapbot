"""Run PowerShell on the Windows test box over WinRM and print the output."""

import sys

import winrm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = winrm.Session(
    "http://152.175.241.226:5985/wsman",
    auth=("Administrator", "zGObanpBktwg8Z3t"),
    transport="basic",
)


def ps(script: str, timeout: int = 600):
    result = SESSION.run_ps(script)
    out = result.std_out.decode("utf-8", "replace")
    err = result.std_err.decode("utf-8", "replace")
    return result.status_code, out.strip(), err.strip()


if __name__ == "__main__":
    code, out, err = ps(sys.argv[1] if len(sys.argv) > 1 else "whoami")
    print(f"[exit {code}]")
    print(out)
    if err:
        print("--- stderr ---")
        print(err)
