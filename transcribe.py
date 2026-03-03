"""
Japanese Speech Transcription Module (Standard Version)
"""

from faster_whisper import WhisperModel
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

class Transcriber:
    def __init__(
        self,
        model_size: str = "medium",
        device: str = "cpu",
        compute_type: str = "int16",
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
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
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
            print(f"[{line_data.start}-{line_data.end}]: {line_data.text}")
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