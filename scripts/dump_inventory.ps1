# dump_inventory.ps1 - decrypt AlecaFrame .dat files via the app's own DLL
#
# Loads AlecaFrameClientLib.dll, invokes public static methods to read the
# HWID-encrypted blobs, writes plain JSON to -OutDir.
#
# Exit codes:
#   0 - success
#   2 - AlecaFrame install not found
#   3 - DLL load failed
#   4 - decryption failed
#
# Output: one JSON object on stdout (status, paths, sizes, timing).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [string]$AlecaExtensionsRoot = "$env:LOCALAPPDATA\Overwolf\Extensions\afmcagbpgggkpdkokjhjkllpegnadmkignlonpjm",

    [string]$AlecaDataDir = "$env:LOCALAPPDATA\AlecaFrame"
)

$ErrorActionPreference = 'Stop'
$started = Get-Date

function Emit-Result([hashtable]$result) {
    $result.elapsed_ms = [int]((Get-Date) - $started).TotalMilliseconds
    $result | ConvertTo-Json -Depth 6 -Compress
}

# --- locate the extension version dir ------------------------------------
if (-not (Test-Path $AlecaExtensionsRoot)) {
    Emit-Result @{ ok = $false; error = "AlecaFrame extension dir not found: $AlecaExtensionsRoot"; code = 2 }
    exit 2
}
$versionDir = Get-ChildItem $AlecaExtensionsRoot -Directory -Force `
    | Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } `
    | Sort-Object { [version]$_.Name } -Descending `
    | Select-Object -First 1
if (-not $versionDir) {
    Emit-Result @{ ok = $false; error = "no version sub-folder under $AlecaExtensionsRoot"; code = 2 }
    exit 2
}
$netDir = Join-Path $versionDir.FullName 'NET'
$mainDll = Join-Path $netDir 'AlecaFrameClientLib.dll'
if (-not (Test-Path $mainDll)) {
    Emit-Result @{ ok = $false; error = "missing $mainDll"; code = 2 }
    exit 2
}

# --- load the lib + siblings --------------------------------------------
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

try {
    Get-ChildItem $netDir -Filter '*.dll' `
        | Where-Object { $_.Name -notmatch '^(7z|x64|x86)\.dll$' } `
        | ForEach-Object {
            try { [void][System.Reflection.Assembly]::LoadFrom($_.FullName) } catch { }
        }
    $lib = [AppDomain]::CurrentDomain.GetAssemblies() `
        | Where-Object { $_.FullName -match '^AlecaFrameClientLib' } `
        | Select-Object -First 1
    if (-not $lib) { throw "AlecaFrameClientLib not loaded" }
    $misc = $lib.GetType('AlecaFrameClientLib.Utils.Misc')
    if (-not $misc) { throw "type AlecaFrameClientLib.Utils.Misc not found" }
} catch {
    Emit-Result @{ ok = $false; error = "DLL load failed: $($_.Exception.Message)"; code = 3 }
    exit 3
}

# --- decrypt + write -----------------------------------------------------
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$result = @{ ok = $true; files = @{} }

function Read-Or-Skip([string]$srcFile, [string]$dstFile, [string]$method, [object[]]$methodArgs) {
    if (-not (Test-Path $srcFile)) {
        return @{ skipped = $true; reason = "source missing: $srcFile" }
    }
    try {
        $m = $misc.GetMethod($method)
        # PowerShell can wrap strings as PSObject; .NET reflection then refuses the cast.
        # Build a typed object[] with raw strings so reflection sees System.String.
        $typedArgs = [object[]]::new($methodArgs.Length)
        for ($i = 0; $i -lt $methodArgs.Length; $i++) {
            $a = $methodArgs[$i]
            $typedArgs[$i] = if ($a -is [string]) { [string]$a } else { $a }
        }
        $json = $m.Invoke($null, $typedArgs)
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($dstFile, $json, $utf8)
        return @{
            bytes      = (Get-Item $dstFile).Length
            chars      = $json.Length
            written_at = (Get-Item $dstFile).LastWriteTimeUtc.ToString('o')
        }
    } catch {
        $msg = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        return @{ error = $msg }
    }
}

$lastDataSrc = Join-Path $AlecaDataDir 'lastData.dat'
$deltasSrc   = Join-Path $AlecaDataDir 'deltas.dat'

$result.files.lastData = Read-Or-Skip $lastDataSrc (Join-Path $OutDir 'lastData.json') 'ReadLastDataFile' @()
$result.files.deltas   = Read-Or-Skip $deltasSrc   (Join-Path $OutDir 'deltas.json')   'ReadAllTextEncrypted' @($deltasSrc)

# --- meta ----------------------------------------------------------------
$result.meta = @{
    aleca_version    = $versionDir.Name
    aleca_data_dir   = $AlecaDataDir
    extension_dir    = $versionDir.FullName
    wfm_username     = (Get-Content (Join-Path $AlecaDataDir 'lastUsername.txt') -ErrorAction SilentlyContinue)
    cached_json_dir  = (Join-Path $AlecaDataDir 'cachedData\json')
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    (Join-Path $OutDir '_meta.json'),
    ($result | ConvertTo-Json -Depth 10),
    $utf8
)

# any per-file errors -> exit 4
$failed = @($result.files.GetEnumerator() | Where-Object { $_.Value.error })
if ($failed.Count -gt 0) {
    $result.ok = $false
    $result.code = 4
    Emit-Result $result
    exit 4
}

Emit-Result $result
exit 0
