import asyncio
import edge_tts

# ja-JP-NanamiNeural 是最推荐的日语音色（成熟女声）
# ja-JP-KeitaNeural  是男声
TEXT = """
上海には春、夏、秋、冬の四季があります。上海にはまた、梅雨があります。毎年 6 月から始まって大体一か月ぐらいです。梅雨の間はよく雨が降ります。蒸し暑くて大変です。その後、夏になります。夏の終わりにはよく台風が来ます。上海辺りがよくその被害を受けます。上海の冬は寒いですが、あまり雪が降りません。
昨日は久しぶりのよい天気でした。家族と蘇州（そしゅう）へ遊びに行きました。朝 8 時ごろに出かけて 9 時半に着きました。一時間ぐらい掛かりました。蘇州で色々な名園を廻って、写真もたくさん撮りました。本当に楽しかったです。
"""
VOICE = "ja-JP-NanamiNeural"
OUTPUT_FILE = "japanese_test.mp3"

async def main():
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(OUTPUT_FILE)
    print(f"成功保存音频到: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())