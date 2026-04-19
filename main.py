import discord
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, Request
import uvicorn
import asyncio
import os
import time
import re
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# --- [설정 영역] ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NOTIFICATION_CHANNEL_ID = 1491819968411467789 # 알림 보낼 채널 ID

# --- [초기화] ---
app = FastAPI()
intents = discord.Intents.all() # 모달 및 모든 기능을 위해 all 사용
bot = commands.Bot(command_prefix="!", intents=intents)

# 입금 대기 명단 저장 (이름: {amount: 금액, user_id: ID, expire_at: 시간})
pending_requests = {}

# --- [충전 양식 모달] ---
class ChargeModal(discord.ui.Modal, title="로벅스 충전 신청"):
    name = discord.ui.TextInput(label="이름", placeholder="입금자 성함을 입력하세요.", min_length=2, max_length=10)
    amount = discord.ui.TextInput(label="금액", placeholder="숫자만 입력하세요. (예: 10000)", min_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = self.name.value
        
        # 금액 숫자 변환
        try:
            target_amount = int(self.amount.value.replace(",", ""))
        except ValueError:
            await interaction.response.send_message("금액은 숫자만 입력해주세요!", ephemeral=True)
            return

        current_time = time.time()
        
        # 중복 신청 및 시간 체크
        # 1. 이미 같은 유저가 신청했는지 확인 (5분 이내)
        for n, data in list(pending_requests.items()):
            if data['user_id'] == user_id and data['expire_at'] > current_time:
                await interaction.response.send_message("이미 진행 중인 충전 신청이 있습니다. 5분 뒤에 다시 시도하세요.", ephemeral=True)
                return
            elif data['expire_at'] <= current_time: # 만료된 건 정리
                if n in pending_requests: del pending_requests[n]

        # 대기 명단 등록 (5분 = 300초)
        pending_requests[user_name] = {
            "amount": target_amount,
            "user_id": user_id,
            "expire_at": current_time + 300
        }

        await interaction.response.send_message(
            f"✅ **충전 신청 완료**\n입금자명: `{user_name}`\n금액: `{target_amount:,}원`\n\n5분 이내에 농협 계좌로 입금해주세요!", 
            ephemeral=True
        )

# --- [영업 버튼 뷰] ---
class VendingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="충전", style=discord.ButtonStyle.green, custom_id="btn_charge")
    async def charge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChargeModal())

# --- [슬래시 커맨드 및 이벤트] ---
@bot.event
async def on_ready():
    # 슬래시 커맨드 동기화
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.tree.command(name="영업", description="자판기 메뉴를 띄웁니다.")
async def open_shop(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 서지수 로벅스 샵",
        description="아래 버튼을 눌러 충전 신청을 해주세요.",
        color=0x5865F2
    )
    embed.add_field(name="⚠️ 주의사항", value="신청 후 5분 이내에 입금해야 자동 확인됩니다.", inline=False)
    await interaction.response.send_message(embed=embed, view=VendingView())

# --- [웹 서버: 아이폰 신호 받는 곳] ---
@app.post("/charge")
async def handle_charge(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        
        if not message:
            return {"ok": False, "error": "메시지 내용이 없습니다."}

        # 1. 일단 디스코드 채널에 전체 기록 전송 (기존 기능)
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            await channel.send(f"📢 **입금 확인 알림**\n내용: {message}")

        # 2. 입금 문자 분석 및 자동 충전 확인 로직
        # 농협 문자 예시: [Web발신] 농협 입금10,000원 04/17 19:34 ... 홍길동 잔액...
        amount_match = re.search(r'입금\s*([\d,]+)원', message)
        name_match = re.search(r'원\s*([가-힣]{2,4})', message) # '원' 뒤의 한글 2~4자 추출

        if amount_match and name_match:
            amount = int(amount_match.group(1).replace(",", ""))
            name = name_match.group(1)
            current_time = time.time()

            # 대기 명단에 있는지 확인
            if name in pending_requests:
                req = pending_requests[name]
                
                # 시간 및 금액 대조
                if current_time <= req['expire_at'] and req['amount'] == amount:
                    user_id = req['user_id']
                    user = await bot.fetch_user(user_id)
                    
                    if user:
                        # 유저에게 알림 전송 (나만 보게 수정된 느낌으로 DM 발송)
                        await user.send(f"✅ **충전 성공!**\n{name}님, 신청하신 {amount:,}원이 정상 확인되었습니다.")
                    
                    # 처리 완료 후 삭제
                    del pending_requests[name]
                    return {"ok": True, "status": "matched"}
                
        return {"ok": True, "status": "no_match_or_expired"}

    except Exception as e:
        print(f"Error handling charge: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root():
    return {"status": "ok", "message": "I am awake!"}

# --- [실행] ---
async def run_servers():
    config = uvicorn.Config(app, host="0.0.0.0", port=88)
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        server.serve(),
        bot.start(DISCORD_TOKEN)
    )

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("에러: DISCORD_TOKEN이 설정되지 않았습니다.")
    else:
        asyncio.run(run_servers())
