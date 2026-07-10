@echo off
REM install_offline.bat
REM TARGET SIDE (AIRGAPPED, no network). Run from inside the offline_bundle folder.
REM Steps 1-3 are PRIVILEGED system installs (admin), NOT pip. Step 4 is the offline pip install
REM that "takes from the bundle instead of the network" via --no-index --find-links.

setlocal

echo === 1. VC++ x64 runtime (silent) ===
vc_redist.x64.exe /install /quiet /norestart

echo === 2. NVIDIA driver ===
echo     Run the bundled NVIDIA driver .exe as Administrator, then REBOOT.
echo     (Kernel-mode install, governed by site IT policy -- cannot be scripted/silent here.)
echo     This is the only piece a wheel cannot supply (provides nvcuda.dll). Re-run this script after reboot.
where nvidia-smi >nul 2>nul || (echo     Driver not detected yet -- install it and reboot before continuing. & pause)

echo === 3. Python (only if not present) ===
where python >nul 2>nul || (echo     Install python-3.12.x-amd64.exe with "Add python.exe to PATH", then re-run this script. & exit /b 1)

echo === 4. OFFLINE pip install -- all requirements pulled from .\wheels, network never touched ===
python -m venv app_env && call app_env\Scripts\activate
python -m pip install --no-index --find-links=.\wheels --upgrade pip
python -m pip install --no-index --find-links=.\wheels -r requirements.txt || goto :err

echo === 5. prove the GPU path (cuda.is_available()==True is NOT proof kernels run) ===
python gpu_selfcheck.py || goto :err

echo.
echo OK. Launch the app with:
echo     call app_env\Scripts\activate ^&^& streamlit run disc5_gui_app.py
goto :eof

:err
echo OFFLINE INSTALL FAILED -- see error above. & exit /b 1
