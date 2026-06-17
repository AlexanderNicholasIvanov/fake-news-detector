<#
.SYNOPSIS
  One-time native setup for the Fake-News Detector (no Docker, no admin).

.DESCRIPTION
  Idempotent. Prepares everything the launcher needs to run the stack natively,
  using a portable, EDB-free PostgreSQL + pgvector from conda-forge (so nothing
  is downloaded from EnterpriseDB and nothing is compiled):

    1. micromamba (single exe) under %LOCALAPPDATA%\FakeNewsDetector
    2. conda env with postgresql 16 + pgvector (matched, prebuilt win-64)
    3. a PostgreSQL data dir (initdb, trust auth on localhost)
    4. backend Python venv + dependencies (backend/.venv)
    5. frontend npm dependencies (frontend/node_modules)
    6. app role + database + the vector extension + migrations

  Prerequisites: Python 3.12 and Node.js/npm on PATH. Everything else is fetched.

  To instead restore an existing corpus dump (backups\fakenews.dump) rather than
  start empty, pass -RestoreDump.
#>
param(
  [switch]$RestoreDump
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $repo "backend"
$frontend = Join-Path $repo "frontend"

$base = Join-Path $env:LOCALAPPDATA "FakeNewsDetector"
$mm = Join-Path $base "micromamba.exe"
$prefix = Join-Path $base "pg"
$bin = Join-Path $prefix "Library\bin"
$pgdata = Join-Path $base "pgdata"
New-Item -ItemType Directory -Force $base | Out-Null
$env:MAMBA_ROOT_PREFIX = Join-Path $base "mamba"

# 1. micromamba ----------------------------------------------------------------
if (-not (Test-Path $mm)) {
  Write-Host "[setup] downloading micromamba ..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri 'https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64.exe' `
    -OutFile $mm -UseBasicParsing -TimeoutSec 180
}

# 2. conda env: postgresql 16 + pgvector --------------------------------------
if (-not (Test-Path (Join-Path $bin "pg_ctl.exe"))) {
  Write-Host "[setup] creating PostgreSQL 16 + pgvector env (conda-forge) ..." -ForegroundColor Cyan
  & $mm create -y -p $prefix -c conda-forge --no-rc "postgresql=16" pgvector
  if ($LASTEXITCODE -ne 0) { throw "conda env creation failed." }
}

# 3. data dir ------------------------------------------------------------------
if (-not (Test-Path (Join-Path $pgdata "PG_VERSION"))) {
  Write-Host "[setup] initdb ..." -ForegroundColor Cyan
  & (Join-Path $bin "initdb.exe") -D $pgdata -U postgres -E UTF8 --auth-host=trust --auth-local=trust
  if ($LASTEXITCODE -ne 0) { throw "initdb failed." }
}

# 4. backend venv + deps -------------------------------------------------------
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Write-Host "[setup] creating backend venv ..." -ForegroundColor Cyan
  python -m venv (Join-Path $backend ".venv")
}
Write-Host "[setup] installing backend deps ..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -e $backend --quiet
if ($LASTEXITCODE -ne 0) { throw "backend dependency install failed." }

# 5. frontend deps -------------------------------------------------------------
Write-Host "[setup] installing frontend deps ..." -ForegroundColor Cyan
Push-Location $frontend
try { npm install } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "npm install failed." }

# 6. start PG, create role/db, extension + schema -----------------------------
function Pg-Running { try { (New-Object Net.Sockets.TcpClient).Connect('localhost', 5432); $true } catch { $false } }
$startedPg = $false
if (-not (Pg-Running)) {
  Write-Host "[setup] starting PostgreSQL ..." -ForegroundColor Cyan
  & (Join-Path $bin "pg_ctl.exe") -D $pgdata -l (Join-Path $base "pg.log") -o "-p 5432" -w start
  $startedPg = $true
}
try {
  $psql = Join-Path $bin "psql.exe"
  Write-Host "[setup] ensuring role + database ..." -ForegroundColor Cyan
  & $psql -U postgres -h localhost -p 5432 -d postgres -v ON_ERROR_STOP=1 -c "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='fnd') THEN CREATE ROLE fnd LOGIN PASSWORD 'fnd_dev_password'; END IF; END `$`$;"
  "SELECT 'CREATE DATABASE fakenews OWNER fnd' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='fakenews')\gexec" | & $psql -U postgres -h localhost -p 5432 -d postgres -v ON_ERROR_STOP=1

  $dump = Join-Path $repo "backups\fakenews.dump"
  if ($RestoreDump -and (Test-Path $dump)) {
    Write-Host "[setup] restoring corpus from backups\fakenews.dump ..." -ForegroundColor Cyan
    & (Join-Path $bin "pg_restore.exe") -U postgres -h localhost -p 5432 -d fakenews --no-privileges $dump
  } else {
    Write-Host "[setup] enabling vector extension + applying migrations ..." -ForegroundColor Cyan
    & $psql -U postgres -h localhost -p 5432 -d fakenews -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;"
    $env:DATABASE_URL = "postgresql+psycopg://fnd:fnd_dev_password@localhost:5432/fakenews"
    Push-Location $backend
    try { & $venvPy -m alembic upgrade head } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed." }
  }
}
finally {
  if ($startedPg) { & (Join-Path $bin "pg_ctl.exe") -D $pgdata -m fast stop | Out-Null }
}

Write-Host "[setup] done. Launch with run-fakenews.exe" -ForegroundColor Green
