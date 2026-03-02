import json
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from transcribe import Transcriber
from pathlib import Path

app = FastAPI(title="Japanese Transcription API", version="1.0.0")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 Transcriber (建议放在 app 级别防止重复加载模型)
transcriber = Transcriber(model_size="medium")

# 定义存放音频和数据的目录
UPLOAD_DIR = Path("uploads")
DATA_DIR = Path("data_cache")
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


@app.post("/transcribe")
async def handle_transcription(file: UploadFile = File(...)):
    try:
        audio_path = UPLOAD_DIR / file.filename
        json_path = DATA_DIR / f"{Path(file.filename).stem}.json"

        # 1. 检查缓存
        if json_path.exists():
            data = Transcriber.load_data(str(json_path))
            return JSONResponse(content={"data": data}) # 统一包装在 data 键下

        # 2. 保存文件
        with open(audio_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 3. 执行识别 (现在的 data 是原始 List)
        raw_data = transcriber.transcribe(str(audio_path), str(json_path))

        # 关键修复：处理 NumPy 序列化问题
        # 强制将数据转为标准 Python 类型，防止 round() 后的 numpy.float 导致 500 错误
        serializable_data = json.loads(json.dumps(raw_data, ensure_ascii=False))

        return JSONResponse(content={"data": serializable_data})

    except Exception as e:
        import traceback
        traceback.print_exc() # 在控制台打印具体的报错栈，方便排查
        return JSONResponse(
            status_code=500,
            content={"error": f"处理失败: {str(e)}"}
        )


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)