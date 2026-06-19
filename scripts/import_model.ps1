<#
.SYNOPSIS
  Importe le GGUF eve-qwen3-8b dans Ollama (une seule fois).
.DESCRIPTION
  Cree un modele Ollama "eve-qwen3-8b" a partir du Modelfile (qui pointe vers le .gguf).
  Ensuite : .\scripts\chat.ps1  (le modele par defaut est deja eve-qwen3-8b).
.PARAMETER Name
  Nom du modele Ollama a creer (defaut eve-qwen3-8b - doit matcher config.OLLAMA_MODEL).
#>
[CmdletBinding()]
param(
    [string] $Name = "eve-qwen3-8b",
    [string] $Modelfile = (Join-Path $PSScriptRoot "eve.Modelfile")
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Modelfile)) { throw "Modelfile introuvable : $Modelfile" }

Write-Host "Creation du modele Ollama '$Name' depuis $Modelfile ..."
ollama create $Name -f $Modelfile
Write-Host ""
Write-Host "[OK] Modele '$Name' pret. Verifie : ollama list"
Write-Host "Lance le chat : .\scripts\chat.ps1"
