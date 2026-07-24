@echo off
rem Commande de la tache MSIA_refresh_index_vps, lancee SANS FENETRE par scripts\run_hidden.vbs.
pushd "C:\Users\<user>\Claude\Projects\MultiService IA"
echo. >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\refresh_index_vps.log"
echo ===== %DATE% %TIME% ===== >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\refresh_index_vps.log"
"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\Users\<user>\Claude\Projects\MultiService IA\scripts\refresh_index_vps.ps1" >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\refresh_index_vps.log" 2>&1
echo [code retour %ERRORLEVEL%] >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\refresh_index_vps.log"
popd
