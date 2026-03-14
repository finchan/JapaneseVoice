"""
Japanese Speech Transcription Module (Standard Version)
"""
import os

from faster_whisper import WhisperModel
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import COMPUTE_TYPE

class Transcriber:
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = COMPUTE_TYPE,
        language: str = "ja",
        beam_size: int = 5,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            # 1. 自动识别用户根目录 (Windows: C:\Users\Admin, Linux: /home/user)
            user_home = os.path.expanduser("~")

            # 2. 匹配你下载的文件夹名称
            local_folder_name = "faster-whisper-large-v3-turbo-ct2"

            # 3. 构造本地路径：~/.cache/huggingface/hub/faster-whisper-large-v3-turbo-ct2
            local_path = os.path.join(user_home, ".cache", "huggingface", "hub", local_folder_name)

            # 4. 强制指向本地，如果不存在则回退名称（但因为服务器断网，找不到路径会报错而不是下载）
            target = local_path if os.path.exists(local_path) else self.model_size

            if os.path.exists(local_path):
                print(f"--- 离线模式：已锁定本地路径 {local_path} ---")

            # 5. 针对 2 核 CPU 优化
            self._model = WhisperModel(
                target,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=1,  # 修改为 1，确保不会占满 2 核 CPU，留出资源给系统
                num_workers=1
            )
        return self._model

    def transcribe(self, audio_path: str, output_path: str = "data.json") -> List[Dict[str, Any]]:
        # 还原：移除 initial_prompt 中的强制注音暗示，恢复正常识别
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=self.beam_size,
            language=self.language,
            word_timestamps=True,
            initial_prompt="こんにちは。今日は漢字とかなを使って日本語で話します。"
        )

        print(f"Detected language: {info.language} (confidence: {info.language_probability:.2f})")

        results: List[Dict[str, Any]] = []
        for segment in segments:
            # 还原：只保留单词、开始和结束时间
            line_data = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text,
                "words": [
                    {
                        "word": w.word,
                        "start": round(w.start, 2),
                        "end": round(w.end, 2)
                    } for w in segment.words
                ]
            }
            print(f"[{line_data['start']}-{line_data['end']}]: {line_data['text']}")
            results.append(line_data)

        self._save_json(results, output_path)
        return results

    @staticmethod
    def _save_json(data: List[Dict[str, Any]], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_data(json_path: str = "data.json") -> List[Dict[str, Any]]:
        path = Path(json_path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)