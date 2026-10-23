"""Install the private build into workspace staging, check it, then uninstall."""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = (ROOT / "artifacts").resolve()
STAGE = (ARTIFACTS / "install-smoke-0.1.1").resolve()
SETUP = (ROOT / "releases/Jeru-Setup-0.1.1.exe").resolve()
REPORT = ARTIFACTS / "installed-self-check.json"
if not STAGE.is_relative_to(ARTIFACTS) or STAGE == ARTIFACTS or STAGE.exists():
    raise ValueError("Installer staging must be a new directory inside workspace artifacts")
if not SETUP.is_file():
    raise FileNotFoundError("Build the Jeru installer first")
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
result = {}
try:
    install = subprocess.run([str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS", "/DIR=" + str(STAGE), "/LOG=" + str(ARTIFACTS / "install-smoke.log")], timeout=600, creationflags=flags)
    result["install_exit"] = install.returncode
    if install.returncode:
        raise ValueError("Silent installer failed")
    executable = (STAGE / "Jeru.exe").resolve()
    if executable.parent != STAGE or not executable.is_file():
        raise ValueError("Installed executable is not in the verified staging directory")
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "QT_PLUGIN_PATH"):
        env.pop(key, None)
    env["PATH"] = str(Path(os.environ["WINDIR"]) / "System32") + ";" + os.environ["WINDIR"]
    check = subprocess.run([str(executable), "--self-check", str(REPORT)], env=env, timeout=120, creationflags=flags)
    result["self_check_exit"] = check.returncode
    result["self_check"] = json.loads(REPORT.read_text(encoding="utf-8"))
    if check.returncode or not result["self_check"].get("passed"):
        raise ValueError("Installed runtime self-check failed")
finally:
    # Verify the final absolute location before invoking the recursive uninstaller.
    uninstaller = (STAGE / "unins000.exe").resolve()
    if uninstaller.is_file():
        if not uninstaller.is_relative_to(ARTIFACTS) or uninstaller.parent != STAGE:
            raise ValueError("Uninstaller is outside the verified staging directory")
        uninstall = subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=" + str(ARTIFACTS / "uninstall-smoke.log")], timeout=300, creationflags=flags)
        result["uninstall_exit"] = uninstall.returncode
        # Inno's final self-deletion may finish after the launcher process exits.
        deadline = time.monotonic() + 10
        while STAGE.exists() and time.monotonic() < deadline:
            time.sleep(.2)
    result["staging_removed"] = not STAGE.exists()
    (ARTIFACTS / "installer-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if result.get("uninstall_exit") != 0:
    raise SystemExit(1)
