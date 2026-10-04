param(
    [Parameter(Mandatory = $true)]
    [string]$Image,

    [string]$Platform = "linux/amd64",

    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$imageDir = Join-Path $scriptDir "image"

docker build --platform $Platform -t $Image $imageDir

if (-not $NoPush) {
    docker push $Image
}

Write-Host "Image ready: $Image"

