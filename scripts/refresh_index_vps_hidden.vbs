' Lanceur SILENCIEUX du rafraichissement d'index (tache planifiee hebdomadaire).
'
' Pourquoi ce detour : une tache planifiee "Interactive" lancant pwsh directement fait apparaitre
' une console, meme avec -WindowStyle Hidden (la fenetre est creee puis masquee -> flash visible).
' Le 2e argument de Run vaut 0 = fenetre MASQUEE : rien ne s'affiche, jamais.
' L'alternative propre (LogonType S4U) exige des droits administrateur ; ceci n'en demande aucun.
'
' Le 3e argument False = ne pas attendre la fin (la tache rend la main tout de suite).
' La sortie du script part dans logs\refresh_index_vps.log (redirection ci-dessous).

Option Explicit

Dim sh, fso, racine, script, journal, commande
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

racine  = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
script  = racine & "\scripts\refresh_index_vps.ps1"
journal = racine & "\logs\refresh_index_vps.log"

If Not fso.FolderExists(racine & "\logs") Then
    fso.CreateFolder racine & "\logs"
End If

commande = "pwsh.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command " & _
           """& '" & script & "' *>> '" & journal & "'"""

sh.Run commande, 0, False
