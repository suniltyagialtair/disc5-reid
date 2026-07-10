@echo off
REM build_gui.bat — build the DISC5 SKANN GUI on the GPU VM (Windows).
REM Run from the folder containing disc5_gui.spec and disc5_arcface_8k_ft2_ep003.pth.

echo === DISC5 GUI build ===

REM 1) GPU torch must be installed in this env for the frozen app to use CUDA on the VM.
REM    If `python -c "import torch;print(torch.cuda.is_available())"` prints False, install the
REM    CUDA wheel for your VM's CUDA version, e.g.:
REM      pip install torch --index-url https://download.pytorch.org/whl/cu121
python -c "import torch;print('CUDA available:',torch.cuda.is_available())"

REM 2) install the rest
pip install -r requirements.txt

REM 3) sanity: weights present?
if not exist "disc5_arcface_8k_ft2_ep003.pth" (
  echo ERROR: disc5_arcface_8k_ft2_ep003.pth not found beside this script. Copy it here first.
  exit /b 1
)

REM 4) freeze (onedir)
pyinstaller disc5_gui.spec --noconfirm

echo.
echo === Build done. App at: dist\disc5_gui\disc5_gui.exe ===
echo Launch it; a console window shows the URL (http://localhost:8520) and opens the browser.
echo gallery.npz / gallery_tonal.json are written next to disc5_gui.exe.
pause
