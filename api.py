import os
import uvicorn
import httpx
import edge_tts
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from transcribe import Transcriber
from pathlib import Path
import sqlite3
import shutil

app = FastAPI(title="Japanese Transcription API", version="1.0.0")
# 【第一处：路径检查打印】
# 放在这里，每次运行后台，控制台第一行就会告诉你它在哪个目录下找资源
print("="*50)
print(f"当前 Python 运行的工作目录 (CWD): {os.getcwd()}")
print(f"FastAPI 尝试挂载的资源绝对路径: {Path('resources').resolve()}")
print("="*50)

# 【第二处：挂载静态目录】
# 确保 directory="resources" 对应的文件夹就在上面打印出的路径里
app.mount("/resources", StaticFiles(directory="resources"), name="resources")

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

@app.get("/api/manage/files")
async def list_permanent_files():
    """获取永久存储目录下的所有 MP3 和对应的 JSON 文件"""
    audio_dir = UPLOAD_DIR / "storage" / "permanent"
    json_dir = DATA_DIR / "storage" / "permanent"

    # 确保目录存在
    audio_dir.mkdir(parents=True, exist_ok=True)

    files_list = []
    # 扫描所有的 mp3 文件
    for idx, audio_file in enumerate(sorted(audio_dir.glob("*.mp3"))):
        base_name = audio_file.stem  # 获取不带后缀的文件名
        json_file_name = f"{base_name}.json"

        # 检查对应的 JSON 是否存在
        has_json = (json_dir / json_file_name).exists()

        files_list.append({
            "id": idx + 1,
            "mp3": audio_file.name,
            "json": json_file_name if has_json else "Missing JSON"
        })

    return JSONResponse(content={"files": files_list})


@app.post("/api/manage/submit")
async def handle_manage_submit(
        book: str = Form(...),
        course: str = Form(...),
        selected_file: str = Form(...)
):
    try:
        # 1. 解析文件名
        # "9-1-text.mp3 | 9-1-text.json" -> ["9-1-text.mp3", "9-1-text.json"]
        parts = [p.strip() for p in selected_file.split("|")]
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid file pair format")

        filename = selected_file.split(".")[0]

        mp3_filename, json_filename = parts[0], parts[1]

        # 2. 构建物理路径
        # 目标文件夹: resources/书籍/课程
        target_dir = Path("resources") / book / course
        target_dir.mkdir(parents=True, exist_ok=True)

        source_mp3 = UPLOAD_DIR / "storage" / "permanent" / mp3_filename
        source_json = DATA_DIR / "storage" / "permanent" / json_filename

        dest_mp3_path = target_dir / mp3_filename
        dest_json_path = target_dir / json_filename

        # 3. 执行物理移动 (Move)
        if source_mp3.exists():
            shutil.move(str(source_mp3), str(dest_mp3_path))
        if source_json.exists() and json_filename != "Missing JSON":
            shutil.move(str(source_json), str(dest_json_path))

        # 4. 数据库操作
        db_path = Path("db/jvdb.sqlite")
        db_path.parent.mkdir(exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 准备插入数据
        # 字段: book, course, filename, format, location
        records = [
            (book, course, filename, "mp3", str(dest_mp3_path).replace("\\", "/")),
            (book, course, filename, "json", str(dest_json_path).replace("\\", "/"))
        ]

        cursor.executemany(
            "INSERT INTO voice_info (book, course, filename, format, location) VALUES (?, ?, ?, ?, ?)",
            records
        )

        conn.commit()
        conn.close()

        print(f"Successfully archived: {mp3_filename} to {target_dir}")

        return {"status": "success", "message": "Files moved and database updated."}

    except Exception as e:
        print(f"Error in handle_manage_submit: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/sources/books")
async def get_books():
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()
        query = "SELECT DISTINCT book FROM voice_info ORDER BY book ASC"
        cursor.execute(query)
        books = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"books": books}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/sources/courses")
async def get_courses(book: str):
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT course FROM voice_info WHERE book = ? ORDER BY course", (book,))
        courses = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"courses": courses}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/sources/files")
async def get_files_list(book: str, course: str):
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, location 
            FROM voice_info 
            WHERE book = ? AND course = ? AND format = 'mp3' 
            ORDER BY filename ASC
        """, (book, course))
        rows = cursor.fetchall()
        conn.close()
        files = [{"id": r[0], "name": r[1], "path": r[2]} for r in rows]
        return {"files": files}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/sources/load_content")
async def load_specific_content(book: str, course: str, filename: str):
    """获取 MP3 URL 及其对应的 JSON 字幕内容（简化版）"""
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()

        # 1. 获取 MP3 物理路径
        cursor.execute("SELECT location FROM voice_info WHERE book=? AND course=? AND filename=? AND format='mp3'",
                       (book, course, filename))
        mp3_row = cursor.fetchone()

        # 2. 获取 JSON 物理路径 (构造同名的 .json 文件名进行查询)
        cursor.execute("SELECT location FROM voice_info WHERE book=? AND course=? AND filename=? AND format='json'",
                       (book, course, filename))
        json_row = cursor.fetchone()
        conn.close()

        if not mp3_row:
            raise HTTPException(404, "MP3 record not found in database")

        # --- 处理 MP3 URL ---
        db_path = mp3_row[0].replace("\\", "/")
        # 仅仅去掉开头的 resources/ 字符串，不要进行 quote 编码
        url_sub_path = db_path[len("resources/"):] if db_path.startswith("resources/") else db_path

        # 返回原始的中文字符串路径，前端 fetch 时浏览器会自动处理编码
        mp3_url = f"http://localhost:8000/resources/{url_sub_path}"

        # --- 读取 JSON 字幕数据 ---
        json_data = []
        if json_row:
            # 路径标准化并转为绝对路径（Path 对象会自动处理 Windows/Linux 差异）
            json_phys_path = Path(json_row[0]).resolve()

            if json_phys_path.exists():
                with open(json_phys_path, 'r', encoding='utf-8') as f:
                    raw_data = python_json.load(f)
                    # 统一返回 segments 格式（兼容字典和数组格式）
                    json_data = raw_data.get("segments", raw_data) if isinstance(raw_data, dict) else raw_data
            else:
                print(f"Warning: JSON file not found at {json_phys_path}")

        return {
            "mp3_url": mp3_url,
            "segments": json_data
        }
    except Exception as e:
        print(f"Load content error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})


import json as python_json
from fastapi import Form
from fastapi.responses import JSONResponse, StreamingResponse


@app.post("/api/convert")
async def convert_text_to_voice(
        filename: str = Form(...),
        text: str = Form(...),
        role: str = Form(...)
):
    try:
        VOICE = "ja-JP-NanamiNeural"

        async def audio_stream_generator():
            communicate = edge_tts.Communicate(text, VOICE)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        return StreamingResponse(
            audio_stream_generator(),
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={filename}.mp3"}
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)