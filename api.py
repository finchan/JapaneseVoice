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
from config import BASE_URL, ENV
import shutil
import traceback
import sys

app = FastAPI(title="Japanese Transcription API", version="1.0.0")
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

        print("文件上传成功准备调用transcriber.transcribe方法")

        # 5. 写入文件到对应角色的存储目录
        with open(audio_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 6. 调用转写逻辑，并将结果存入对应角色的数据目录
        print("开始调用transcriber.transcribe方法")
        raw_data = transcriber.transcribe(str(audio_path), str(json_path))

        print("完成transcriber.transcribe方法")
        serializable_data = python_json.loads(python_json.dumps(raw_data, ensure_ascii=False))
        return JSONResponse(content={"data": serializable_data})

    except Exception as e:
        # ========== 核心修改：全方位打印异常信息 ==========
        print("\n" + "="*50 + " 异常详情 " + "="*50)
        # 1. 基础异常信息（原 str(e)）
        print(f"【异常描述】: {str(e)}")
        # 2. 异常类型（比如 FileNotFoundError/ImportError 等）
        print(f"【异常类型】: {type(e).__name__}")
        # 3. 异常完整栈（定位到具体哪一行代码报错）
        print(f"【完整异常栈】: ")
        traceback.print_exc(file=sys.stdout)  # 输出到终端（而非仅日志）
        # 4. 异常附加信息（部分异常有 args/errno 等）
        print(f"【异常参数】: {e.args}")
        if hasattr(e, "errno"):
            print(f"【错误码】: {e.errno}")
        if hasattr(e, "filename"):
            print(f"【关联文件】: {e.filename}")
        print("="*108 + "\n")
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
        mp3_url = f"{BASE_URL}/resources/{url_sub_path}"

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


# ═══════════════════════════════════════════════════════════════════════════
# VERB CONJUGATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = Path("db/jvdb.sqlite")


def get_db():
    db_path = Path("db/jvdb.sqlite")
    db_path.parent.mkdir(exist_ok=True)
    return sqlite3.connect(str(db_path))


# ── DDL: create japanese_verbs table if not exists ──────────────────────────
def init_verb_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS japanese_verbs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            verb       TEXT NOT NULL,
            reading    TEXT NOT NULL,
            type       TEXT NOT NULL CHECK(type IN ('ichidan','godan','kuru','suru')),
            meaning    TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jv_verb    ON japanese_verbs(verb)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jv_type    ON japanese_verbs(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jv_reading ON japanese_verbs(reading)")
    conn.commit()
    conn.close()


init_verb_table()

# ── Conjugation rule engine ──────────────────────────────────────────────────
# Five-step (godan) ending → row mappings
GODAN = {
    'く': dict(i='き', a='か', e='け', o='こ', te='いて', ta='いた'),
    'ぐ': dict(i='ぎ', a='が', e='げ', o='ご', te='いで', ta='いだ'),
    'す': dict(i='し', a='さ', e='せ', o='そ', te='して', ta='した'),
    'つ': dict(i='ち', a='た', e='て', o='と', te='って', ta='った'),
    'ぬ': dict(i='に', a='な', e='ね', o='の', te='んで', ta='んだ'),
    'ぶ': dict(i='び', a='ば', e='べ', o='ぼ', te='んで', ta='んだ'),
    'む': dict(i='み', a='ま', e='め', o='も', te='んで', ta='んだ'),
    'る': dict(i='り', a='ら', e='れ', o='ろ', te='って', ta='った'),
    'う': dict(i='い', a='わ', e='え', o='お', te='って', ta='った'),
}


def conjugate(verb: str, verb_type: str) -> dict:
    """
    Returns a dict with all basic forms + auxiliary compound forms.
    For suru verbs the stored verb may omit trailing する (e.g. 発展).
    """
    r = {}

    if verb_type == 'ichidan':
        # Remove trailing る to get stem
        stem = verb[:-1] if verb.endswith('る') else verb
        r['原形'] = verb
        r['ます形'] = stem + 'ます'
        r['ない形'] = stem + 'ない'
        r['て形'] = stem + 'て'
        r['た形'] = stem + 'た'
        r['ば形'] = stem + 'れば'
        r['意向形'] = stem + 'よう'
        r['命令形'] = stem + 'ろ'
        r['禁止形'] = stem + 'な'
        r['可能形'] = stem + 'られる'
        r['受身形'] = stem + 'られる'
        r['使役形'] = stem + 'させる'
        te_stem = stem + 'て'

    elif verb_type == 'godan':
        ending = verb[-1]
        rows = GODAN.get(ending, {})
        stem = verb[:-1]

        # Special case: 行く (iku) - irregular て-form and た-form
        is_iku = (verb in ('行く', 'いく'))

        # Special case: 問う (とう), 乞う (こう), 請う (こう), 厭う (とう) - 促音便 / ウ音便 (both forms)
        is_tou_kou = verb in ('問う', 'とう', '乞う', 'こう', '請う', '厭う', 'いとう')

        # Special case: ある (aru) - special verb for existence
        is_aru = (verb in ('ある', 'ある'))

        # Special keigo godan verbs (ザ変敬語)
        # masu形: ru-verb change (る→い) + ます
        # 命令形: special ru-verb change (る→い)
        # Other conjugations follow regular GODAN rules (る→って/った)
        keigo_verbs = {
            'いらっしゃる': {'stem': 'いらっしゃ', 'masu': 'いらっしゃいます', 'imperative': 'いらっしゃい'},
            'おっしゃる': {'stem': 'おっしゃ', 'masu': 'おっしゃいます', 'imperative': 'おっしゃい'},
            'なさる': {'stem': 'なさ', 'masu': 'なさいます', 'imperative': 'なさい'},
            '下さる': {'stem': 'くださ', 'masu': 'くださいます', 'imperative': 'ください'},
            'くださる': {'stem': 'くださ', 'masu': 'くださいます', 'imperative': 'ください'},
            'ござる': {'stem': 'ござ', 'masu': 'ございます', 'imperative': 'ござい'},
        }

        is_keigo = verb in keigo_verbs

        if is_iku:
            te_form = 'いって'
            ta_form = 'いった'
        elif is_tou_kou:
            if verb in ('問う', 'とう'):
                te_form = 'とって/とうて'
                ta_form = '問った/問うた'
            elif verb in ('厭う', 'いとう'):
                te_form = 'いとって/いとうて'
                ta_form = 'いとった/いとうた'
            else:  # 乞う, こう, 請う
                te_form = 'こって/こうて'
                ta_form = 'こった/こうた'
        elif is_keigo:
            te_form = stem + 'って'
            ta_form = stem + 'った'
        elif is_aru:
            te_form = 'あって'
            ta_form = 'あった'
        else:
            te_form = stem + rows.get('te', '')
            ta_form = stem + rows.get('ta', '')

        if is_keigo:
            keigo_info = keigo_verbs[verb]
            r['原形'] = verb
            r['ます形'] = keigo_info['masu']
            r['ない形'] = stem + rows.get('a', '') + 'ない'
            r['て形'] = stem + 'って'
            r['た形'] = stem + 'った'
            r['ば形'] = stem + rows.get('e', '') + 'ば'
            r['意向形'] = stem + rows.get('o', '') + 'う'
            r['命令形'] = keigo_info['imperative']
            r['禁止形'] = verb + 'な'
            r['可能形'] = stem + rows.get('e', '') + 'る'
            r['受身形'] = stem + rows.get('a', '') + 'れる'
            r['使役形'] = stem + rows.get('a', '') + 'せる'
            te_stem = stem + 'って'
        elif is_aru:
            r['原形'] = verb
            r['ます形'] = 'あります'
            r['ない形'] = 'ない'
            r['て形'] = 'あって'
            r['た形'] = 'あった'
            r['ば形'] = 'あれば'
            r['意向形'] = 'あろう'
            r['命令形'] = 'あれ'
            r['禁止形'] = verb + 'な'
            r['可能形'] = 'えられる'
            r['受身形'] = 'あられる'
            r['使役形'] = 'あさせる'
            te_stem = 'あって'
        else:
            r['原形'] = verb
            r['ます形'] = stem + rows.get('i', '') + 'ます'
            r['ない形'] = stem + rows.get('a', '') + 'ない'
            r['て形'] = te_form
            r['た形'] = ta_form
            r['ば形'] = stem + rows.get('e', '') + 'ば'
            r['意向形'] = stem + rows.get('o', '') + 'う'
            r['命令形'] = stem + rows.get('e', '')
            r['禁止形'] = verb + 'な'
            r['可能形'] = stem + rows.get('e', '') + 'る'
            r['受身形'] = stem + rows.get('a', '') + 'れる'
            r['使役形'] = stem + rows.get('a', '') + 'せる'
            te_stem = te_form

    elif verb_type == 'kuru':
        r['原形'] = 'くる'
        r['ます形'] = 'きます'
        r['ない形'] = 'こない'
        r['て形'] = 'きて'
        r['た形'] = 'きた'
        r['ば形'] = 'くれば'
        r['意向形'] = 'こよう'
        r['命令形'] = 'こい'
        r['禁止形'] = 'くるな'
        r['可能形'] = 'こられる'
        r['受身形'] = 'こられる'
        r['使役形'] = 'こさせる'
        te_stem = 'きて'

    elif verb_type == 'suru':
        # verb may be bare noun (発展) or full する
        base = verb if verb == 'する' else verb + 'する'
        noun = '' if verb == 'する' else verb
        r['原形'] = base
        r['ます形'] = noun + 'します'
        r['ない形'] = noun + 'しない'
        r['て形'] = noun + 'して'
        r['た形'] = noun + 'した'
        r['ば形'] = noun + 'すれば'
        r['意向形'] = noun + 'しよう'
        r['命令形'] = noun + 'しろ / ' + noun + 'せよ'
        r['禁止形'] = base + 'な'
        r['可能形'] = noun + 'できる'
        r['受身形'] = noun + 'される'
        r['使役形'] = noun + 'させる'
        te_stem = noun + 'して'

    else:
        return r

    te = r.get('て形', te_stem)

    # ── Auxiliary compound forms keyed as aux_{catKey}__{form} ──────────────
    aux = {
        # テンス・アスペクト
        'tense_aspect__ている': te + 'いる',
        'tense_aspect__ていた': te + 'いた',
        'tense_aspect__てある': te + 'ある',
        'tense_aspect__てあった': te + 'あった',
        'tense_aspect__てしまう': te + 'しまう',
        'tense_aspect__てしまった': te + 'しまった',
        # 授受
        'juju__てあげる': te + 'あげる',
        'juju__てもらう': te + 'もらう',
        'juju__てくれる': te + 'くれる',
        'juju__てあげた': te + 'あげた',
        'juju__てもらった': te + 'もらった',
        'juju__てくれた': te + 'くれた',
        # 願望
        'desire__たい': r.get('ます形', '').replace('ます', '') + 'たい',
        'desire__たくない': r.get('ます形', '').replace('ます', '') + 'たくない',
        'desire__たかった': r.get('ます形', '').replace('ます', '') + 'たかった',
        'desire__たがる': r.get('ます形', '').replace('ます', '') + 'たがる',
        'desire__たがっている': r.get('ます形', '').replace('ます', '') + 'たがっている',
        # 推量
        'conjecture__でしょう': r.get('原形', '') + 'でしょう',
        'conjecture__だろう': r.get('原形', '') + 'だろう',
        'conjecture__はずだ': r.get('原形', '') + 'はずだ',
        'conjecture__はずがない': r.get('原形', '') + 'はずがない',
        'conjecture__にちがいない': r.get('原形', '') + 'にちがいない',
        # 可能性
        'possibility__かもしれない': r.get('原形', '') + 'かもしれない',
        'possibility__かもしれなかった': r.get('た形', '') + 'かもしれなかった',
        # 義務
        'obligation__べきだ': r.get('原形', '') + 'べきだ',
        'obligation__べきではない': r.get('原形', '') + 'べきではない',
        'obligation__なければならない': r.get('ない形', '').replace('ない', '') + 'なければならない',
        'obligation__なくてはいけない': r.get('ない形', '').replace('ない', '') + 'なくてはいけない',
        # 許可
        'permission__てもいい': te + 'もいい',
        'permission__てはいけない': te + 'はいけない',
        'permission__てもかまわない': te + 'もかまわない',
        # 試み
        'attempt__てみる': te + 'みる',
        'attempt__てみた': te + 'みた',
        'attempt__ておく': te + 'おく',
        'attempt__ておいた': te + 'おいた',
        # 変化
        'change__てくる': te + 'くる',
        'change__ていく': te + 'いく',
        'change__てきた': te + 'きた',
        # 否定丁寧
        'negative_polite__ません': r.get('ます形', '').replace('ます', '') + 'ません',
        'negative_polite__ませんでした': r.get('ます形', '').replace('ます', '') + 'ませんでした',
        'negative_polite__ないでください': r.get('ない形', '') + 'でください',
        'negative_polite__なくてもいい': r.get('ない形', '').replace('ない', 'な') + 'くてもいい',
        # 条件
        'conditional__たら': r.get('た形', '') + 'ら',
        'conditional__なら': r.get('原形', '') + 'なら',
        'conditional__と': r.get('原形', '') + 'と',
        # 使役受身複合
        'causative_passive__させられる': r.get('使役形', '').replace('る', '') + 'られる' if verb_type in (
        'ichidan', 'kuru') else r.get('使役形', '').replace('せる', 'させられる'),
        'causative_passive__てもらえる': te + 'もらえる',
        'causative_passive__させてもらう': r.get('使役形', '') + 'もらう',
        # 依頼
        'request__てください': te + 'ください',
        'request__てほしい': te + 'ほしい',
        'request__てもらいたい': te + 'もらいたい',
        # 様態伝聞
        'hearsay__そうだ（様態）': r.get('ます形', '').replace('ます', '') + 'そうだ',
        'hearsay__そうだ（伝聞）': r.get('原形', '') + 'そうだ',
        'hearsay__らしい': r.get('原形', '') + 'らしい',
        'hearsay__ようだ': r.get('原形', '') + 'ようだ',
    }

    for k, v in aux.items():
        r[f'aux_{k}'] = v

    return r


# ── API: search verb ─────────────────────────────────────────────────────────
from pydantic import BaseModel


class VerbSearchRequest(BaseModel):
    verb: str


class VerbConjugateRequest(BaseModel):
    verb: str
    type: str


class TtsRequest(BaseModel):
    text: str


@app.post("/api/verbs/search")
async def search_verb(req: VerbSearchRequest):
    """Search japanese_verbs table. Returns found=False if outside the vocabulary."""
    q = req.verb.strip()
    conn = get_db()
    cursor = conn.cursor()
    # Try exact match on verb or reading
    cursor.execute(
        "SELECT verb, reading, type, meaning FROM japanese_verbs WHERE verb=? OR reading=? LIMIT 1",
        (q, q)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"found": False}
    return {
        "found": True,
        "verb_info": {"verb": row[0], "reading": row[1], "type": row[2], "meaning": row[3]}
    }


@app.post("/api/verbs/conjugate")
async def conjugate_verb(req: VerbConjugateRequest):
    """Run rule-based conjugation engine and return all forms."""
    result = conjugate(req.verb.strip(), req.type.strip())
    return {"conjugations": result}


@app.post("/api/tts-stream")
async def tts_stream(req: TtsRequest):
    """Stream TTS audio for a single text string via edge-tts."""
    VOICE = "ja-JP-NanamiNeural"
    try:
        async def gen():
            communicate = edge_tts.Communicate(req.text, VOICE)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        return StreamingResponse(gen(), media_type="audio/mpeg")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# ADJECTIVE I (い形容词) CONJUGATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

SPECIAL_ADJ_I = {
    'いい': {
        '现在式肯定（终止形 / 礼貌形）': 'いい / いです',
        '现在式否定 1（否定形 1 / 礼貌否定 1）': 'よくない / よくないです',
        '现在式否定 2（否定形 2 / 礼貌否定 2）': 'よくは / よくありません',
        '过去式肯定（过去形 / 礼貌过去形）': 'よかった / よかったです',
        '过去式否定 1（过去否定 1 / 礼貌过去否定 1）': 'よくなかった / よくなかったです',
        '过去式否定 2（过去否定 2 / 礼貌过去否定 2）': 'よくはなかった / よくなくなりました',
        '副词化（连用形）': 'よく',
        '名词化 1（程度名词）': 'よさ',
        '名词化 2（属性名词）': 'よみ',
        '并列/中顿（て形）': 'よくて',
        '假定形（条件形）': 'よければ',
        '推量形（推测形 / 礼貌推测）': 'よかろう / いいでしょう',
        '样态（样态形 / 礼貌样态）': 'よさそうだ / よさそうです',
        '程度过分（简体复合 / 礼貌复合）': 'よすぎる / よすぎます',
    },
    '良い': {
        '现在式肯定（终止形 / 礼貌形）': 'いい / いです',
        '现在式否定 1（否定形 1 / 礼貌否定 1）': 'よくない / よくないです',
        '现在式否定 2（否定形 2 / 礼貌否定 2）': 'よくは / よくありません',
        '过去式肯定（过去形 / 礼貌过去形）': 'よかった / よかったです',
        '过去式否定 1（过去否定 1 / 礼貌过去否定 1）': 'よくなかった / よくなかったです',
        '过去式否定 2（过去否定 2 / 礼貌过去否定 2）': 'よくはなかった / よくなくなりました',
        '副词化（连用形）': 'よく',
        '名词化 1（程度名词）': 'よさ',
        '名词化 2（属性名词）': 'よみ',
        '并列/中顿（て形）': 'よくて',
        '假定形（条件形）': 'よければ',
        '推量形（推测形 / 礼貌推测）': 'よかろう / いいでしょう',
        '样态（样态形 / 礼貌样态）': 'よさそうだ / よさそうです',
        '程度过分（简体复合 / 礼貌复合）': 'よすぎる / よすぎます',
    }
}


def init_adj_i_table():
    """Create japanese_adj_i table if not exists."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS japanese_adj_i (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            adj_i      TEXT NOT NULL,
            reading    TEXT NOT NULL,
            meaning    TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_adj_i ON japanese_adj_i(adj_i)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_adj_i_reading ON japanese_adj_i(reading)")
    conn.commit()
    conn.close()


init_adj_i_table()


def conjugate_adj_i(adj_i: str) -> dict:
    """
    Generate all conjugation forms for i-adjectives based on Excel rules.
    Special cases are handled first.
    """
    # Check for special irregular adjectives
    if adj_i in SPECIAL_ADJ_I:
        return SPECIAL_ADJ_I[adj_i]

    r = {}
    stem = adj_i[:-1] if adj_i.endswith('い') else adj_i

    # 14 basic forms from Excel
    r['现在式肯定（终止形 / 礼貌形）'] = f"{adj_i} / {adj_i}です"
    r['现在式否定 1（否定形 1 / 礼貌否定 1）'] = f"{stem}くない / {stem}くないです"
    r['现在式否定 2（否定形 2 / 礼貌否定 2）'] = f"{stem}くはない / {stem}くありません"
    r['过去式肯定（过去形 / 礼貌过去形）'] = f"{stem}かった / {stem}かったです"
    r['过去式否定 1（过去否定 1 / 礼貌过去否定 1）'] = f"{stem}くなかった / {stem}くなかったです"
    r['过去式否定 2（过去否定 2 / 礼貌过去否定 2）'] = f"{stem}くはなかった / {stem}くありませんでした"
    r['副词化（连用形）'] = stem + 'く'
    r['名词化 1（程度名词）'] = stem + 'さ'
    r['名词化 2（属性名词）'] = stem + 'み'
    r['并列/中顿（て形）'] = stem + 'くて'
    r['假定形（条件形）'] = stem + 'ければ'
    r['推量形（推测形 / 礼貌推测）'] = f"{stem}かろう / {adj_i}でしょう"
    r['样态（样态形 / 礼貌样态）'] = f"{stem}そうだ / {stem}そうです"
    r['程度过分（简体复合 / 礼貌复合）'] = f"{stem}すぎる / {stem}すぎます"

    return r


class AdjISearchRequest(BaseModel):
    adj_i: str


class AdjIConjugateRequest(BaseModel):
    adj_i: str


@app.post("/api/adjectives-i/search")
async def search_adj_i(req: AdjISearchRequest):
    """Search japanese_adj_i table for an i-adjective."""
    q = req.adj_i.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT adj_i, reading, meaning FROM japanese_adj_i WHERE adj_i=? OR reading=? LIMIT 1",
        (q, q)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"found": False}
    return {
        "found": True,
        "adj_i_info": {"adj_i": row[0], "reading": row[1], "meaning": row[2]}
    }


@app.post("/api/adjectives-i/conjugate")
async def conjugate_adj_i_endpoint(req: AdjIConjugateRequest):
    """Generate all conjugation forms for an i-adjective."""
    result = conjugate_adj_i(req.adj_i.strip())
    return {"conjugations": result}


# ═══════════════════════════════════════════════════════════════════════════
# ADJECTIVE NA (な形容词) CONJUGATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

def init_adj_na_table():
    """Create japanese_adj_na table if not exists."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS japanese_adj_na (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            adj_na     TEXT NOT NULL,
            reading    TEXT NOT NULL,
            meaning    TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_adj_na ON japanese_adj_na(adj_na)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_adj_na_reading ON japanese_adj_na(reading)")
    conn.commit()
    conn.close()


init_adj_na_table()


def conjugate_adj_na(adj_na: str) -> dict:
    """
    Generate all conjugation forms for Na-adjectives based on Excel rules.
    """
    r = {}
    stem = adj_na

    # 14 basic forms from Excel
    r['现在式肯定（终止形 / 礼貌形）'] = f"{stem}だ / {stem}です"
    r['现在式否定 1（否定形 1 / 礼貌否定 1）'] = f"{stem}ではない / {stem}ではありません"
    r['现在式否定 2（否定形 2 / 礼貌否定 2）'] = f"{stem}じゃない / {stem}じゃないです"
    r['过去式肯定（过去形 / 礼貌过去形）'] = f"{stem}だった / {stem}でした"
    r['过去式否定 1（过去否定 1 / 礼貌过去否定 1）'] = f"{stem}ではなかった / {stem}ではありませんでした"
    r['过去式否定 2（过去否定 2 / 礼貌过去否定 2）'] = f"{stem}じゃなかった / {stem}じゃなかったです"
    r['副词化（连用形）'] = stem + 'に'
    r['名词化 1（程度名词）'] = stem + 'さ'
    r['名词化 2（属性名词）'] = stem + 'み'
    r['并列/中顿（で形）'] = stem + 'で'
    r['假定形（条件形）'] = f"{stem}なら（ば）"
    r['推量形（推测形 / 礼貌推测）'] = f"{stem}だろう / {stem}でしょう"
    r['样态（样态形 / 礼貌样态）'] = f"{stem}そうだ / {stem}そうです"
    r['程度过分（简体复合 / 礼貌复合）'] = f"{stem}すぎる / {stem}すぎます"

    return r


class AdjNaSearchRequest(BaseModel):
    adj_na: str


class AdjNaConjugateRequest(BaseModel):
    adj_na: str


@app.post("/api/adjectives-na/search")
async def search_adj_na(req: AdjNaSearchRequest):
    """Search japanese_adj_na table for a Na-adjective."""
    q = req.adj_na.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT adj_na, reading, meaning FROM japanese_adj_na WHERE adj_na=? OR reading=? LIMIT 1",
        (q, q)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"found": False}
    return {
        "found": True,
        "adj_na_info": {"adj_na": row[0], "reading": row[1], "meaning": row[2]}
    }


@app.post("/api/adjectives-na/conjugate")
async def conjugate_adj_na_endpoint(req: AdjNaConjugateRequest):
    """Generate all conjugation forms for a Na-adjective."""
    result = conjugate_adj_na(req.adj_na.strip())
    return {"conjugations": result}


from config import HOST, PORT
if ENV == 'TEST':
    if __name__ == "__main__":
        uvicorn.run("api:app", host=HOST, port=PORT, reload=True)
elif ENV == 'PROD_DM':
    if __name__ == "__main__":
        uvicorn.run(
        "api:app",
        host=HOST,
        port=PORT,
        reload=True,
        ssl_certfile="/opt/japanese-voice/cert/tasche.top_bundle.pem",
        ssl_keyfile="/opt/japanese-voice/cert/tasche.top.key"
    )
else: #PROD_IP
    if __name__ == "__main__":
        uvicorn.run("api:app", host=HOST, port=PORT, reload=True)