# Spectator credential configuration

The optional remote spectator token is read from `XIANGQI_SIMULATION_TOKEN`.
In PowerShell, set it before starting the application:

```powershell
$env:XIANGQI_SIMULATION_TOKEN = '<token supplied by the service owner>'
.\.venv312\Scripts\python.exe -X utf8 main.py --physical
```

Without this variable the token is empty. Local game/viewer execution does not
require a remote spectator credential. Do not commit tokens or add them to logs.

The previously embedded token was removed from config.py and redacted in tracked
config archive artifacts. It still exists in earlier Git history: the service
owner must revoke/rotate it. Removing a string from code does not revoke access.
Historical config hashes in the old reports describe their original snapshots,
not the now-redacted archive files. Other historical source evidence is retained.
