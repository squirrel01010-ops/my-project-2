# Bot-Hosting.net 무료 배포 준비

계정 가입만으로 이 작업 환경에 계정 접근 권한이 생기지는 않습니다. 공식 OAuth MCP 연결 또는 별도 범위 제한 API 인증이 필요합니다.

공식 연결 안내: https://bot-hosting.net/mcp
MCP URL: https://bot-hosting.net/api/mcp
인증: OAuth

계정/무료 할당량을 확인한 후 Python 3.12 Application 하나에 웹과 봇을 함께 실행합니다. 기존 deployment가 있으면 먼저 확인하고 재사용 여부를 결정합니다. 유료 리소스나 credits:spend 권한은 사용하지 않습니다.

- Source: Archive, 압축 해제 시 파일이 최상위에 위치하는 orbit-free-hosting.zip
- Runtime: Python 3.12
- Entry File: run.py
- requirements.txt 자동 설치 지원 (패키지 버전은 requirements.lock 참고)
- 최대 무료 할당량: 256 MB RAM / 25% CPU / 512 MB storage / deployment 1개 (계정에서 재확인)
- HOST=0.0.0.0, PORT는 서비스가 할당한 primary port
- DB_PATH는 실제 영구 파일 영역의 bot.db, BACKUP_DIR도 같은 영구 영역의 backups
- PUBLIC_URL은 Domains에서 활성화한 HTTPS 하위 도메인
- REQUIRE_DISCORD=1
- DISCORD_TOKEN, DISCORD_GUILD_ID, DISCORD_CLIENT_ID는 별도 환경변수로 전달
- 웹 OAuth: DISCORD_CLIENT_SECRET 추가 및 리디렉션 PUBLIC_URL/auth/callback 등록
- ADMIN_TOKEN은 강한 난수로 생성해 비공개 환경변수로 전달

토큰·현재 DB는 소스 ZIP에 포함하지 않습니다. 실제 이관 시 기존 프로세스를 멈추고 최종 SQLite 백업을 생성해 별도로 업로드한 후 새 서비스를 시작합니다. 중복 봇이 실행되지 않게 확인합니다. 새 서비스 실패 시 이전 환경으로 되돌립니다.

무료 플랜은 4일마다 사용자가 갱신해야 합니다. 봇/웹의 실제 메모리 사용량과 데이터 지속성은 배포 후 검증해야 합니다. 가입/연결 완료 전에는 실제 배포가 완료된 것이 아닙니다.
