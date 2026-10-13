@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv312\Scripts\python.exe" (
    echo [ERROR] Run SETUP_WINDOWS.bat first.
    exit /b 1
)
rem Verified Windows/GTX1650Ti stack: CUDA12.6 and cuDNN9 from Torch's wheel.
".venv312\Scripts\python.exe" -m pip install --upgrade torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -m pip uninstall -y onnxruntime
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -m pip install onnxruntime-gpu==1.20.2
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -c "import torch,onnxruntime as ort; assert torch.cuda.is_available(), 'CUDA Torch unavailable'; assert 'CUDAExecutionProvider' in ort.get_available_providers(), 'ORT CUDA unavailable'; from src.vision.cchess_recognizer import CChessRecognizer; r=CChessRecognizer('models/cchess/pose_4_v6.onnx','models/cchess/layout_nano_v3.onnx',use_gpu=True); assert 'CUDAExecutionProvider' in r.pose_session.get_providers() and 'CUDAExecutionProvider' in r.layout_session.get_providers(), 'ORT fell back to CPU'; r.pose_session.run(None,{r.pose_input_name:__import__('numpy').zeros((1,3,256,256),dtype='float32')}); print('GPU verified:',torch.cuda.get_device_name(0))"
if errorlevel 1 exit /b 1
echo GPU setup complete. VISION_DEVICE defaults to auto; set VISION_DEVICE=cpu to use CPU.
exit /b 0
