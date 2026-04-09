import os
import re
import threading
import discord
from discord.ext import commands
from fastapi import FastAPI, Request
import uvicorn

# --- [1. 설정 영역] ---
# 자신의 디스코드 봇 토큰을 여기에 넣으세요
TOKEN = "당신의_디스코드_봇_토큰"

intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용을 읽기 위해 필수!
bot = commands.Bot(command_prefix="!", intents=intents)
app = FastAPI()

# 임시 데이터베이스 (실제 운영 시에는 파일이나 DB에 저장해야 합니다)
user_money = {}        # {유저ID: 잔액}
pending_requests = {}  # {입금자명: [금액, 유저ID]}

# --- [2. 디스코드 봇 명령어] ---

@bot.event
async def on_ready():
    print(f'🤖 봇 로그인 성공: {bot.user}')

@bot.command()
async def 충전신청(ctx, 입금자명: str, 금액: int):
    """유저가 입금 전 미리 신청하는 명령어"""
    pending_requests[입금자명] = [금액, ctx.author.id]
    await ctx.send(f"✅ **{입금자명}** 이름으로 **{금액:,}원**을 입금해주세요!\n(입금이 확인되면 자동으로 충전됩니다.)")

@bot.command()
async def 잔액(ctx):
    """자신의 잔액을 확인하는 명령어"""
    money = user_money.get(ctx.author.id, 0)
    await ctx.send(f"💰 {ctx.author.mention}님의 현재 잔액은 **{money:,}원**입니다.")

# --- [3. 웹훅 & 입금 확인 로직] ---

@app.get("/")
async def root():
    return {"message": "자판기 서버 정상 작동 중! 🚀"}

@app.post("/webhook")
async def receive_sms(request: Request):
    data = await request.json()
    sms_content = data.get("content", "")
    print(f"📩 문자 수신: {sms_content}")

    # 농협 문자 분석 (정규표현식)
    # 예: [NH농협] 04/10 12:05 입금10,000원 홍길동
    amount_match = re.search(r'입금\s?([\d,]+)원', sms_content)
    name_match = re.search(r'원\s?([가-힣\s]+)', sms_content)

    if amount_match and name_match:
        amount = int(amount_match.group(1).replace(',', ''))
        name = name_match.group(1).strip()

        # 대기 목록에 있는지 확인
        if name in pending_requests:
            req_amount, user_id = pending_requests[name]
            
            if amount == req_amount:
                # 잔액 업데이트
                user_money[user_id] = user_money.get(user_id, 0) + amount
                
                # 디스코드 유저에게 알림 전송
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f"✨ 입금이 확인되었습니다! **{amount:,}원**이 충전되어 현재 잔액은 **{user_money[user_id]:,}원**입니다.")
                
                del pending_requests[name] # 처리 완료 후 삭제
                print(f"💰 충전 완료: {name} - {amount}원")
            else:
                print(f"⚠️ 금액 불일치: {name}님 (신청:{req_amount} / 입금:{amount})")
    
    return {"status": "ok"}

# --- [4. 실행] ---
def run_web():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.run(TOKEN)
