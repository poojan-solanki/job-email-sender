# Walkthrough — Job Application Email Sender Rewrite

## `.env` Variables to Add

Open `.env` in the project root and add:

```env

GMAIL_USER=your-email-address
GMAIL_APP_PASSWORD=your_app_password_here

RECIPIENTS_FILE=recipients.txt
PROCESSED_FILE=processed.txt
ATTACHMENT_PATH=your_resume_filepath.pdf
HTML_TEMPLATE=email_body_filepath.html
EMAIL_SUBJECT=your_subject
TIMEZONE=Asia/Kolkata
LOG_FILE=email_sender.log
LOG_LEVEL=INFO
```

> Change any value in `.env`, and the script picks it up automatically on the next run.  
---

## How to Run Manually (test)

```bash
# Windows (laptop)
cd path/to/job-application
.venv\Scripts\python.exe main.py

# Ubuntu (office PC)
cd /path/to/job-application
.venv/bin/python main.py
```

---

## Setting Up the Daily Schedule

### Ubuntu — Linux cron

```bash
crontab -e
```

Add one of these lines:

```cron
# If Ubuntu timezone = Asia/Kolkata
0 10 * * *  cd /path/to/job-application && .venv/bin/python main.py

# If Ubuntu timezone = UTC  (10:00 IST = 04:30 UTC)
30 4 * * *  cd /path/to/job-application && .venv/bin/python main.py
```

Check your Ubuntu timezone:
```bash
timedatectl | grep "Time zone"
```

### Ubuntu — systemd timer *(recommended over cron)*

systemd timers survive reboots and — with `Persistent=true` — automatically run the missed job when the machine comes back online after being off at the scheduled time.

**Step 1 — Create the service unit**

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
User=YOUR_USERNAME
WorkingDirectory=/path/to/job-application
ExecStart=/path/to/job-application/.venv/bin/python /path/to/job-application/main.py
StandardOutput=append:/path/to/job-application/email_sender.log
StandardError=append:/path/to/job-application/email_sender.log
```

**Step 2 — Create the timer unit**

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

> `Persistent=true` means: if the machine was off at 10:00 AM, the job fires immediately on the **next boot** instead of waiting until tomorrow.

**Step 3 — Enable and start**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-sender.timer
```

**Verify it's scheduled:**

```bash
systemctl status email-sender.timer
systemctl list-timers email-sender.timer
```

**Run manually to test (without waiting for the timer):**

```bash
sudo systemctl start email-sender.service
journalctl -u email-sender.service -f
```

> **cron vs systemd timer** — cron is simpler to set up; systemd timer gives you better logging (`journalctl`), boot-time catch-up (`Persistent`), and dependency ordering (`After=network-online.target`).


### Windows — Task Scheduler

1. Open **Task Scheduler** → *Create Basic Task*
2. **Trigger**: Daily at 10:00 AM
3. **Action**: Start a program
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `P:\personal-programs\job-application`
4. Save and enable

---

## What Happens on Each Run

```
Run triggered (cron or Task Scheduler)
    │
    ├─ Load .env
    ├─ Set up logging (console + email_sender.log)
    ├─ Validate config (missing password/files → exit 1)
    ├─ Read recipients.txt
    │   └─ Empty? → log + exit 0 (clean, nothing to do)
    ├─ Read HTML template
    ├─ Connect to Gmail SMTP
    │   └─ Auth fail / connect fail → log CRITICAL, exit 1
    │       recipients.txt NOT touched → retried next run
    ├─ Send emails one by one
    ├─ Append to processed.txt  (e.g. "user@x.com  # processed at 2026-05-24 10:00:01")
    ├─ Clear recipients.txt
    └─ Log "Run complete — N email(s) processed."
```

---

## Error Handling Summary

| Error | Behaviour |
|---|---|
| `GMAIL_APP_PASSWORD` missing | `CRITICAL` log + `exit 1` |
| File not found | `CRITICAL` log + `exit 1` |
| `recipients.txt` empty | `INFO` log + `exit 0` (healthy, nothing to do) |
| SMTP auth failure | `CRITICAL` log + `exit 1`, recipients **preserved** for retry |
| SMTP connection failure | `CRITICAL` log + `exit 1`, recipients **preserved** for retry |
| Any other SMTP/unexpected error | `CRITICAL` log + `exit 1`, recipients **preserved** for retry |
| `processed.txt` write fails | `ERROR` log + `exit 1` with manual-action message |

> **Key safety rule**: `recipients.txt` is only cleared **after** emails are confirmed sent.  
> Any failure before that point leaves recipients intact for the next cron run.

---

## Log Output Example

```
2026-05-24 10:00:01 [INFO    ] ============================================================
2026-05-24 10:00:01 [INFO    ] Job Application Email Sender — run started
2026-05-24 10:00:01 [INFO    ] ============================================================
2026-05-24 10:00:01 [INFO    ] Loaded 2 recipient(s) from 'recipients.txt'.
2026-05-24 10:00:01 [INFO    ] Sending emails from 'poojan0105@gmail.com' | subject: 'Application for AI/ML Engineer Role'
Sent to recruiter1@company.com
Sent to recruiter2@company.com
2026-05-24 10:00:04 [INFO    ] All 2 email(s) sent successfully.
2026-05-24 10:00:04 [INFO    ] Appended 2 address(es) to 'processed.txt'.
2026-05-24 10:00:04 [INFO    ] Cleared 'recipients.txt'.
2026-05-24 10:00:04 [INFO    ] ============================================================
2026-05-24 10:00:04 [INFO    ] Run complete — 2 email(s) processed.
2026-05-24 10:00:04 [INFO    ] ============================================================
```
