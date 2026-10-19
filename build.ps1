$ErrorActionPreference='Stop'
$vsFind=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath=& $vsFind -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsPath){throw 'Install Visual Studio 2022 C++ Build Tools and Windows SDK.'}
$vcvars=Join-Path $vsPath 'VC/Auxiliary/Build/vcvars64.bat'
$cm=Join-Path $vsPath 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
$pkg=Join-Path $PSScriptRoot 'libssh2-1.11.1.tar.gz'
$expected='d9ec76cbe34db98eec3539fe2c899d26b0c837cb3eb466a56b0f109cabf658f7'
if((Get-FileHash -LiteralPath $pkg -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw 'Dependency archive hash mismatch.'}
$deps=Join-Path $PSScriptRoot '.build'
New-Item -ItemType Directory -Path $deps -Force | Out-Null
if(-not (Test-Path -LiteralPath (Join-Path $deps 'libssh2-1.11.1'))){& tar.exe -xf $pkg -C $deps;if($LASTEXITCODE){throw 'Dependency extraction failed.'}}
$source=Join-Path $deps 'libssh2-1.11.1'
$build=Join-Path $deps 'libssh2-build'
& $cm -S $source -B $build -G 'Visual Studio 17 2022' -A x64 -DCRYPTO_BACKEND=WinCNG -DBUILD_SHARED_LIBS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF -DENABLE_ZLIB_COMPRESSION=OFF -DCMAKE_POLICY_DEFAULT_CMP0091=NEW -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
if($LASTEXITCODE){throw 'CMake configure failed.'}
& $cm --build $build --config Release --parallel 2
if($LASTEXITCODE){throw 'SSH dependency build failed.'}
$inc=Join-Path $source 'include';$lib=Join-Path $build 'src/Release/libssh2.lib'
Push-Location $PSScriptRoot
try {
 $command='call "{0}" >nul && rc /nologo SiteBackup.rc && cl /nologo /std:c++17 /utf-8 /O2 /EHsc /MT /DUNICODE /D_UNICODE /DLIBSSH2_STATIC /I"{1}" SiteBackup.cpp SiteBackup.res "{2}" /Fe:DroBinGBackup.exe /link /SUBSYSTEM:WINDOWS Ws2_32.lib Bcrypt.lib Crypt32.lib Advapi32.lib Shell32.lib Ole32.lib User32.lib Gdi32.lib /DYNAMICBASE /NXCOMPAT' -f $vcvars,$inc,$lib
 & cmd.exe /d /s /c $command
 if($LASTEXITCODE -ne 0){throw "Build failed: $LASTEXITCODE"}
} finally {Pop-Location}
