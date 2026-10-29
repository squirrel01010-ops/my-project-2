# 다른 계정에서 작업 이어가기

Python 3.12 기반 단일 서버용 Discord 봇과 웹 관리 화면입니다. README.md에 전체 기능과 실행 방법이 있습니다.

## 개발 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python run.py
```

관리자 키는 새로 생성해 .env의 ADMIN_TOKEN에 넣으세요. 봇 연결에는 DISCORD_TOKEN, DISCORD_GUILD_ID, DISCORD_CLIENT_ID가 필요합니다. 웹 Discord 로그인에는 DISCORD_CLIENT_SECRET과 Developer Portal의 OAuth 리디렉션 등록도 필요합니다. 로컬 개발 기본 URL은 http://127.0.0.1:8080입니다.

## 파일 구조

- core.py: 경험치, 경제, 설정, SQLite 데이터
- bot.py / social_bot.py: Discord 명령과 버튼
- games.py / poker.py / social.py: 게임과 정산
- app.py / public/: 웹 API와 관리 화면
- run.py / runtime_health.py: 봇과 웹 실행 및 상태 확인
- tests/: 격리된 테스트 데이터베이스를 사용하는 검사

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

## 현재 운영과 배포

Bot-Hosting 무료 Python 서버에서 봇과 웹을 실행합니다. 자세한 설정은 deploy/BOT-HOSTING.md를 참고하세요. 무료 플랜은 4일마다 수동 갱신과 봇 확인이 필요합니다. 유료 전환은 사용하지 않습니다.

저장소 변경은 운영 서버에 자동 배포되지 않습니다. 운영 중인 .env와 bot.db는 별도 보관됩니다. 배포할 때 두 파일을 덮어쓰거나 삭제하지 마세요. 운영 봇 토큰으로 개발용 인스턴스를 동시에 켜지 마세요. 테스트에는 별도 봇과 서버를 사용하세요. 데이터 이관은 기존 봇 중지 → SQLite 백업 → 새 서버로 이전 → 단일 인스턴스 실행 순서입니다.

## 다른 계정의 접근

공개 저장소는 다른 계정에서 Fork해 작업하고 PR을 만들 수 있습니다. 비공개 저장소는 소유자가 Settings → Collaborators에서 작업할 GitHub 계정을 초대해야 합니다. 다른 ChatGPT 계정에서는 그 GitHub 계정과 저장소를 연결하세요. 운영 호스팅 접근 권한과 비밀키는 GitHub 접근 권한과 별개입니다.

토큰, 관리자 키, 실사용 데이터, 배포 식별 정보는 저장소에 포함하지 않습니다.
