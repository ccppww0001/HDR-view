"""ComfyUI 的 GPU 测试需要显式安装环境；缺失时明确跳过。"""

import pytest


def test_truehdr_execution_requires_explicit_comfyui_environment():
    pytest.importorskip("nvvfx")
    import torch

    if not torch.cuda.is_available():
        pytest.skip("无 CUDA；不伪造 TrueHDR 执行结果")
    pytest.skip("需要用户已安装并固定版本的 ComfyUI 工作流才能执行真实照片")
