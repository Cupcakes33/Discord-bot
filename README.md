# 🤖 Discord 출퇴근 기록 봇

디스코드에서 출퇴근 시간을 기록하고 관리하는 봇입니다.

---

## 📋 기능

- `/출근` - 출근 기록
- `/퇴근` - 퇴근 기록 및 근무 시간 계산
- `/휴식 [사유]` - 휴식 시작 (근무 시간에서 자동 제외)
- `/복귀` - 휴식 종료
- `/상태` - 내 출근 상태 확인
- `/현황` - 전체 인원 현황 확인
- `/명령어` - 도움말

✨ **휴식 시간은 근무 시간에서 자동으로 제외됩니다!**

---

## 🚀 설치 방법 (macOS)

### 1. 필요한 것
- Python 3.8 이상
- Discord Bot Token

### 2. Discord Bot 설정

1. [Discord Developer Portal](https://discord.com/developers/applications) 접속
2. 애플리케이션 생성
3. **Bot** 메뉴에서:
    - Bot Token 복사 (나중에 사용)
    - **Privileged Gateway Intents** 3개 모두 활성화:
        - ✅ PRESENCE INTENT
        - ✅ SERVER MEMBERS INTENT
        - ✅ MESSAGE CONTENT INTENT
4. **OAuth2 → URL Generator**에서:
    - SCOPES: `bot`, `applications.commands` 선택
    - BOT PERMISSIONS: `Send Messages`, `Read Message History`, `Use Slash Commands` 선택
    - 생성된 URL로 봇을 서버에 초대

### 3. 프로젝트 설정
```bash
# 프로젝트 폴더로 이동
cd /path/to/discordBot

# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# 가상환경 활성화되면 (venv) 표시됨
# 예: (venv) [discordBot]

# 라이브러리 설치
pip install -r requirements.txt

# 또는 개별 설치
pip install discord.py python-dotenv
```

### 4. 환경 변수 설정

`.env` 파일 생성:
```
DISCORD_TOKEN=your_bot_token_here
```
---

## 💻 실행 방법

### 기본 실행 (테스트용)
```bash
# 프로젝트 폴더로 이동
cd /path/to/discordBot

# 가상환경 활성화
source venv/bin/activate

# 봇 실행
python bot.py
```

**중지**: `Ctrl + C`

### 24시간 백그라운드 실행 (맥북 안 꺼지게)
```bash
# 프로젝트 폴더로 이동
cd /path/to/discordBot

# 가상환경 활성화 필요 없음 (venv/bin/python 직접 사용)
nohup caffeinate -dims venv/bin/python bot.py > bot.log 2>&1 &
```

**설명**:
- `venv/bin/python` - 가상환경의 Python을 직접 사용
- `nohup` - 터미널 종료해도 계속 실행
- `caffeinate -dims` - 맥북 잠자기 방지
- `> bot.log 2>&1` - 로그를 파일로 저장
- `&` - 백그라운드 실행

**💡 팁**: 백그라운드 실행할 때는 `source venv/bin/activate` 불필요!

---

## 🔍 관리 명령어

### 봇 상태 확인
```bash
# 프로세스 확인
ps aux | grep bot.py

# 로그 실시간 확인
tail -f bot.log

# 로그 전체 보기
cat bot.log
```

### 봇 중지
```bash
# 봇만 중지
pkill -f bot.py

# caffeinate까지 모두 중지
pkill -f caffeinate
pkill -f bot.py
```

### 봇 재시작
```bash
# 기존 봇 중지
pkill -f bot.py

# 다시 시작
cd /path/to/discordBot
nohup caffeinate -dims venv/bin/python bot.py > bot.log 2>&1 &

# 로그 확인
tail -f bot.log
```

---

## 📁 파일 구조
```
discordBot/
├── bot.py              # 봇 메인 코드
├── .env                # 환경 변수 (토큰)
├── requirements.txt    # 필요한 라이브러리
├── work_data.json      # 출근 기록 (자동 생성)
├── bot.log            # 실행 로그 (자동 생성)
├── venv/              # 가상환경 (자동 생성)
└── README.md          # 이 파일
```

---

## ⚙️ 채널 설정

봇은 기본적으로 **"출석-기록"** 채널에서만 작동합니다.

채널 이름을 변경하려면 `bot.py` 파일의 다음 부분을 수정:
```python
ALLOWED_CHANNEL_NAME = "원하는-채널-이름"
```

---

## 🐛 문제 해결

### 명령어가 안 보여요

1. 봇이 실행 중인지 확인: `ps aux | grep bot.py`
2. 로그 확인: `tail -f bot.log`
3. 디스코드 앱 재시작
4. 명령어 동기화는 1~10분 정도 걸릴 수 있습니다

### "애플리케이션이 응답하지 않습니다"

1. Discord Developer Portal에서 Intents 3개 모두 활성화했는지 확인
2. 봇 재시작: `pkill -f bot.py && nohup caffeinate -dims venv/bin/python bot.py > bot.log 2>&1 &`

### 봇이 자꾸 멈춰요

1. `caffeinate` 명령어를 사용했는지 확인
2. 맥북 전원 어댑터 연결 확인
3. 로그에서 에러 확인: `cat bot.log`

### ModuleNotFoundError 에러
```bash
source venv/bin/activate
pip install discord.py python-dotenv
```

---

## 🔐 보안 주의사항

- ⚠️ `.env` 파일과 Bot Token은 절대 공개하지 마세요
- ⚠️ GitHub에 업로드할 때 `.gitignore`에 `.env` 추가 필수
- ⚠️ Token이 유출되면 즉시 Discord Developer Portal에서 Reset Token

---

## 📊 사용 예시
```
# 출근하기
/출근
→ 🟢 홍길동님이 2025년 10월 22일 09:00:00에 출근했습니다.

# 휴식하기
/휴식 점심식사
→ 🟡 홍길동님이 점심식사 사유로 휴식합니다.

# 복귀하기
/복귀
→ 🟢 홍길동님이 업무에 복귀했습니다. (휴식 시간: 30분)

# 퇴근하기
/퇴근
→ 🔴 홍길동님이 퇴근했습니다. 
   순수 근무 시간: 8시간 30분
   휴식 시간: 30분

# 전체 현황 보기
/현황
→ 📊 출근 현황
   🟢 근무 중 (2명)
   🟡 휴식 중 (1명)
```