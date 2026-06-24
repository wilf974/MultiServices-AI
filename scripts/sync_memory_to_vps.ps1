<#
.SYNOPSIS
  DEPRECATED (21 juin 2026) -- ne plus utiliser. Remplace par sync_memory_merge.ps1.

.DESCRIPTION
  Ce script faisait un push OVERWRITE (Windows -> VM) du journal. Depuis que la VM
  ECRIT aussi (catalogue des projets, decisions cote root), un overwrite EFFACERAIT
  les events propres a la VM. Utilise la fusion bidirectionnelle sans perte :

      pwsh scripts/sync_memory_merge.ps1

  (union par id, append-only, idempotente, snapshots .bak des deux cotes).
#>

Write-Output "[DEPRECATED] sync_memory_to_vps.ps1 fait un overwrite destructif."
Write-Output "             La VM ecrit desormais son propre journal -> un overwrite EFFACERAIT ses events."
Write-Output "             Utilise plutot la fusion bidirectionnelle sans perte :"
Write-Output ""
Write-Output "    pwsh scripts/sync_memory_merge.ps1"
Write-Output ""
exit 1
