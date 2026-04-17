import discord
from discord.ext import commands
from fastapi import FastAPI, Request
import uvicorn
import asyncio
import os
from dotenv import load_dotenv

# .env 파일 로드 (TOKEN이나 URL 관리용)
load_dotenv()

# --- [설정 영역] ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") # 디스코드 봇 토큰
NOTIFICATION_CHANNEL_ID = 1491819968411467789 # 알림을 보낼 디스코드 채널 ID (숫자)

# --- [봇 및 웹 서버 초기화] ---
app = FastAPI()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [웹 서버: 아이폰 신호 받는 곳] ---
@app.post("/charge")
async def handle_charge(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        
        if not message:
            return {"ok": False, "error": "메시지 내용이 없습니다."}

        # 여기서 입금 문자 분석 로직 (간단 예시)
        # 예: "NH농협 입금 10,000원 홍길동" -> "홍길동"과 "10,000" 추출 가능
        
        # 디스코드 채널로 알림 전송
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            # 봇이 디스코드에 메시지를 보냅니다.
            await channel.send(f"📢 **입금 확인 알림**\n내용: {message}")
            return {"ok": True}
        else:
            return {"ok": False, "error": "디스코드 채널을 찾을 수 없습니다."}

    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root():
    return {"message": "서버가 정상 작동 중입니다!"}

# --- [봇 실행 및 메인 루프] ---
async def run_servers():
    # FastAPI 서버와 디스코드 봇을 동시에 실행하기 위한 설정
    config = uvicorn.Config(app, host="0.0.0.0", port=88)
    server = uvicorn.Server(config)
    
    # 봇과 서버를 병렬로 실행
    await asyncio.gather(
        server.serve(),
        bot.start(DISCORD_TOKEN)
    )

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("에러: DISCORD_TOKEN이 설정되지 않았습니다.")
    else:
        asyncio.run(run_servers())

@app.get("/")
async def root():
    return {"status": "ok", "message": "I am awake!"}
