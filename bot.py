import discord
from discord import app_commands
from discord.ext import commands
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ALLOWED_CHANNEL_NAME = "출석-기록"

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

def channel_only():
    """특정 채널에서만 명령어 사용 가능하도록 제한"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.channel.name != ALLOWED_CHANNEL_NAME:
            await interaction.response.send_message(
                f"❌ 이 명령어는 **{ALLOWED_CHANNEL_NAME}** 채널에서만 사용할 수 있습니다!",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# 출근 기록 저장용 딕셔너리
work_records = {}  # {user_id: {'start_time': datetime, 'break_time': datetime, 'total_break': int}}

# 데이터 저장 파일
DATA_FILE = 'work_data.json'

def load_data():
    """저장된 데이터 불러오기"""
    global work_records
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            work_records = {}
            for user_id, record in data.items():
                work_records[user_id] = {
                    'start_time': datetime.fromisoformat(record['start_time']) if record.get('start_time') else None,
                    'break_time': datetime.fromisoformat(record['break_time']) if record.get('break_time') else None,
                    'total_break': record.get('total_break', 0)
                }
    except FileNotFoundError:
        work_records = {}

def save_data():
    """데이터 저장하기"""
    save_dict = {}
    for user_id, record in work_records.items():
        save_dict[user_id] = {
            'start_time': record['start_time'].isoformat() if record.get('start_time') else None,
            'break_time': record['break_time'].isoformat() if record.get('break_time') else None,
            'total_break': record.get('total_break', 0)
        }

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(save_dict, f, ensure_ascii=False, indent=2)

@bot.event
async def on_ready():
    """봇이 준비되었을 때"""
    print(f'{bot.user} 봇이 준비되었습니다!')
    load_data()
    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)}개의 명령어가 동기화되었습니다.')
    except Exception as e:
        print(f'명령어 동기화 실패: {e}')

@bot.tree.command(name="출근", description="출근을 기록합니다")
@channel_only()
async def work_start(interaction: discord.Interaction):
    """출근 명령어"""
    user_id = str(interaction.user.id)
    current_time = datetime.now()

    # 이미 출근한 경우
    if user_id in work_records and work_records[user_id].get('start_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 이미 출근 상태입니다!",
            ephemeral=True
        )
        return

    # 출근 기록
    work_records[user_id] = {
        'start_time': current_time,
        'break_time': None,
        'total_break': 0
    }
    save_data()

    time_str = current_time.strftime('%Y년 %m월 %d일 %H:%M:%S')

    embed = discord.Embed(
        title="🟢 출근",
        description=f"{interaction.user.mention}님이 출근했습니다.",
        color=discord.Color.green()
    )
    embed.add_field(name="출근 시간", value=time_str, inline=False)
    embed.set_footer(text="출근 기록됨")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="퇴근", description="퇴근을 기록하고 근무 시간을 계산합니다")
@channel_only()
async def work_end(interaction: discord.Interaction):
    """퇴근 명령어"""
    user_id = str(interaction.user.id)
    current_time = datetime.now()

    # 출근 기록이 없는 경우
    if user_id not in work_records or not work_records[user_id].get('start_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 출근 기록이 없습니다!",
            ephemeral=True
        )
        return

    record = work_records[user_id]

    # 휴식 중인 경우 자동으로 복귀 처리
    if record.get('break_time'):
        break_duration = int((current_time - record['break_time']).total_seconds())
        record['total_break'] += break_duration

    # 근무 시간 계산 (총 시간 - 휴식 시간)
    start_time = record['start_time']
    total_duration = current_time - start_time
    total_seconds = int(total_duration.total_seconds())
    work_seconds = total_seconds - record['total_break']

    # 시간, 분 계산
    hours = work_seconds // 3600
    minutes = (work_seconds % 3600) // 60

    # 휴식 시간 계산
    break_hours = record['total_break'] // 3600
    break_minutes = (record['total_break'] % 3600) // 60

    # 출근 기록 삭제
    del work_records[user_id]
    save_data()

    time_str = current_time.strftime('%Y년 %m월 %d일 %H:%M:%S')

    embed = discord.Embed(
        title="🔴 퇴근",
        description=f"{interaction.user.mention}님이 퇴근했습니다.",
        color=discord.Color.red()
    )
    embed.add_field(name="퇴근 시간", value=time_str, inline=False)
    embed.add_field(name="순수 근무 시간", value=f"{hours}시간 {minutes}분", inline=True)
    if record['total_break'] > 0:
        embed.add_field(name="휴식 시간", value=f"{break_hours}시간 {break_minutes}분", inline=True)
    embed.set_footer(text="퇴근 기록됨")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="휴식", description="휴식을 시작합니다")
@channel_only()
@app_commands.describe(사유="휴식 사유를 입력하세요")
async def work_break(interaction: discord.Interaction, 사유: str):
    """휴식 명령어"""
    user_id = str(interaction.user.id)
    current_time = datetime.now()

    # 출근하지 않은 경우
    if user_id not in work_records or not work_records[user_id].get('start_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 출근 상태가 아닙니다!",
            ephemeral=True
        )
        return

    # 이미 휴식 중인 경우
    if work_records[user_id].get('break_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 이미 휴식 중입니다!",
            ephemeral=True
        )
        return

    # 휴식 시작
    work_records[user_id]['break_time'] = current_time
    save_data()

    time_str = current_time.strftime('%Y년 %m월 %d일 %H:%M:%S')

    embed = discord.Embed(
        title="🟡 휴식 시작",
        description=f"{interaction.user.mention}님이 **{사유}** 사유로 휴식합니다.",
        color=discord.Color.gold()
    )
    embed.add_field(name="시간", value=time_str, inline=False)
    embed.set_footer(text="휴식 기록됨")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="복귀", description="휴식을 종료하고 업무에 복귀합니다")
@channel_only()
async def work_return(interaction: discord.Interaction):
    """복귀 명령어"""
    user_id = str(interaction.user.id)
    current_time = datetime.now()

    # 출근하지 않은 경우
    if user_id not in work_records or not work_records[user_id].get('start_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 출근 상태가 아닙니다!",
            ephemeral=True
        )
        return

    # 휴식 중이 아닌 경우
    if not work_records[user_id].get('break_time'):
        await interaction.response.send_message(
            f"❌ {interaction.user.mention}님은 휴식 중이 아닙니다!",
            ephemeral=True
        )
        return

    # 휴식 시간 계산
    break_start = work_records[user_id]['break_time']
    break_duration = int((current_time - break_start).total_seconds())
    work_records[user_id]['total_break'] += break_duration
    work_records[user_id]['break_time'] = None
    save_data()

    # 휴식 시간 표시
    break_minutes = break_duration // 60
    break_seconds = break_duration % 60

    time_str = current_time.strftime('%Y년 %m월 %d일 %H:%M:%S')

    embed = discord.Embed(
        title="🟢 업무 복귀",
        description=f"{interaction.user.mention}님이 업무에 복귀했습니다.",
        color=discord.Color.green()
    )
    embed.add_field(name="복귀 시간", value=time_str, inline=False)
    embed.add_field(name="휴식 시간", value=f"{break_minutes}분 {break_seconds}초", inline=False)
    embed.set_footer(text="복귀 기록됨")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="현황", description="현재 출근한 인원을 확인합니다")
@channel_only()
async def work_status_all(interaction: discord.Interaction):
    """전체 현황 명령어"""
    if not work_records:
        await interaction.response.send_message("📊 현재 출근한 인원이 없습니다.", ephemeral=True)
        return

    current_time = datetime.now()

    # 출근 인원과 휴식 인원 분류
    working = []
    on_break = []

    for user_id, record in work_records.items():
        if not record.get('start_time'):
            continue

        try:
            user = await bot.fetch_user(int(user_id))
            user_name = user.display_name
        except:
            user_name = f"Unknown User ({user_id})"

        start_time = record['start_time']
        elapsed = current_time - start_time
        elapsed_seconds = int(elapsed.total_seconds()) - record['total_break']
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60

        start_time_str = start_time.strftime('%H:%M')

        if record.get('break_time'):
            break_start = record['break_time']
            break_elapsed = int((current_time - break_start).total_seconds())
            break_minutes = break_elapsed // 60
            on_break.append(f"**{user_name}** - 출근: {start_time_str} (휴식 {break_minutes}분째)")
        else:
            working.append(f"**{user_name}** - 출근: {start_time_str} (근무 {hours}시간 {minutes}분)")

    embed = discord.Embed(
        title="📊 출근 현황",
        color=discord.Color.blue()
    )

    if working:
        embed.add_field(
            name=f"🟢 근무 중 ({len(working)}명)",
            value="\n".join(working),
            inline=False
        )

    if on_break:
        embed.add_field(
            name=f"🟡 휴식 중 ({len(on_break)}명)",
            value="\n".join(on_break),
            inline=False
        )

    embed.set_footer(text=f"총 {len(working) + len(on_break)}명 출근")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="상태", description="내 현재 출근 상태를 확인합니다")
@channel_only()
async def work_status(interaction: discord.Interaction):
    """개인 상태 확인 명령어"""
    user_id = str(interaction.user.id)

    if user_id not in work_records or not work_records[user_id].get('start_time'):
        await interaction.response.send_message(
            f"📊 {interaction.user.mention}님은 현재 **퇴근** 상태입니다.",
            ephemeral=True
        )
        return

    record = work_records[user_id]
    start_time = record['start_time']
    current_time = datetime.now()

    # 순수 근무 시간 계산
    total_duration = current_time - start_time
    work_seconds = int(total_duration.total_seconds()) - record['total_break']

    # 휴식 중이면 현재 휴식 시간도 빼기
    if record.get('break_time'):
        current_break = int((current_time - record['break_time']).total_seconds())
        work_seconds -= current_break

    hours = work_seconds // 3600
    minutes = (work_seconds % 3600) // 60

    start_time_str = start_time.strftime('%H:%M:%S')

    embed = discord.Embed(
        title="📊 내 상태",
        color=discord.Color.blue()
    )

    if record.get('break_time'):
        embed.description = f"{interaction.user.mention}님은 현재 **휴식 중**입니다."
        break_start = record['break_time']
        break_elapsed = int((current_time - break_start).total_seconds())
        break_minutes = break_elapsed // 60
        embed.add_field(name="현재 휴식 시간", value=f"{break_minutes}분", inline=False)
    else:
        embed.description = f"{interaction.user.mention}님은 현재 **근무 중**입니다."

    embed.add_field(name="출근 시간", value=start_time_str, inline=True)
    embed.add_field(name="순수 근무 시간", value=f"{hours}시간 {minutes}분", inline=True)

    if record['total_break'] > 0:
        total_break_minutes = record['total_break'] // 60
        embed.add_field(name="누적 휴식 시간", value=f"{total_break_minutes}분", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="명령어", description="봇 사용법을 확인합니다")
@channel_only()
async def help_command(interaction: discord.Interaction):
    """도움말 명령어"""
    embed = discord.Embed(
        title="📖 출퇴근 봇 사용 가이드",
        description="출퇴근 기록 봇의 모든 명령어입니다.",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🟢 /출근",
        value="출근을 기록합니다.",
        inline=False
    )

    embed.add_field(
        name="🔴 /퇴근",
        value="퇴근을 기록하고 순수 근무 시간을 계산합니다.\n(휴식 시간은 자동으로 제외됩니다)",
        inline=False
    )

    embed.add_field(
        name="🟡 /휴식 [사유]",
        value="휴식을 시작합니다. 사유를 입력해주세요.\n예: `/휴식 점심식사`",
        inline=False
    )

    embed.add_field(
        name="🟢 /복귀",
        value="휴식을 종료하고 업무에 복귀합니다.",
        inline=False
    )

    embed.add_field(
        name="📊 /상태",
        value="내 현재 출근 상태를 확인합니다.",
        inline=False
    )

    embed.add_field(
        name="📊 /현황",
        value="현재 출근한 모든 인원의 현황을 확인합니다.",
        inline=False
    )

    embed.add_field(
        name="📖 /명령어",
        value="이 도움말을 표시합니다.",
        inline=False
    )

    embed.set_footer(text="💡 휴식 시간은 근무 시간에서 자동으로 제외됩니다!")

    await interaction.response.send_message(embed=embed)

# 봇 실행
if __name__ == "__main__":
    bot.run(TOKEN)