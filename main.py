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

load_dotenv()

# --- [설정 영역] ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- [초기화] ---
app = FastAPI()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 입금 대기 명단
pending_requests = {}

# --- [충전 양식 모달] ---
class ChargeModal(discord.ui.Modal, title="로벅스 충전 신청"):
    name = discord.ui.TextInput(label="이름", placeholder="입금자 성함을 입력하세요.", min_length=2, max_length=10)
    amount = discord.ui.TextInput(label="금액", placeholder="숫자만 입력하세요. (예: 10000)", min_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = self.name.value.strip() # 공백 제거
        
        try:
            # 금액에서 콤마나 '원' 글자 제거 후 숫자로 변환
            target_amount = int(self.amount.value.replace(",", "").replace("원", "").strip())
        except ValueError:
            await interaction.response.send_message("금액은 숫자만 입력해주세요!", ephemeral=True)
            return

        current_time = time.time()
        
        # 중복 신청 처리: 동일 유저가 다시 신청하면 기존 기록 갱신
        for n, data in list(pending_requests.items()):
            if data['user_id'] == user_id:
                if n in pending_requests: del pending_requests[n]

        # 대기 등록 (5분)
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

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="영업", description="자판기 메뉴를 띄웁니다.")
async def open_shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 서지수 로벅스 샵", description="아래 버튼을 눌러 충전 신청을 해주세요.", color=0x5865F2)
    await interaction.response.send_message(embed=embed, view=VendingView())

# --- [웹 서버: 입금 확인 핵심 로직] ---
@app.post("/charge")
async def handle_charge(request: Request):
    try:
        data = await request.json()
        raw_message = data.get("message", "")
        
        if not raw_message:
            return {"ok": False, "error": "메시지 없음"}

        # 불필요한 알림 채널 메시지 전송은 요청하신 대로 삭제했습니다.

        # 문자 분석 (정규표현식 보강)
        # 1. 금액 추출: '입금' 뒤에 붙은 숫자들 추출 (콤마 제거 후 분석)
        clean_msg = raw_message.replace(",", "")
        amount_match = re.search(r'입금(\d+)', clean_msg)
        
        # 2. 이름 추출: 날짜/시간(예: 04/20 04:26) 뒤에 오는 한글 이름 추출
        # 문자 패턴: ... 04/20 04:26 352-*** 김재형 잔액... 
        # 이름은 보통 계좌번호 뒷부분 혹은 잔액 앞에 위치함
        name_match = re.search(r'([가-힣]{2,4})\s+잔액', clean_msg)

        if amount_match and name_match:
            amount = int(amount_match.group(1))
            name = name_match.group(1).strip()
            current_time = time.time()

            if name in pending_requests:
                req = pending_requests[name]
                
                # 시간 만료 여부 및 금액 일치 확인
                if current_time <= req['expire_at'] and req['amount'] == amount:
                    user_id = req['user_id']
                    user = await bot.fetch_user(user_id)
                    
                    if user:
                        await user.send(f"✅ **자동 충전 완료!**\n{name}님, {amount:,}원이 성공적으로 충전되었습니다.")
                    
                    del pending_requests[name]
                    return {"ok": True, "status": "success"}
        
        print(f"매칭 실패: 분석된 이름({name_match.group(1) if name_match else '없음'}), 금액({amount_match.group(1) if amount_match else '없음'})")
        return {"ok": True, "status": "no_match"}

    except Exception as e:
        print(f"서버 에러: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root():
    return {"status": "ok", "message": "I am awake!"}

async def run_servers():
    config = uvicorn.Config(app, host="0.0.0.0", port=88)
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), bot.start(DISCORD_TOKEN))

if __name__ == "__main__":
    if DISCORD_TOKEN:
        asyncio.run(run_servers())
