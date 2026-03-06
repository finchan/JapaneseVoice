import json as python_json
import uvicorn
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from transcribe import Transcriber
from pathlib import Path
import sqlite3
from urllib.parse import quote
import shutil
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Japanese Transcription API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态资源：这意味着访问 http://localhost:8000/resources/xxx 其实是访问 物理目录 resources/xxx
app.mount("/resources", StaticFiles(directory="resources"), name="resources")

transcriber = Transcriber(model_size="medium")

UPLOAD_DIR = Path("uploads")
DATA_DIR = Path("data_cache")

@app.get("/api/sources/books")
async def get_books():
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT book FROM voice_info 
            ORDER BY 
            CASE 
                WHEN book LIKE '%第一%' THEN 1
                WHEN book LIKE '%第二%' THEN 2
                WHEN book LIKE '%第三%' THEN 3
                WHEN book LIKE '%第四%' THEN 4
                WHEN book LIKE '%第五%' THEN 5
                WHEN book LIKE '%第六%' THEN 6
                WHEN book LIKE '%第七%' THEN 7
                WHEN book LIKE '%第八%' THEN 8
                WHEN book LIKE '%第九%' THEN 9
                WHEN book LIKE '%第十%' THEN 10
                ELSE 99 
            END, book ASC
        """
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
        # 对应你提供的 DDL: book, course, filename, format, location
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
    try:
        conn = sqlite3.connect("db/jvdb.sqlite")
        cursor = conn.cursor()
        
        # 1. 获取路径 (假设 location 为 "resources/日语综合教程第一册/第01課 天气/1.mp3")
        cursor.execute("SELECT location FROM voice_info WHERE book=? AND course=? AND filename=?", (book, course, filename))
        row = cursor.fetchone()
        if not row: raise HTTPException(404, "File not found")
        
        db_path = row[0].replace("\\", "/")
        
        # 2. 剥离 resources/ 前缀
        if db_path.startswith("resources/"):
            url_sub_path = db_path[len("resources/"):]
        else:
            url_sub_path = db_path

        # 3. 【关键修复】对中文路径进行编码，防止空格和特殊字符解析失败
        # quote 会把 "第01課 天气" 变成 "%E7%AC%AC01%E8%AA%B2%20%E5%A4%A9%E6%B0%97"
        encoded_path = quote(url_sub_path)
        
        mp3_url = f"http://localhost:8000/resources/{encoded_path}"
        
        # ... 后续 JSON 处理逻辑 ...
        return {"mp3_url": mp3_url, "segments": json_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ... 保持 handle_manage_submit 和其他原有逻辑不变 ...

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)