# AWS EC2 Ubuntu 운영 런북

이 문서는 기존 비트겟 봇을 정지하고 업비트 HUNT 자동매매 봇을 AWS EC2 Ubuntu에서 단독으로 실행하는 절차입니다. 두 봇을 동시에 실행하지 마세요.

## 1. AWS 공인 고정 IP 확인

EC2의 일반 `Public IPv4 address`는 인스턴스를 중지했다가 시작하면 바뀔 수 있습니다. 업비트 Open API에 등록할 주소는 AWS의 고정 공인 IPv4인 **Elastic IP address**를 사용합니다.

AWS 콘솔에서 다음 순서로 설정합니다.

1. `EC2 > Network & Security > Elastic IP addresses`로 이동합니다.
2. `Allocate Elastic IP address`를 누르고 생성합니다.
3. 생성된 주소를 선택하고 `Actions > Associate Elastic IP address`를 누릅니다.
4. Resource type은 `Instance`, 대상은 봇용 EC2 인스턴스로 선택한 뒤 `Associate`를 누릅니다.
5. EC2 인스턴스 상세 화면의 `Public IPv4 address`가 Elastic IP와 같은지 확인합니다.

서버에 SSH로 접속한 뒤 외부에서 보이는 IP도 확인합니다.

```bash
curl -4 https://checkip.amazonaws.com
```

이 명령의 결과와 AWS 콘솔의 Elastic IP가 같아야 합니다. 이 주소 하나를 업비트 Open API 허용 IP로 등록하고, 이후 SSH 접속 주소에도 사용합니다.

AWS는 사용 중이거나 미사용 중인 공인 IPv4에 현재 시간당 **USD 0.005**를 부과합니다. 30일 기준 약 USD 3.60이며, 사용하지 않는 Elastic IP도 비용이 발생하므로 여분 주소는 해제합니다.

참고:

- [AWS Elastic IP 개요](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html)
- [Elastic IP 할당 및 연결 방법](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html)
- [AWS Public IPv4 가격](https://aws.amazon.com/vpc/pricing/)

## 2. 기존 비트겟 봇 정지

비트겟 화면에서 포지션과 미체결 주문이 없는지 먼저 확인합니다. 서버에서 실행 중인 프로세스를 찾습니다.

```bash
pgrep -af 'bot.py|mybot'
```

결과에 표시된 봇 PID만 종료하고 다시 확인합니다.

```bash
kill <PID>
sleep 3
pgrep -af 'bot.py|mybot'
```

기존 폴더는 삭제하지 않고 백업합니다.

```bash
mv ~/mybot ~/mybot-bitget-backup-$(date +%Y%m%d-%H%M%S)
```

## 3. 서버 준비 및 코드 설치

권장 최소 구성은 Ubuntu LTS, `t4g.nano` 또는 `t3.nano`, 8 GiB EBS입니다. ARM 호환 여부를 단순화하려면 `t3.nano`를 선택합니다.

로컬 PowerShell에서 비밀키, 가상환경, 거래 상태, 로그를 제외한 배포 묶음을 만들고 전송합니다.

```powershell
Set-Location C:\path\huntbot
tar --exclude=.git --exclude=.venv --exclude=.env --exclude=data --exclude=logs `
  -czf $env:TEMP\huntbot-deploy.tgz .
scp -i C:\path\huntbot.pem $env:TEMP\huntbot-deploy.tgz ubuntu@<ELASTIC_IP>:~/
```

서버에서 압축을 풀고 설치 스크립트를 실행합니다.

```bash
rm -rf ~/huntbot-upload
mkdir -p ~/huntbot-upload
tar -xzf ~/huntbot-deploy.tgz -C ~/huntbot-upload
sudo bash ~/huntbot-upload/deploy/install-ubuntu.sh ~/huntbot-upload
```

최초 설치에서는 `/opt/huntbot/shared/.env`가 없으므로 종료 코드 2와 안내 문구가 나오는 것이 정상입니다. 이 단계에서 서비스는 설치만 되고 시작되지 않습니다.

## 4. API 키 등록

업비트 API 키에는 조회와 주문 권한만 부여하고 **출금 권한**은 부여하지 마세요. 업비트 Open API의 허용 IP에는 앞에서 확인한 Elastic IP만 등록합니다.

```bash
sudo install -o huntbot -g huntbot -m 600 /dev/null /opt/huntbot/shared/.env
sudoedit /opt/huntbot/shared/.env
```

다음 키를 입력합니다. 실제 값은 문서나 Git에 저장하지 않습니다.

```dotenv
UPBIT_OPEN_API_ACCESS_KEY=...
UPBIT_OPEN_API_SECRET_KEY=...
UPBIT_OPEN_API_SERVER_URL=https://api.upbit.com
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

설치 스크립트를 한 번 더 실행해 권한과 패키지를 확인합니다.

```bash
sudo bash ~/huntbot-upload/deploy/install-ubuntu.sh ~/huntbot-upload
```

## 5. 현재 거래 상태 이전

로컬 봇을 먼저 정지한 뒤 `data/state/auto-trading.json`을 서버로 보냅니다. 로컬과 AWS 봇을 동시에 실행하면 중복 주문 위험이 있습니다.

```powershell
Stop-ScheduledTask -TaskName "HuntBot-Auto-5m" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'huntbot run-auto-5m' } |
  Select-Object ProcessId, Name, CommandLine
Stop-Process -Id <PID1>,<PID2>

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item .\data\state\auto-trading.json ".\data\state\auto-trading-$stamp.json"
scp -i C:\path\huntbot.pem .\data\state\auto-trading.json ubuntu@<ELASTIC_IP>:~/auto-trading.json
```

`Get-CimInstance` 명령을 다시 실행해 봇 프로세스가 남아 있지 않은지 확인한 후 진행합니다. 상태파일의 `phase`가 실제 업비트 보유 수량과 일치하는지도 확인합니다.

서버에서 `pending_order`가 `null`인지 확인합니다. 값이 남아 있으면 서비스를 시작하지 말고 해당 주문 상태부터 확인합니다.

```bash
python3 -c "import json; d=json.load(open('/home/ubuntu/auto-trading.json')); print('phase=', d.get('phase')); print('pending_order=', d.get('pending_order'))"
sudo install -o huntbot -g huntbot -m 600 /home/ubuntu/auto-trading.json /opt/huntbot/shared/data/state/auto-trading.json
```

### 기존 서버를 30초 RSI 확인 코드로 갱신

현재 라이브 서비스를 먼저 정지하고 프로세스가 남지 않았는지 확인합니다.

```bash
sudo systemctl disable --now huntbot-auto
pgrep -af 'huntbot run-auto-5m' || true
```

업비트에서 미체결 주문을 확인하고, 상태파일의 `pending_order`가 `null`인지
확인한 뒤에만 진행합니다. 코드를 갱신하고 현재 커밋을 기록합니다.

```bash
cd ~/huntbot-upload
git fetch origin
git checkout codex/upbit-rsi-sell-bot
git pull --ff-only origin codex/upbit-rsi-sell-bot
git rev-parse --short HEAD
```

라이브 상태를 시각이 포함된 이름으로 백업한 뒤 설치합니다. 새 RSI 확인 필드는
기존 상태파일에 없어도 자동으로 `null` 기본값을 사용합니다.

```bash
stamp=$(date +%Y%m%d-%H%M%S)
sudo cp -a /opt/huntbot/shared/data/state/auto-trading.json \
  /opt/huntbot/shared/data/state/auto-trading.before-hold30s-$stamp.json
sudo bash deploy/install-ubuntu.sh ~/huntbot-upload
```

서비스를 시작하기 전에 새 코드로 기존 라이브 상태가 읽히는지 확인합니다. 이
명령은 주문을 보내지 않습니다.

```bash
sudo -u huntbot bash -lc 'cd /opt/huntbot/app && /opt/huntbot/venv/bin/python -c "from huntbot.auto_state import load_auto_state; s=load_auto_state(); print(\"phase=\", s.phase); print(\"pending_order=\", s.pending_order); print(\"rsi_signal_action=\", s.rsi_signal_action)"'
```

`pending_order=None`을 확인한 뒤 아래 1회 dry-run을 실행하고, 오류가 없을 때만
7절의 라이브 서비스 시작 명령을 실행합니다.

## 6. 주문 없는 1회 점검

라이브 서비스 시작 전에 dry-run을 한 번 실행합니다. 실제 잔고와 시세는 읽지만 주문은 보내지 않습니다.

```bash
sudo -u huntbot bash -lc 'cd /opt/huntbot/app && /opt/huntbot/venv/bin/python -m huntbot run-auto-5m --dry-run --once'
```

API 인증, 잔고 조회, 상태파일 읽기가 모두 정상인지 로그를 확인합니다.

## 7. 라이브 서비스 시작

모든 점검이 끝난 뒤에만 서비스를 활성화합니다.

```bash
sudo systemctl enable --now huntbot-auto
sudo systemctl status huntbot-auto
sudo journalctl -u huntbot-auto -f
```

파일 로그는 다음 위치에도 기록됩니다.

```bash
sudo tail -f /opt/huntbot/shared/logs/huntbot-auto.log
```

EC2를 한 번 **재부팅**하고 자동 시작 여부를 확인합니다.

```bash
sudo reboot
```

재접속한 뒤:

```bash
sudo systemctl status huntbot-auto
pgrep -af 'huntbot run-auto-5m'
sudo journalctl -u huntbot-auto --since boot
```

## 8. 로컬 대시보드용 데이터 받기

대시보드는 AWS에 상시 띄우지 않습니다. 필요할 때 로컬 PowerShell에서 상태와 로그만 내려받습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-aws-runtime.ps1 `
  -HostName <ELASTIC_IP> `
  -KeyPath C:\path\huntbot.pem

powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1
```

다운로드된 데이터는 `data/remote-runtime`에 저장됩니다. `.env`와 API 비밀키는 내려받지 않습니다.

## 9. 중지 및 롤백

긴급 중지:

```bash
sudo systemctl disable --now huntbot-auto
pgrep -af 'huntbot run-auto-5m'
```

서비스 중지 후 업비트의 미체결 주문과 보유 수량을 직접 확인합니다. 기존 비트겟 봇으로 되돌릴 때도 업비트 봇이 완전히 정지한 것을 먼저 확인하고, 두 자동매매 프로그램을 동시에 실행하지 마세요.
