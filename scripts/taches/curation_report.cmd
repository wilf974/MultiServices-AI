@echo off
rem Commande de la tache MSIA_curation_report, lancee SANS FENETRE par scripts\run_hidden.vbs.
rem Le journal est obligatoire : une tache invisible qui echoue sans trace serait pire que rien.
cd /d "C:\Users\<user>\Claude\Projects\MultiService IA"
echo. >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\curation_report.log"
echo ===== %DATE% %TIME% ===== >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\curation_report.log"
"C:\Python313\python.exe" -m multiservice.curation_report >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\curation_report.log" 2>&1
echo [code retour %ERRORLEVEL%] >> "C:\Users\<user>\Claude\Projects\MultiService IA\logs\curation_report.log"
