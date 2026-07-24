' Lanceur SILENCIEUX generique pour les taches planifiees MultiService IA.
'
' Pourquoi : une tache planifiee "Interactive" qui lance python.exe ou pwsh.exe fait apparaitre
' une console, meme avec -WindowStyle Hidden (la fenetre est creee puis masquee -> flash visible).
' Le 2e argument de Run vaut 0 = fenetre MASQUEE : rien ne s'affiche, jamais. Le 3e (False) rend
' la main immediatement. L'alternative propre (LogonType S4U) exige des droits administrateur.
'
' Usage (action de la tache) :
'   wscript.exe "<...>\scripts\run_hidden.vbs" "<...>\scripts\taches\<nom>.cmd"
'
' UN SEUL argument, et c'est un CHEMIN. Raison mesuree le 24/07/2026 : wscript RETIRE les
' guillemets internes des arguments (`-c "print(1)"` arrive en `-c print(1)`), donc passer une
' ligne de commande complete est condamne des qu'elle contient un chemin entre guillemets.
' Chaque tache a donc son .cmd, qui porte sa commande ET sa redirection de journal.

Option Explicit

Dim sh, fso, cible

If WScript.Arguments.Count < 1 Then
    WScript.Quit 2                      ' appel malforme : on echoue franchement
End If

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

cible = WScript.Arguments(0)
If Not fso.FileExists(cible) Then
    WScript.Quit 3                      ' .cmd introuvable : idem, pas d'echec muet
End If

sh.Run """" & cible & """", 0, False
