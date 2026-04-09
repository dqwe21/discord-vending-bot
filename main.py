import os
import re
import threading
import discord
from discord.ext import commands
from fastapi import FastAPI, Request
import uvicorn

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
app = FastAPI()

pending_requests = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@app.get("/")
async def root():
    return {"message": "서버가 정상적으로 살아있습니다! 🚀"}
    
@app.post("/webhook")
async def receive_sms(request: Request):
    data = await request.json()
    sms_content = data.get("content", "")
    print(f"SMS Received: {sms_content}")

    # 금액/이름 추출 로직 (농협 문자 양식에 맞게 조정 필요)
    amount_match = re.search(r'입금\s?([\d,]+)원', sms_content)
    name_match = re.search(r'원\s?([가-힣\s]+)', sms_content)

    if amount_match and name_match:
        amount = int(amount_match.group(1).replace(',', ''))
        name = name_match.group(1).strip()
        if name in pending_requests and pending_requests[name][0] == amount:
            user_id = pending_requests[name][1]
            user = await bot.fetch_user(user_id)
            await user.send(f"💰 {name}님, {amount:,}원 입금이 확인되어 충전되었습니다!")
            del pending_requests[name]

    return {"status": "ok"}

def run_web_server():
    # Render는 PORT 환경 변수를 사용합니다.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.run("당신의_디스코드_봇_토큰")
