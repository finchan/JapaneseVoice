import logging
from faster_whisper import WhisperModel

# 开启调试日志，查看加载过程停在哪一步
logging.basicConfig(level=logging.DEBUG)

model_path = "/root/.cache/huggingface/hub/models--Systran--faster-whisper-medium/snapshots/08e178d48790749d25932bbc082711ddcfdfbc4f"
# 或者直接用仓库名，它会自动去 cache 找
model_size = "medium"

try:
    print("正在加载模型...")
    # 如果没有 GPU，请确保 device="cpu"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print("模型加载成功！")

    # 随便找个 1 秒的音频测试
    segments, info = model.transcribe("m1.mp3")
    print("识别结果:", list(segments))
except Exception as e:
    print(f"运行出错: {e}")