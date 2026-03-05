import json as python_json
import uvicorn
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
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

@app.get("/translate_mazii")
async def translate_mazii(keyword: str = Query(...)):
    clean_keyword = keyword.strip().replace("\n", "").replace("\r", "")
    url = "https://mazii.net/api/search"

    # Mazii API payload {dict: "jacn", type: "kanji", query: "暖かい", page: 1}
    payload = {
        "dict": "jatw",  # Japanese to jatw/jaen/jacn
        "type": "word",
        "query": clean_keyword,
        "limit": 1
    }

    async with httpx.AsyncClient() as client:
        try:
            # Mazii often requires a custom User-Agent to allow the request
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await client.post(url, json=payload, headers=headers, timeout=5.0)
            data = response.json()

            # Mazii returns 'data' as a list of words
            return {"data": data.get("data", [])}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})


# @app.post("/transcribe")
# async def handle_transcription(file: UploadFile = File(...)):
#     try:
#         audio_path = UPLOAD_DIR / file.filename
#         json_path = DATA_DIR / f"{Path(file.filename).stem}.json"
#         if json_path.exists():
#             data = Transcriber.load_data(str(json_path))
#             return JSONResponse(content={"data": data})
#         with open(audio_path, "wb") as buffer:
#             content = await file.read()
#             buffer.write(content)
#         raw_data = transcriber.transcribe(str(audio_path), str(json_path))
#         serializable_data = python_json.loads(python_json.dumps(raw_data, ensure_ascii=False))
#         return JSONResponse(content={"data": serializable_data})
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})
@app.post("/transcribe")
async def handle_transcription(
        file: UploadFile = File(...),
        role: str = Form(...)  # 接收前端传来的 'admin' 或 'guest'
):
    try:
        # 1. 根据角色确定子文件夹名称
        sub_folder = "permanent" if role.lower() == "admin" else "temporary"

        # 2. 动态构建上传和数据存储目录 (例如: uploads/storage/permanent)
        current_upload_dir = UPLOAD_DIR / "storage" / sub_folder
        current_data_dir = DATA_DIR / "storage" / sub_folder

        # 确保这些物理目录存在
        current_upload_dir.mkdir(parents=True, exist_ok=True)
        current_data_dir.mkdir(parents=True, exist_ok=True)

        # 3. 定义文件的完整路径
        audio_path = current_upload_dir / file.filename
        json_path = current_data_dir / f"{Path(file.filename).stem}.json"

        # 4. 如果缓存存在，直接返回对应角色目录下的缓存
        if json_path.exists():
            data = Transcriber.load_data(str(json_path))
            return JSONResponse(content={"data": data})

        # 5. 写入文件到对应角色的存储目录
        with open(audio_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 6. 调用转写逻辑，并将结果存入对应角色的数据目录
        raw_data = transcriber.transcribe(str(audio_path), str(json_path))

        serializable_data = python_json.loads(python_json.dumps(raw_data, ensure_ascii=False))
        return JSONResponse(content={"data": serializable_data})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)