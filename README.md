# 📧 Job Application Email Sender

Automated daily email sender for job applications. Add recruiter emails to `recipients.txt`, and the script sends a personalised HTML email with your resume attached — then moves processed addresses to `processed.txt` so you never send duplicates.

Built to run on a schedule (Linux cron / systemd / Windows Task Scheduler). Config-driven via `.env` — no code changes needed.

---

## Features

- ✅ Sends HTML emails with resume attachment
- ✅ Auto-injects **company name** from recipient's email domain (`hr@stripe.com` → *Stripe*)
- ✅ Moves sent addresses from `recipients.txt` → `processed.txt` with timestamp
- ✅ Safe retry — recipients are **never removed** if sending fails
- ✅ Rotating log file (`email_sender.log`) with structured output
- ✅ All config via `.env` — works on Windows & Ubuntu unchanged

---

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager  
  Install: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) generated

---

## Project Setup

### 1. Clone the repository

```bash
git clone https://github.com/poojan-solanki/job-email-sender.git
cd job-email-sender
```

### 2. Create the virtual environment and install dependencies

```bash
uv sync
```

### 3. Create the `.env` file

Create a `.env` file in the project root (it is gitignored):

```env
# Gmail credentials
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password

# File paths (relative to project root, or absolute)
RECIPIENTS_FILE=recipients.txt
PROCESSED_FILE=processed.txt
ATTACHMENT_PATH=your_resume.pdf
HTML_TEMPLATE=your_email_template.html

# Email content
EMAIL_SUBJECT=Application for AI/ML Engineer Role

# Timezone for logging timestamps
TIMEZONE=Asia/Kolkata

# Logging
LOG_FILE=email_sender.log
LOG_LEVEL=INFO        # DEBUG | INFO | WARNING | ERROR
```

> **Getting a Gmail App Password:**  
> Google Account → Security → 2-Step Verification → App Passwords → Generate

### 4. Add recipients

Open `recipients.txt` and add one email address per line:

```
recruiter@stripe.com
hr@openai.com
jobs@company.com
```

### 5. Test the setup

```bash
# Windows
.venv\Scripts\python.exe main.py

# Ubuntu / macOS
.venv/bin/python main.py
```

A successful run will:
- Send emails to all addresses in `recipients.txt`
- Append them to `processed.txt` with a timestamp
- Clear `recipients.txt`
- Write a log to `email_sender.log`

---

## Scheduling (Daily Automation)

### Option A — Linux cron (simple)

```bash
crontab -e
```

Add one of these lines:

```cron
# If system timezone = Asia/Kolkata → 10:00 AM IST
0 10 * * *  cd /path/to/job-email-sender && .venv/bin/python main.py

# If system timezone = UTC → 10:00 AM IST = 04:30 UTC
30 4 * * *  cd /path/to/job-email-sender && .venv/bin/python main.py
```

Check your system timezone:
```bash
timedatectl | grep "Time zone"
```

---

### Option B — systemd timer *(recommended — survives reboots)*

With `Persistent=true`, if the machine is off at the scheduled time, the job runs automatically on the next boot instead of being silently skipped.

**Step 1 — Create the service file**

```bash
sudo nano /etc/systemd/system/email-sender.service
```

```ini
[Unit]
Description=Job Application Email Sender
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=YOUR_LINUX_USERNAME
WorkingDirectory=/path/to/job-email-sender
ExecStart=/path/to/job-email-sender/.venv/bin/python /path/to/job-email-sender/main.py
StandardOutput=append:/path/to/job-email-sender/email_sender.log
StandardError=append:/path/to/job-email-sender/email_sender.log
```

**Step 2 — Create the timer file**

```bash
sudo nano /etc/systemd/system/email-sender.timer
```

```ini
[Unit]
Description=Run email sender daily at 10:00 AM

[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Step 3 — Enable and start**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-sender.timer
```

**Verify / debug:**

```bash
systemctl list-timers email-sender.timer   # next scheduled run
journalctl -u email-sender.service -f      # live log output
```

---

### Option C — Windows Task Scheduler

1. Open **Task Scheduler** → *Create Basic Task*
2. **Trigger**: Daily at 10:00 AM
3. **Action**: Start a program
   - Program: `C:\path\to\job-email-sender\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\path\to\job-email-sender`
4. Save and enable

---

## How It Works

```
Script triggered by scheduler
    │
    ├─ Load .env
    ├─ Validate config (missing vars/files → exit 1)
    ├─ Read recipients.txt
    │   └─ Empty? → log info, exit 0 (nothing to do today)
    ├─ Read HTML template
    ├─ Connect to Gmail SMTP
    │   └─ Auth/connection failure → log CRITICAL, exit 1
    │       recipients.txt NOT touched → retried on next run
    ├─ For each recipient:
    │   ├─ Inject company name from email domain
    │   └─ Send personalised HTML email with attachment
    ├─ Append sent addresses to processed.txt (with timestamp)
    ├─ Clear recipients.txt
    └─ Log "Run complete — N email(s) processed."
```

---

## File Structure

```
job-email-sender/
├── main.py               # Main script
├── recipients.txt        # Add emails here (one per line)
├── processed.txt         # Auto-populated after each run
├── email_sender.log      # Rotating log (auto-created)
├── your_resume.pdf       # Your resume (set path in .env)
├── your_template.html    # HTML email body (set path in .env)
├── .env                  # Config — gitignored, create manually
└── pyproject.toml        # Dependencies
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `GMAIL_APP_PASSWORD` not set | `CRITICAL` log + exit 1 |
| File not found (template/attachment) | `CRITICAL` log + exit 1 |
| `recipients.txt` empty | `INFO` log + exit 0 *(healthy)* |
| SMTP auth failure | `CRITICAL` log + exit 1, recipients **preserved** |
| SMTP connection failure | `CRITICAL` log + exit 1, recipients **preserved** |
| Unexpected error | `CRITICAL` log + exit 1, recipients **preserved** |

> **Safety guarantee:** `recipients.txt` is only cleared *after* all emails are confirmed sent. Any failure before that preserves the list for automatic retry on the next scheduled run.
