@ECHO OFF
pushd %~dp0
set SPHINXBUILD=.venv\Scripts\sphinx-build.exe
set SOURCEDIR=source
set BUILDDIR=build
set SPHINXOPTS=-W --keep-going

if "%1" == "" goto html
if "%1" == "html" goto html
if "%1" == "linkcheck" goto linkcheck
if "%1" == "clean" goto clean
if "%1" == "watch" goto watch
goto unknown

:html
%SPHINXBUILD% -b html %SOURCEDIR% %BUILDDIR%\html %SPHINXOPTS%
goto end

:linkcheck
%SPHINXBUILD% -b linkcheck %SOURCEDIR% %BUILDDIR%\linkcheck %SPHINXOPTS%
goto end

:watch
.venv\Scripts\sphinx-autobuild.exe -a %SOURCEDIR% %BUILDDIR%\html
goto end

:clean
if exist %BUILDDIR% rmdir /s /q %BUILDDIR%
goto end

:unknown
echo Unknown target: %1
echo Available: html, watch, linkcheck, clean

:end
popd
