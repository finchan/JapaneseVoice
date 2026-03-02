"""
Japanese Speech Transcription Module

Provides a clean class-based interface for transcribing Japanese audio files
using faster-whisper with word-level timestamps.
"""

from faster_whisper import WhisperModel
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from starlette.responses import JSONResponse


class Transcriber:
    """
    Transcriber class for Japanese speech transcription using faster-whisper.

    Usage:
        >>> transcriber = Transcriber()
        >>> transcriber.transcribe("audio.mp3", "output.json")
        >>> data = Transcriber.load_data("output.json")
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ja",
        beam_size: int = 10,
    ):
        """
        Initialize the Whisper model.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
            device: Computation device ("cpu" or "cuda")
            compute_type: Quantization type ("int8" for CPU, "float16" for GPU)
            language: Target language code
            beam_size: Decoding beam width
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        """Lazy load the Whisper model."""
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: str, output_path: str = "data.json") -> List[Dict[str, Any]]:
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=self.beam_size,
            language=self.language,
            word_timestamps=True,
            # 新增下面这一行，引导模型多用汉字
            initial_prompt="こんにちは。今日は漢字とかなを使って日本語で話します。"
        )

        print(f"Detected language: {info.language} (confidence: {info.language_probability:.2f})")

        results: List[Dict[str, Any]] = []
        for segment in segments:
            line_data = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text,
                "words": [
                    {"word": w.word, "start": round(w.start, 2), "end": round(w.end, 2)}
                    for w in segment.words
                ]
            }
            results.append(line_data)
            print(f"[{line_data['start']}s -> {line_data['end']}s] {line_data['text']}")

        self._save_json(results, output_path)
        return results

    @staticmethod
    def _save_json(data: List[Dict[str, Any]], output_path: str) -> None:
        """Save transcription data to JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Transcription saved to: {output_path}")

    @staticmethod
    def load_data(json_path: str = "data.json") -> List[Dict[str, Any]]:
        """
        Load transcription data from JSON file.

        Args:
            json_path: Path to the JSON file (default: "data.json")

        Returns:
            List of transcription segments

        Raises:
            FileNotFoundError: If the JSON file does not exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcription file not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
