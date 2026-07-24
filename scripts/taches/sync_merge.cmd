@echo off
rem Commande de la tache MSIA_sync_merge, lancee SANS FENETRE par scripts\run_hidden.vbs.
rem Le journal est obligatoire : une tache invisible qui echoue sans trace serait pire que rien.
cd /d "C:\Users\<user>\Claude\Projects\MultiService IA"
echo. >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\sync_merge.task.log"
echo ===== %DATE% %TIME% ===== >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\sync_merge.task.log"
"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\Users\<user>\Claude\Projects\MultiService IA\scripts\sync_memory_scheduled.ps1" >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\sync_merge.task.log" 2>&1
echo [code retour %ERRORLEVEL%] >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\sync_merge.task.log"
