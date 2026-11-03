@echo off
rem Builds bin\dinput8.dll (x64) with Visual Studio 2022's compiler.
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~dp0"
if not exist bin mkdir bin
if not exist obj mkdir obj
cl /nologo /O2 /W4 /LD /Foobj\ dynspaces.c /Fe:bin\dinput8.dll /link /NOLOGO user32.lib
