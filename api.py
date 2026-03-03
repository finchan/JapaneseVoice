import json as python_json
import uvicorn
import httpx  # 确保已安装: pip install httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from transcribe import Transcriber
from pathlib import Path

app = FastAPI(title="Japanese Transcription API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

transcriber = Transcriber(model_size="medium")

UPLOAD_DIR = Path("uploads")
DATA_DIR = Path("data_cache")
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


@app.get("/translate")
async def translate_word(keyword: str = Query(..., description="要查询的日语单词")):
    # 清理关键词，去除换行和空格
    clean_keyword = keyword.strip().replace("\n", "").replace("\r", "")
    if not clean_keyword:
        return {"data": []}

    # 有道词典接口：le=jap 代表日语，doctype=json 返回 JSON
    youdao_url = f"https://dict.youdao.com/suggest?q={clean_keyword}&le=jap&doctype=json"

    async with httpx.AsyncClient() as client:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
            }
            response = await client.get(youdao_url, headers=headers, timeout=5.0)

            if response.status_code != 200:
                return JSONResponse(status_code=response.status_code, content={"error": "有道接口异常"})

            data = response.json()
            # 提取 entries 列表
            result = data.get("data", {}).get("entries", [])
            return {"data": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/transcribe")
async def handle_transcription(file: UploadFile = File(...)):
    # ... 原有代码保持不变 ...
    try:
        audio_path = UPLOAD_DIR / file.filename
        json_path = DATA_DIR / f"{Path(file.filename).stem}.json"
        if json_path.exists():
            data = Transcriber.load_data(str(json_path))
            return JSONResponse(content={"data": data})
        with open(audio_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        raw_data = transcriber.transcribe(str(audio_path), str(json_path))
        serializable_data = python_json.loads(python_json.dumps(raw_data, ensure_ascii=False))
        return JSONResponse(content={"data": serializable_data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)