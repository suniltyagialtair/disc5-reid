# gpu_selfcheck.py
# Run ONCE on the airgapped target after installing the NVIDIA driver, to prove the GPU path works
# BEFORE trusting the app. Encodes the hard-won lesson: cuda.is_available()==True only proves a
# device is visible, NOT that kernels for THIS card's arch actually run. A cu126/cpu wheel on a
# Blackwell card reports a device but has no sm_120 kernels. So we also check get_arch_list() and
# force a real kernel launch.

import sys
import torch

print('torch           :', torch.__version__)
print('cuda available  :', torch.cuda.is_available())
print('arch list       :', torch.cuda.get_arch_list())

if not torch.cuda.is_available():
    sys.exit('FAIL: no CUDA device. Install the CUDA-13-capable NVIDIA driver on the target first.')

archs = torch.cuda.get_arch_list()
if not any(('sm_120' in a) or a.endswith('120') for a in archs):
    sys.exit('FAIL: this torch build has no sm_120 kernels (not a cu130 wheel). '
             'Rebuild the bundle with torch ...+cu130.')

# force an actual kernel launch on the device (the real proof)
try:
    x = torch.randn(40000, device='cuda').view(1, 1, 40000)
    _ = float((x * 2.0).sum().item())
    torch.cuda.synchronize()
except Exception as e:
    sys.exit(f'FAIL: kernel launch errored on {torch.cuda.get_device_name(0)}: {e}')

print('device          :', torch.cuda.get_device_name(0))
print('PASS: cu130 kernels launch on this card. The app will use the GPU.')
