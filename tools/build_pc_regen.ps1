# rr6-nx: the PC build after the hook table changed. A hook added to a source is not an input of the code generator, and tools/direct_calls.py made
# its callers direct calls while the function was unhooked, so they would go on bypassing the hook: the generated code is made again. The passes
# rewrite renut_pch.h during the build, after the precompiled header's dependency was read, so that goes first and the build runs twice.
# -Generator: after a change to the SDK's code generator (sdk/src/codegen). rexglue skips codegen while generated/codegen.stamp's
# fingerprint matches, and that covers the input files, the SDK version and the flags but not the generator's own code, so a fixed
# builder compiles and never reaches the generated code. This removes the fingerprint too (every generated file is written again,
# so everything recompiles) and fails if the generator did not write a new one.
#   powershell -File tools/build_pc_regen.ps1 [-Name pc_buildN] [-Generator]
param([string]$Name = "pc_build_regen", [switch]$Generator)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$started = Get-Date
Remove-Item -Force "app\generated\codegen.build.stamp" -ErrorAction SilentlyContinue
if ($Generator) { Remove-Item -Force "app\generated\codegen.stamp" -ErrorAction SilentlyContinue }
$cmd = "$env:SystemRoot\System32\cmd.exe"
& $cmd /c "tools\build_pc.bat > out\$Name.a.log 2>&1"
Remove-Item -Force "app\out\pc\CMakeFiles\renut_recomp.dir\cmake_pch.hxx.pch" -ErrorAction SilentlyContinue
& $cmd /c "tools\build_pc.bat > out\$Name.log 2>&1"
"exit=$LASTEXITCODE"
if ($Generator -and -not ((Test-Path "app\generated\codegen.stamp") -and (Get-Item "app\generated\codegen.stamp").LastWriteTime -ge $started)) {
    "THE GENERATOR DID NOT RUN: generated/codegen.stamp is not new"
}
Select-String -Path "out\$Name.log" -Pattern ' error:|FAILED:|undefined symbol|multiply defined|fatal error' | Select-Object -First 12 | ForEach-Object { $_.Line.Substring(0, [Math]::Min(200, $_.Line.Length)) }
Get-Item "app\out\pc\renut.exe" | Select-Object Length, LastWriteTime | Format-List
