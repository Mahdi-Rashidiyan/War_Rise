# War Rise

War Rise is a multi-bot Telegram strategy game. Countries manage money and infrastructure, manufacture restricted weapons, conduct espionage, form alliances, negotiate, and fight wars.

## Local setup

1. Install Python 3.11 or newer.
2. Create an environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in every bot token, the admin Telegram ID, and channel usernames. Rotate the tokens that were previously stored in `config.py`.
4. Initialize the database:

```powershell
.venv\Scripts\python.exe database.py
```

5. Start all bots:

```powershell
.venv\Scripts\python.exe run_all_bots.py
```

The SQLite database is created as `game.db`. Back it up before upgrades; it is intentionally ignored by Git.

## VPS deployment

On Ubuntu/Debian:

```bash
sudo useradd --system --home /opt/war-rise --shell /usr/sbin/nologin war-rise
sudo mkdir -p /opt/war-rise
sudo chown war-rise:war-rise /opt/war-rise
git clone YOUR_PRIVATE_REPOSITORY_URL /opt/war-rise
cd /opt/war-rise
sudo -u war-rise python3 -m venv .venv
sudo -u war-rise .venv/bin/pip install -r requirements.txt
sudo -u war-rise cp .env.example .env
sudo -u war-rise nano .env
sudo -u war-rise .venv/bin/python database.py
sudo cp deploy/war-rise.service /etc/systemd/system/war-rise.service
sudo systemctl daemon-reload
sudo systemctl enable --now war-rise
sudo journalctl -u war-rise -f
```

Keep `.env` and `game.db` outside public repositories. Use a private GitHub repository and deploy with a read-only deploy key or a CI secret; never commit bot tokens.

## Operations

```bash
sudo systemctl status war-rise
sudo systemctl restart war-rise
sudo journalctl -u war-rise --since today
```

Telegram bots use long polling, so no public HTTP port or reverse proxy is required. Only the server's outbound internet access must be available.