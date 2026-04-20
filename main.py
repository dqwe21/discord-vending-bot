import discord
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, Request
import uvicorn
import asyncio
import os
import time
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- [설정 영역] ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BANK_ACCOUNT = "3521856034173"

# --- [초기화] ---
app = FastAPI()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 입금 대기 명단
pending_requests = {}

# --- [계좌 복사 버튼 뷰] ---
class CopyAccountView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="농협계좌 복사하기", style=discord.ButtonStyle.secondary)
    async def copy_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(BANK_ACCOUNT, ephemeral=True)

# --- [영업 버튼 뷰] ---
class VendingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="충전", style=discord.ButtonStyle.green, custom_id="btn_charge")
    async def charge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChargeModal())

# --- [충전 양식 모달] ---
class ChargeModal(discord.ui.Modal, title="로벅스 충전 신청"):
    name = discord.ui.TextInput(label="이름", placeholder="입금자 성함을 입력하세요.", min_length=2, max_length=10)
    amount = discord.ui.TextInput(label="금액", placeholder="숫자만 입력하세요. (예: 10000)", min_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = self.name.value.strip()
        
        try:
            target_amount = int(self.amount.value.replace(",", "").replace("원", "").strip())
        except ValueError:
            await interaction.response.send_message("금액은 숫자만 입력해주세요!", ephemeral=True)
            return

        current_time = time.time()
        for n, data in list(pending_requests.items()):
            if data['user_id'] == user_id and data['expire_at'] > current_time:
                await interaction.response.send_message("이미 진행 중인 충전 신청이 있습니다.", ephemeral=True)
                return

        await interaction.response.send_message("📬 DM을 확인해주세요!", ephemeral=True)

        embed = discord.Embed(
            title="💳 입금 대기 중", 
            description="아래 **[농협계좌 복사하기]** 버튼을 누른 후,\n나타나는 번호를 터치하면 바로 복사됩니다!",
            color=0x5865F2, 
            timestamp=datetime.now()
        )
        embed.add_field(name="상태", value="`입금 확인 중...`", inline=False)
        embed.add_field(name="입금자명", value=f"`{user_name}`", inline=True)
        embed.add_field(name="신청금액", value=f"`{target_amount:,}원`", inline=True)
        embed.add_field(name="입금계좌", value=f"농협 `{BANK_ACCOUNT}`", inline=False)
        embed.set_footer(text="5분 이내 미입금 시 자동 취소")
        
        try:
            dm_msg = await interaction.user.send(embed=embed, view=CopyAccountView())
            pending_requests[user_name] = {
                "amount": target_amount,
                "user_id": user_id,
                "msg_obj": dm_msg,
                "expire_at": current_time + 300
            }
        except discord.Forbidden:
            pass

# --- [만료 체크 태스크] ---
async def check_expiration():
    while True:
        current_time = time.time()
        for name, data in list(pending_requests.items()):
            if current_time > data['expire_at']:
                try:
                    fail_embed = discord.Embed(title="❌ 충전 실패", color=0xFF0000, timestamp=datetime.now())
                    fail_embed.add_field(name="사유", value="`입금 시간 초과 (5분 경과)`")
                    await data['msg_obj'].edit(content=None, embed=fail_embed, view=None)
                except: pass
                del pending_requests[name]
        await asyncio.sleep(15) # 부하를 줄이기 위해 15초로 조정

# --- [슬래시 커맨드 및 이벤트] ---
@bot.event
async def on_ready():
    # 429 에러 방지: 봇이 켜질 때마다 무조건 동기화하지 않고 필요할 때만 실행 추천
    # 테스트 기간에는 유지하되, 완료 후에는 주석 처리하는 것이 좋습니다.
    try:
        await bot.tree.sync()
        print(f"✅ 슬래시 커맨드 동기화 완료: {bot.user}")
    except discord.errors.HTTPException as e:
        print(f"⚠️ 동기화 실패 (Rate Limit): {e}")
    
    if not hasattr(bot, 'expiration_task_started'):
        bot.loop.create_task(check_expiration())
        bot.expiration_task_started = True

@bot.tree.command(name="영업", description="자판기 메뉴를 띄웁니다.")
async def open_shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 서지수 로벅스 샵", description="아래 버튼을 눌러 충전 신청을 해주세요.", color=0x5865F2)
    await interaction.response.send_message(embed=embed, view=VendingView())

# --- [웹 서버 로직은 동일] ---
@app.post("/charge")
async def handle_charge(request: Request):
    try:
        data = await request.json()
        raw_message = data.get("message", "")
        if not raw_message: return {"ok": False}
        
        clean_msg = raw_message.replace(",", "")
        amount_match = re.search(r'입금(\d+)', clean_msg)
        name_match = re.search(r'([가-힣]{2,4})\s+잔액', clean_msg)

        if amount_match and name_match:
            amount = int(amount_match.group(1))
            name = name_match.group(1).strip()
            
            if name in pending_requests:
                req = pending_requests[name]
                if time.time() <= req['expire_at'] and req['amount'] == amount:
                    success_embed = discord.Embed(title="✅ 충전 완료", color=0x00FF00, timestamp=datetime.now())
                    success_embed.add_field(name="상태", value="`입금 확인 및 충전 성공` [✅]")
                    success_embed.add_field(name="충전금액", value=f"`{amount:,}원`")
                    await req['msg_obj'].edit(content=None, embed=success_embed, view=None)
                    del pending_requests[name]
                    return {"ok": True}
        return {"ok": True}
    except: return {"ok": False}

@app.get("/")
async def root(): return {"status": "ok"}

async def run_servers():
    config = uvicorn.Config(app, host="0.0.0.0", port=88)
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), bot.start(DISCORD_TOKEN))

if __name__ == "__main__":
    if DISCORD_TOKEN: asyncio.run(run_servers())
