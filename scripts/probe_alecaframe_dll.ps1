# probe_alecaframe_dll.ps1 — read-only DLL reflection probe.
#
# Purpose: enumerate AlecaFrameClientLib types/methods to find an entry point
# that fetches fresh inventory from DE (instead of just decrypting what
# AlecaFrame already wrote to lastData.dat).
#
# Run this on the Windows host where AlecaFrame is installed. Output is
# safe to share — it's just type/method names, no game data leaves the box.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\probe_alecaframe_dll.ps1
#
# Output: pretty-printed report on stdout + JSON dump at probe_dll_output.json
# next to the script.

[CmdletBinding()]
param(
    [string]$AlecaExtensionsRoot = "$env:LOCALAPPDATA\Overwolf\Extensions\afmcagbpgggkpdkokjhjkllpegnadmkignlonpjm"
)

$ErrorActionPreference = 'Stop'

function Fail([string]$msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $AlecaExtensionsRoot)) {
    Fail "AlecaFrame extension dir not found: $AlecaExtensionsRoot"
}

$versionDir = Get-ChildItem $AlecaExtensionsRoot -Directory -Force `
    | Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } `
    | Sort-Object { [version]$_.Name } -Descending `
    | Select-Object -First 1
if (-not $versionDir) { Fail "no version subdir under $AlecaExtensionsRoot" }

$netDir = Join-Path $versionDir.FullName 'NET'
Write-Host "AlecaFrame version: $($versionDir.Name)" -ForegroundColor Cyan
Write-Host "NET dir:            $netDir" -ForegroundColor Cyan
Write-Host ""

# --- load all .dll siblings (resolver for inter-DLL refs) ---------------
$loaded = @{}
$resolver = {
    param($src, $args)
    $name = ($args.Name -split ',')[0]
    $path = Join-Path $netDir "$name.dll"
    if (Test-Path $path) {
        if (-not $loaded.ContainsKey($name)) {
            $loaded[$name] = [System.Reflection.Assembly]::LoadFrom($path)
        }
        return $loaded[$name]
    }
    return $null
}
[AppDomain]::CurrentDomain.add_AssemblyResolve($resolver)

Get-ChildItem $netDir -Filter '*.dll' `
    | Where-Object { $_.Name -notmatch '^(7z|x64|x86)\.dll$' } `
    | ForEach-Object {
        try { [void][System.Reflection.Assembly]::LoadFrom($_.FullName) } catch { }
    }

$assemblies = [AppDomain]::CurrentDomain.GetAssemblies() `
    | Where-Object { $_.FullName -match '^AlecaFrame' }

Write-Host "Loaded AlecaFrame assemblies:" -ForegroundColor Yellow
$assemblies | ForEach-Object { Write-Host "  $($_.GetName().Name)" }
Write-Host ""

# --- enumerate types ----------------------------------------------------
# Filter to types we likely care about: anything with words that hint at
# network/API/DE/inventory in either the type name or its methods.
$interestingTypes = @()
$interestingMethods = @()

# Patterns suggesting "this code talks to DE servers".
$networkHints = @(
    'Http', 'Web', 'Client', 'Request', 'Response', 'Api',
    'Fetch', 'Pull', 'Poll', 'Refresh', 'Sync', 'Update',
    'Inventory', 'Login', 'Token', 'Session', 'Cookie', 'Auth',
    'Download', 'Server', 'Url', 'Endpoint'
)
$pattern = '(?i)' + ($networkHints -join '|')

foreach ($asm in $assemblies) {
    try { $types = $asm.GetTypes() }
    catch { $types = $_.Exception.Types | Where-Object { $_ -ne $null } }
    foreach ($t in $types) {
        if (-not $t.IsPublic -and -not $t.IsNestedPublic) { continue }
        $nameMatch = $t.FullName -match $pattern
        $matchedMethods = @()
        try {
            $methods = $t.GetMethods([System.Reflection.BindingFlags]'Public,Static,Instance,DeclaredOnly')
        } catch { $methods = @() }
        foreach ($m in $methods) {
            if ($m.Name -match '^(get_|set_|add_|remove_|ToString|Equals|GetHashCode|GetType)') { continue }
            if ($m.Name -match $pattern) {
                $params = @($m.GetParameters() | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ', '
                $matchedMethods += [pscustomobject]@{
                    type = $t.FullName
                    name = $m.Name
                    static = $m.IsStatic
                    returns = $m.ReturnType.FullName
                    params = $params
                }
            }
        }
        if ($nameMatch -or $matchedMethods.Count -gt 0) {
            $interestingTypes += [pscustomobject]@{
                fullName = $t.FullName
                assembly = $asm.GetName().Name
                methodHits = $matchedMethods.Count
            }
            $interestingMethods += $matchedMethods
        }
    }
}

# --- pretty print -------------------------------------------------------
Write-Host "=== Types matching network/inventory hints ===" -ForegroundColor Yellow
$interestingTypes | Sort-Object fullName | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Methods matching network/inventory hints (top 80) ===" -ForegroundColor Yellow
$interestingMethods `
    | Sort-Object type, name `
    | Select-Object -First 80 `
    | Format-Table type, name, static, returns, params -AutoSize -Wrap

Write-Host ""
Write-Host "Total interesting types:   $($interestingTypes.Count)" -ForegroundColor Cyan
Write-Host "Total interesting methods: $($interestingMethods.Count)" -ForegroundColor Cyan

# --- dump full report to JSON ------------------------------------------
$report = @{
    aleca_version = $versionDir.Name
    net_dir = $netDir
    assemblies = ($assemblies | ForEach-Object { $_.GetName().Name })
    types = $interestingTypes
    methods = $interestingMethods
}
$outPath = Join-Path $PSScriptRoot 'probe_dll_output.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $outPath -Encoding utf8
Write-Host ""
Write-Host "Full JSON report: $outPath" -ForegroundColor Green
