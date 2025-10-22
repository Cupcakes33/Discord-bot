import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta, time as dt_time
from dotenv import load_dotenv
import sqlite3
from contextlib import contextmanager

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ALLOWED_CHANNEL_NAME = "출석-기록"
DB_FILE = "work_records.db"

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

# 데이터베이스 컨텍스트 매니저
@contextmanager
def get_db():
    """데이터베이스 연결 컨텍스트 매니저"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """데이터베이스 초기화"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 현재 출근 상태 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS current_work_status (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                start_time TEXT NOT NULL,
                break_time TEXT,
                total_break_seconds INTEGER DEFAULT 0
            )
        ''')

        # 출퇴근 히스토리 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                work_seconds INTEGER NOT NULL,
                break_seconds INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 휴식 기록 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS break_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                reason TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 인덱스 생성
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_work_history_user_date ON work_history(user_id, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_work_history_date ON work_history(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_break_history_user ON break_history(user_id, start_time)')

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

@bot.event
async def on_ready():
    """봇이 준비되었을 때"""
    print(f'{bot.user} 봇이 준비되었습니다!')
    init_db()

    # 스케줄러 시작
    if not daily_auto_checkout.is_running():
        daily_auto_checkout.start()
    if not weekly_report.is_running():
        weekly_report.start()

    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)}개의 명령어가 동기화되었습니다.')
    except Exception as e:
        print(f'명령어 동기화 실패: {e}')

# 매일 0시 자동 퇴근 처리
@tasks.loop(time=dt_time(hour=0, minute=0, second=0))
async def daily_auto_checkout():
    """매일 0시에 출근 중인 사람들 자동 퇴근 처리"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # 현재 출근 중인 사람들 조회
            cursor.execute('SELECT * FROM current_work_status')
            working_users = cursor.fetchall()

            if not working_users:
                return

            current_time = datetime.now()
            yesterday = (current_time - timedelta(days=1)).date()

            daily_summary = []

            for user in working_users:
                user_id = user['user_id']
                username = user['username']
                start_time = datetime.fromisoformat(user['start_time'])
                total_break = user['total_break_seconds']

                # 휴식 중이면 휴식 시간도 추가
                if user['break_time']:
                    break_start = datetime.fromisoformat(user['break_time'])
                    total_break += int((current_time - break_start).total_seconds())

                # 근무 시간 계산 (전날 23:59:59까지)
                end_of_day = datetime.combine(yesterday, dt_time(23, 59, 59))
                total_seconds = int((end_of_day - start_time).total_seconds())
                work_seconds = total_seconds - total_break

                # 히스토리에 저장
                cursor.execute('''
                    INSERT INTO work_history (user_id, username, date, start_time, end_time, work_seconds, break_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, username, yesterday.isoformat(), start_time.isoformat(),
                      end_of_day.isoformat(), work_seconds, total_break))

                # 현재 상태에서 삭제
                cursor.execute('DELETE FROM current_work_status WHERE user_id = ?', (user_id,))

                # 요약 정보 추가
                hours = work_seconds // 3600
                minutes = (work_seconds % 3600) // 60
                daily_summary.append(f"**{username}**: {hours}시간 {minutes}분")

            # 출석-기록 채널에 일일 리포트 전송
            channel = discord.utils.get(bot.get_all_channels(), name=ALLOWED_CHANNEL_NAME)
            if channel and daily_summary:
                embed = discord.Embed(
                    title=f"📊 일일 근무 시간 리포트 ({yesterday.strftime('%Y년 %m월 %d일')})",
                    description="\n".join(daily_summary),
                    color=discord.Color.blue()
                )
                embed.set_footer(text="자동 퇴근 처리되었습니다.")
                await channel.send(embed=embed)

    except Exception as e:
        print(f'자동 퇴근 처리 오류: {e}')

# 월요일 0시 주간 리포트
@tasks.loop(time=dt_time(hour=0, minute=0, second=0))
async def weekly_report():
    """월요일 0시에 주간 리포트 전송"""
    try:
        current_time = datetime.now()

        # 월요일이 아니면 종료
        if current_time.weekday() != 0:  # 0 = 월요일
            return

        # 지난주 월요일 ~ 일요일 계산
        last_monday = (current_time - timedelta(days=7)).date()
        last_sunday = (current_time - timedelta(days=1)).date()

        with get_db() as conn:
            cursor = conn.cursor()

            # 주간 근무 시간 집계
            cursor.execute('''
                SELECT
                    username,
                    SUM(work_seconds) as total_work_seconds,
                    COUNT(*) as work_days,
                    AVG(work_seconds) as avg_work_seconds
                FROM work_history
                WHERE date BETWEEN ? AND ?
                GROUP BY user_id, username
                ORDER BY total_work_seconds DESC
            ''', (last_monday.isoformat(), last_sunday.isoformat()))

            weekly_stats = cursor.fetchall()

            if not weekly_stats:
                return

            # 출석-기록 채널에 주간 리포트 전송
            channel = discord.utils.get(bot.get_all_channels(), name=ALLOWED_CHANNEL_NAME)
            if channel:
                embed = discord.Embed(
                    title=f"📈 주간 근무 시간 리포트",
                    description=f"{last_monday.strftime('%Y년 %m월 %d일')} ~ {last_sunday.strftime('%m월 %d일')}",
                    color=discord.Color.purple()
                )

                for stat in weekly_stats:
                    total_hours = stat['total_work_seconds'] // 3600
                    total_minutes = (stat['total_work_seconds'] % 3600) // 60
                    avg_hours = int(stat['avg_work_seconds']) // 3600
                    avg_minutes = (int(stat['avg_work_seconds']) % 3600) // 60

                    embed.add_field(
                        name=f"👤 {stat['username']}",
                        value=f"총 근무: {total_hours}시간 {total_minutes}분\n"
                              f"출근 일수: {stat['work_days']}일\n"
                              f"평균 근무: {avg_hours}시간 {avg_minutes}분",
                        inline=False
                    )

                embed.set_footer(text="수고하셨습니다!")
                await channel.send(embed=embed)

    except Exception as e:
        print(f'주간 리포트 오류: {e}')

@bot.tree.command(name="출근", description="출근을 기록합니다")
@channel_only()
async def work_start(interaction: discord.Interaction):
    """출근 명령어"""
    user_id = str(interaction.user.id)
    username = interaction.user.display_name
    current_time = datetime.now()

    with get_db() as conn:
        cursor = conn.cursor()

        # 이미 출근한 경우 확인
        cursor.execute('SELECT user_id FROM current_work_status WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            await interaction.response.send_message(
                f"❌ {interaction.user.mention}님은 이미 출근 상태입니다!",
                ephemeral=True
            )
            return

        # 출근 기록
        cursor.execute('''
            INSERT INTO current_work_status (user_id, username, start_time, total_break_seconds)
            VALUES (?, ?, ?, 0)
        ''', (user_id, username, current_time.isoformat()))

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
    # 먼저 응답 대기 상태로 전환 (3초 제한 회피)
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    username = interaction.user.display_name
    current_time = datetime.now()
    today = current_time.date()

    with get_db() as conn:
        cursor = conn.cursor()

        # 출근 기록 조회
        cursor.execute('SELECT * FROM current_work_status WHERE user_id = ?', (user_id,))
        record = cursor.fetchone()

        if not record:
            await interaction.followup.send(
                f"❌ {interaction.user.mention}님은 출근 기록이 없습니다!",
                ephemeral=True
            )
            return

        start_time = datetime.fromisoformat(record['start_time'])
        total_break = record['total_break_seconds']

        # 휴식 중인 경우 자동 복귀 처리
        if record['break_time']:
            break_start = datetime.fromisoformat(record['break_time'])
            break_duration = int((current_time - break_start).total_seconds())
            total_break += break_duration

        # 근무 시간 계산
        total_seconds = int((current_time - start_time).total_seconds())
        work_seconds = total_seconds - total_break

        # 히스토리에 저장
        cursor.execute('''
            INSERT INTO work_history (user_id, username, date, start_time, end_time, work_seconds, break_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, today.isoformat(), start_time.isoformat(),
              current_time.isoformat(), work_seconds, total_break))

        # 현재 상태에서 삭제
        cursor.execute('DELETE FROM current_work_status WHERE user_id = ?', (user_id,))

    # 시간 계산
    hours = work_seconds // 3600
    minutes = (work_seconds % 3600) // 60
    break_hours = total_break // 3600
    break_minutes = (total_break % 3600) // 60

    time_str = current_time.strftime('%Y년 %m월 %d일 %H:%M:%S')

    embed = discord.Embed(
        title="🔴 퇴근",
        description=f"{interaction.user.mention}님이 퇴근했습니다.",
        color=discord.Color.red()
    )
    embed.add_field(name="퇴근 시간", value=time_str, inline=False)
    embed.add_field(name="순수 근무 시간", value=f"{hours}시간 {minutes}분", inline=True)
    if total_break > 0:
        embed.add_field(name="휴식 시간", value=f"{break_hours}시간 {break_minutes}분", inline=True)
    embed.set_footer(text="퇴근 기록됨")

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="휴식", description="휴식을 시작합니다")
@channel_only()
@app_commands.describe(사유="휴식 사유를 입력하세요")
async def work_break(interaction: discord.Interaction, 사유: str):
    """휴식 명령어"""
    user_id = str(interaction.user.id)
    username = interaction.user.display_name
    current_time = datetime.now()

    with get_db() as conn:
        cursor = conn.cursor()

        # 출근 상태 확인
        cursor.execute('SELECT break_time FROM current_work_status WHERE user_id = ?', (user_id,))
        record = cursor.fetchone()

        if not record:
            await interaction.response.send_message(
                f"❌ {interaction.user.mention}님은 출근 상태가 아닙니다!",
                ephemeral=True
            )
            return

        # 이미 휴식 중인 경우
        if record['break_time']:
            await interaction.response.send_message(
                f"❌ {interaction.user.mention}님은 이미 휴식 중입니다!",
                ephemeral=True
            )
            return

        # 휴식 시작
        cursor.execute('UPDATE current_work_status SET break_time = ? WHERE user_id = ?',
                      (current_time.isoformat(), user_id))

        # 휴식 히스토리에 기록
        cursor.execute('''
            INSERT INTO break_history (user_id, username, reason, start_time)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, 사유, current_time.isoformat()))

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

    with get_db() as conn:
        cursor = conn.cursor()

        # 출근 상태 및 휴식 정보 조회
        cursor.execute('SELECT break_time, total_break_seconds FROM current_work_status WHERE user_id = ?', (user_id,))
        record = cursor.fetchone()

        if not record:
            await interaction.response.send_message(
                f"❌ {interaction.user.mention}님은 출근 상태가 아닙니다!",
                ephemeral=True
            )
            return

        # 휴식 중이 아닌 경우
        if not record['break_time']:
            await interaction.response.send_message(
                f"❌ {interaction.user.mention}님은 휴식 중이 아닙니다!",
                ephemeral=True
            )
            return

        # 휴식 시간 계산
        break_start = datetime.fromisoformat(record['break_time'])
        break_duration = int((current_time - break_start).total_seconds())
        new_total_break = record['total_break_seconds'] + break_duration

        # 현재 상태 업데이트
        cursor.execute('''
            UPDATE current_work_status
            SET break_time = NULL, total_break_seconds = ?
            WHERE user_id = ?
        ''', (new_total_break, user_id))

        # 휴식 히스토리 업데이트 (가장 최근 기록)
        cursor.execute('''
            UPDATE break_history
            SET end_time = ?, duration_seconds = ?
            WHERE user_id = ? AND end_time IS NULL
            ORDER BY start_time DESC
            LIMIT 1
        ''', (current_time.isoformat(), break_duration, user_id))

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
    with get_db() as conn:
        cursor = conn.cursor()

        # 현재 출근한 모든 사람 조회
        cursor.execute('SELECT * FROM current_work_status')
        all_users = cursor.fetchall()

        if not all_users:
            await interaction.response.send_message("📊 현재 출근한 인원이 없습니다.", ephemeral=True)
            return

    current_time = datetime.now()

    # 출근 인원과 휴식 인원 분류
    working = []
    on_break = []

    for record in all_users:
        username = record['username']
        start_time = datetime.fromisoformat(record['start_time'])
        total_break = record['total_break_seconds']

        elapsed = current_time - start_time
        elapsed_seconds = int(elapsed.total_seconds()) - total_break
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60

        start_time_str = start_time.strftime('%H:%M')

        if record['break_time']:
            break_start = datetime.fromisoformat(record['break_time'])
            break_elapsed = int((current_time - break_start).total_seconds())
            break_minutes = break_elapsed // 60
            on_break.append(f"**{username}** - 출근: {start_time_str} (휴식 {break_minutes}분째)")
        else:
            working.append(f"**{username}** - 출근: {start_time_str} (근무 {hours}시간 {minutes}분)")

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

    with get_db() as conn:
        cursor = conn.cursor()

        # 출근 상태 조회
        cursor.execute('SELECT * FROM current_work_status WHERE user_id = ?', (user_id,))
        record = cursor.fetchone()

        if not record:
            await interaction.response.send_message(
                f"📊 {interaction.user.mention}님은 현재 **퇴근** 상태입니다.",
                ephemeral=True
            )
            return

    start_time = datetime.fromisoformat(record['start_time'])
    current_time = datetime.now()
    total_break = record['total_break_seconds']

    # 순수 근무 시간 계산
    total_duration = current_time - start_time
    work_seconds = int(total_duration.total_seconds()) - total_break

    # 휴식 중이면 현재 휴식 시간도 빼기
    if record['break_time']:
        break_start = datetime.fromisoformat(record['break_time'])
        current_break = int((current_time - break_start).total_seconds())
        work_seconds -= current_break

    hours = work_seconds // 3600
    minutes = (work_seconds % 3600) // 60

    start_time_str = start_time.strftime('%H:%M:%S')

    embed = discord.Embed(
        title="📊 내 상태",
        color=discord.Color.blue()
    )

    if record['break_time']:
        embed.description = f"{interaction.user.mention}님은 현재 **휴식 중**입니다."
        break_start = datetime.fromisoformat(record['break_time'])
        break_elapsed = int((current_time - break_start).total_seconds())
        break_minutes = break_elapsed // 60
        embed.add_field(name="현재 휴식 시간", value=f"{break_minutes}분", inline=False)
    else:
        embed.description = f"{interaction.user.mention}님은 현재 **근무 중**입니다."

    embed.add_field(name="출근 시간", value=start_time_str, inline=True)
    embed.add_field(name="순수 근무 시간", value=f"{hours}시간 {minutes}분", inline=True)

    if total_break > 0:
        total_break_minutes = total_break // 60
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