<#
.SYNOPSIS
    Orquestador de memoria_vectorial: ejecuta el pipeline completo y arranca el vigilante.

.DESCRIPTION
    Fases (cada una con latido de heartbeat y reintentos acotados):
      1 config      validación de configuración (si falla, se aborta)
      2 indexar     indexación incremental            (necesita LM Studio)
      3 aprender    aprendizaje local                 (necesita LM Studio)
      4 reindexar   indexa las notas recién creadas   (necesita LM Studio)
      5 skills      generación de skills              (necesita LM Studio)
      6 entidades   grafo de entidades
      7 repaso      cola de repetición espaciada
      8 tablero     Tablero, Huecos, Conocimiento, AprendidoHoy
      9 guardian    vigilancia (modo observación por defecto)
     10 backup      copia de seguridad con verificación
     11 estado      diagnóstico único publicado en Obsidian
     12 watch       arranca `indexer.py --watch` en segundo plano

    Un fallo en una fase se registra y el pipeline continúa con las demás.
    Si LM Studio no responde, las fases que lo necesitan se omiten (cuentan como fallo).

    Códigos de salida: 0 todo correcto | 2 hubo fallos.

    Parada limpia del vigilante: crear `.memoria\STOP` (lo hace `-Detener`).

.EXAMPLE
    .\iniciar.ps1
    .\iniciar.ps1 -MaxAprender 5 -SinBackup
    .\iniciar.ps1 -SinWatch
    .\iniciar.ps1 -Detener
#>
[CmdletBinding()]
param(
    [int]$MaxAprender = 3,
    [int]$MaxSkills = 3,
    [int]$Reintentos = 2,
    [int]$EsperaSegundos = 5,
    [string]$LmStudioHost = "127.0.0.1",
    [int]$LmStudioPuerto = 1234,
    [switch]$SinWatch,
    [switch]$SinBackup,
    [switch]$Detener,
    [string]$Python = ""
)

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

# ----------------------------------------------------------------- utilidades

function Resolve-Python {
    if ($Python -ne "") { return $Python }
    $venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venv) { return $venv }
    return "python"
}

$Py = Resolve-Python
$MemoriaDir = Join-Path $PSScriptRoot ".memoria"
$StopFile = Join-Path $MemoriaDir "STOP"
$PidFile = Join-Path $MemoriaDir "watch.pid"

if (-not (Test-Path $MemoriaDir)) {
    New-Item -ItemType Directory -Path $MemoriaDir -Force | Out-Null
}

function Write-Paso([string]$Mensaje, [string]$Color = "Cyan") {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Mensaje) -ForegroundColor $Color
}

function Send-Latido([string]$Paso) {
    & $Py heartbeat.py --paso $Paso 2>&1 | Out-Null
}

function Test-LmStudio {
    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $tarea = $cliente.ConnectAsync($LmStudioHost, $LmStudioPuerto)
        if ($tarea.Wait(2000) -and $cliente.Connected) { return $true }
        return $false
    }
    catch { return $false }
    finally { $cliente.Close() }
}

function Test-ProcesoVivo([int]$ProcId) {
    if ($ProcId -le 0) { return $false }
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

# ------------------------------------------------------------------- detener

if ($Detener) {
    New-Item -ItemType File -Path $StopFile -Force | Out-Null
    Write-Paso "Señal de parada creada: $StopFile" "Yellow"

    if (Test-Path $PidFile) {
        $watchPid = [int](Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $limite = (Get-Date).AddSeconds(60)

        while ((Test-ProcesoVivo $watchPid) -and ((Get-Date) -lt $limite)) {
            Start-Sleep -Seconds 2
        }

        if (Test-ProcesoVivo $watchPid) {
            Write-Paso "El vigilante (PID $watchPid) sigue activo tras 60 s; no se fuerza." "Red"
            exit 2
        }

        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Paso "Vigilante detenido." "Green"
    }

    exit 0
}

# ------------------------------------------------------------------ pipeline

$Resultados = New-Object System.Collections.ArrayList

function Invoke-Fase {
    param(
        [string]$Nombre,
        [string[]]$Argumentos,
        [bool]$Critica = $false,
        [bool]$RequiereLm = $false,
        [bool]$LmDisponible = $true
    )

    Send-Latido "iniciar.$Nombre"

    if ($RequiereLm -and -not $LmDisponible) {
        Write-Paso "$Nombre: OMITIDA (LM Studio no responde en ${LmStudioHost}:$LmStudioPuerto)" "Yellow"
        [void]$Resultados.Add([pscustomobject]@{ Fase = $Nombre; Estado = "omitida"; Intentos = 0 })
        return $false
    }

    $maxIntentos = 1 + [Math]::Max(0, $Reintentos)

    for ($intento = 1; $intento -le $maxIntentos; $intento++) {
        Write-Paso "$Nombre (intento $intento/$maxIntentos)"
        # Out-Host evita que la salida del comando contamine el valor devuelto por la función.
        & $Py @Argumentos | Out-Host
        $codigo = $LASTEXITCODE

        if ($codigo -eq 0) {
            [void]$Resultados.Add([pscustomobject]@{ Fase = $Nombre; Estado = "ok"; Intentos = $intento })
            return $true
        }

        Write-Paso "$Nombre terminó con código $codigo" "Yellow"

        if ($intento -lt $maxIntentos) {
            Start-Sleep -Seconds ($EsperaSegundos * $intento)
        }
    }

    [void]$Resultados.Add([pscustomobject]@{ Fase = $Nombre; Estado = "fallo"; Intentos = $maxIntentos })
    Write-Paso "$Nombre: FALLÓ tras $maxIntentos intentos" "Red"
    return $false
}

# El arranque borra una señal de parada anterior.
Remove-Item $StopFile -ErrorAction SilentlyContinue

Write-Paso "memoria_vectorial: inicio del ciclo" "Green"
Send-Latido "iniciar.inicio"

$lm = Test-LmStudio
if (-not $lm) {
    Write-Paso "LM Studio no responde; se omitirán las fases que lo necesitan." "Yellow"
}

if (-not (Invoke-Fase -Nombre "config" -Argumentos @("config.py", "--check") -Critica $true)) {
    Write-Paso "Configuración inválida: se aborta." "Red"
    exit 2
}

[void](Invoke-Fase -Nombre "indexar"   -Argumentos @("indexer.py", "--index") -RequiereLm $true -LmDisponible $lm)
[void](Invoke-Fase -Nombre "aprender"  -Argumentos @("aprender.py", "--max", "$MaxAprender") -RequiereLm $true -LmDisponible $lm)
[void](Invoke-Fase -Nombre "reindexar" -Argumentos @("indexer.py", "--index") -RequiereLm $true -LmDisponible $lm)
[void](Invoke-Fase -Nombre "skills"    -Argumentos @("crear_skills.py", "--max", "$MaxSkills") -RequiereLm $true -LmDisponible $lm)
[void](Invoke-Fase -Nombre "entidades" -Argumentos @("entidades.py"))
[void](Invoke-Fase -Nombre "repaso"    -Argumentos @("repaso.py"))
[void](Invoke-Fase -Nombre "tablero"   -Argumentos @("tablero.py"))
[void](Invoke-Fase -Nombre "guardian"  -Argumentos @("guardian.py", "--una-vez"))

if (-not $SinBackup) {
    [void](Invoke-Fase -Nombre "backup" -Argumentos @("backup.py", "--crear"))
}

[void](Invoke-Fase -Nombre "estado" -Argumentos @("estado.py", "--tablero"))

# ------------------------------------------------------------------- vigilante

if (-not $SinWatch) {
    $yaVivo = $false

    if (Test-Path $PidFile) {
        $previo = [int](Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $yaVivo = Test-ProcesoVivo $previo
    }

    if ($yaVivo) {
        Write-Paso "El vigilante ya está activo (PID $previo)." "Cyan"
    }
    elseif (-not $lm) {
        Write-Paso "watch: OMITIDO (LM Studio no responde)" "Yellow"
        [void]$Resultados.Add([pscustomobject]@{ Fase = "watch"; Estado = "omitida"; Intentos = 0 })
    }
    else {
        $logs = Join-Path $PSScriptRoot "..\Sistema\logs"
        if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }

        $proceso = Start-Process -FilePath $Py `
            -ArgumentList @("indexer.py", "--watch") `
            -WorkingDirectory $PSScriptRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logs "watch.out.log") `
            -RedirectStandardError (Join-Path $logs "watch.err.log") `
            -PassThru

        Set-Content -Path $PidFile -Value $proceso.Id
        Write-Paso "Vigilante iniciado (PID $($proceso.Id)). Para detenerlo: .\iniciar.ps1 -Detener" "Green"
        [void]$Resultados.Add([pscustomobject]@{ Fase = "watch"; Estado = "ok"; Intentos = 1 })
    }
}

# ---------------------------------------------------------------------- resumen

Send-Latido "iniciar.fin"
Write-Host ""
$Resultados | Format-Table -AutoSize | Out-String | Write-Host

$fallos = @($Resultados | Where-Object { $_.Estado -ne "ok" }).Count

if ($fallos -gt 0) {
    Write-Paso "Ciclo terminado con $fallos fase(s) con fallo u omitidas." "Red"
    exit 2
}

Write-Paso "Ciclo terminado sin fallos." "Green"
exit 0
