<#
.SYNOPSIS
  Chat local (Ollama) avec capture journalisee - raccourci.
.DESCRIPTION
  Lance `python -m multiservice.chat --ollama` (modele qwen3.6 par defaut,
  thinking coupe - D13). Args optionnels transmis, ex :
    .\chat.ps1 --ollama-model qwen3.6:latest
    .\chat.ps1 --think
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot   # racine du projet (parent de scripts\)
Set-Location $proj
python -m multiservice.chat --ollama @args
