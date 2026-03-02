# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Japanese Speech Transcription Service - transcribes Japanese audio files to text with word-level timestamps using the faster-whisper library. Exposes transcription data via a FastAPI REST API.

## Core Architecture

### Main Modules

- **`transcribe.py`** - Core transcription module
  - `Transcriber` class: Wraps `faster_whisper.WhisperModel` with lazy loading
  - `transcribe()` function: Convenience function for one-off transcriptions
  - `get_data()` / `load_data()`: Static methods to load saved JSON transcription data
  - Output format: JSON array of segments with `start`, `end`, `text`, and `words[]` (word-level timestamps)

- **`api.py`** - FastAPI REST API
  - `GET /` - Health check endpoint
  - `GET /transcription` - Returns transcription data from `data.json`
  - Runs on uvicorn with auto-reload enabled

### Key Design Decisions

- **Lazy model loading**: WhisperModel is loaded on first access via `@property` decorator
- **Word-level timestamps enabled by default**: Supports karaoke-style highlighting
- **Default language**: Japanese (`ja`)
- **Default model**: "small" size, int8 quantization for CPU
- **JSON output**: UTF-8 encoded with `ensure_ascii=False` for Japanese character preservation

## Development Commands

### Install dependencies
```bash
pip install faster-whisper fastapi uvicorn
```

### Run transcription (direct execution)
```bash
python transcribe.py
```

### Run API server
```bash
python api.py
# Server runs on http://0.0.0.0:8000
```

### Use transcriber programmatically
```python
from transcribe import transcribe, get_data

# Transcribe audio to JSON
transcribe("audio.mp3", "output.json")

# Load existing transcription data
data = get_data("output.json")
```

## Important Notes

- The API's `/transcription` endpoint currently re-transcribes the hardcoded `9-2-dialog.mp3` file on each request (inefficient for production)
- CORS is currently enabled for all origins (`allow_origins=["*"]`)
- Default device is CPU - for GPU acceleration, initialize `Transcriber` with `device="cuda"` and `compute_type="float16"`
