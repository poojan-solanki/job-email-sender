"""
Job Application Email Sender
=============================
Run-once script designed to be triggered by an OS scheduler
(Linux cron / Windows Task Scheduler).

On each run:
  1. Reads recipients from RECIPIENTS_FILE
  2. Sends personalised job-application emails
  3. Moves sent addresses to PROCESSED_FILE (with timestamp)
  4. Clears RECIPIENTS_FILE

All configuration is driven by environment variables / .env file.
No hard-coded values except sensible defaults.

Scheduling examples
-------------------
Ubuntu  (10:00 AM IST, timezone already IST):
    0 10 * * *  cd /path/to/job-application && .venv/bin/python main.py

Ubuntu  (10:00 AM IST, timezone UTC):
    30 4 * * *  cd /path/to/job-application && .venv/bin/python main.py

Windows Task Scheduler:
    Program : C:\\path\\to\\.venv\\Scripts\\python.exe
    Arguments: C:\\path\\to\\job-application\\main.py
    Start in : C:\\path\\to\\job-application
    Trigger  : Daily at 10:00 AM
"""

import os
import sys
import smtplib
import time
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from email.message import EmailMessage

from dotenv import load_dotenv

# Load .env as early as possible so all os.environ lookups below see the values
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(log_file: str, log_level: str) -> logging.Logger:
    """Configure root logger with a rotating file handler and a console handler."""
    logger = logging.getLogger("email_sender")
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # Rotating file (10 MB × 5 backups)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning(
            "Could not open log file '%s': %s — logging to console only.", log_file, exc
        )

    return logger


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """
    Load all runtime config from environment variables (populated by .env).
    Every value is dynamic — change .env to change behaviour without touching code.
    """
    return {
        # Gmail credentials
        "sender":           os.environ.get("GMAIL_USER", "poojan0105@gmail.com"),
        "app_password":     os.environ.get("GMAIL_APP_PASSWORD"),

        # File paths (relative to CWD or absolute)
        "recipients_file":  os.environ.get("RECIPIENTS_FILE", "recipients.txt"),
        "processed_file":   os.environ.get("PROCESSED_FILE", "processed.txt"),
        "attachment_path":  os.environ.get("ATTACHMENT_PATH", ""),
        "html_template":    os.environ.get("HTML_TEMPLATE", ""),

        # Email content
        "subject":          os.environ.get("EMAIL_SUBJECT", "Application for AI/ML Engineer Role"),

        # Locale / scheduling
        "timezone":         os.environ.get("TIMEZONE", "Asia/Kolkata"),

        # Logging
        "log_file":         os.environ.get("LOG_FILE", "email_sender.log"),
        "log_level":        os.environ.get("LOG_LEVEL", "INFO"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# File helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_recipients(path: str) -> list[str]:
    """Return a list of non-empty email addresses from a text file (one per line)."""
    with open(path, "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def move_to_processed(
    recipients: list[str],
    processed_file: str,
    logger: logging.Logger,
) -> None:
    """Append sent addresses to processed_file with an ISO timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(processed_file, "a", encoding="utf-8") as fh:
        for addr in recipients:
            fh.write(f"{addr}  # processed at {timestamp}\n")
    logger.info("Appended %d address(es) to '%s'.", len(recipients), processed_file)


def clear_recipients(recipients_file: str, logger: logging.Logger) -> None:
    """Overwrite recipients_file with an empty file after a successful run."""
    with open(recipients_file, "w", encoding="utf-8") as fh:
        fh.write("")
    logger.info("Cleared '%s'.", recipients_file)


# ─────────────────────────────────────────────────────────────────────────────
# Company name helper
# ─────────────────────────────────────────────────────────────────────────────

def extract_company_name(email: str) -> str:
    """
    Derive a human-readable company name from an email address.

    Examples:
        recruiter@communication.com  →  "Communication"
        hr@openai.com                →  "Openai"
        jobs@big-corp.io             →  "Big-corp"
    """
    try:
        domain = email.split("@")[1]   # e.g. communication.com
        name   = domain.split(".")[0]  # e.g. communication
        return name.replace("-", " ").title()  # e.g. Communication
    except IndexError:
        return "Your Company"


# ─────────────────────────────────────────────────────────────────────────────
# Core email helpers  ← send_emails() untouched from original implementation
# ─────────────────────────────────────────────────────────────────────────────

def build_message(sender, recipient, subject, body, attachment_path):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    # ── Personalise: replace <company_name> placeholder (optional) ──
    # Only substitutes if the placeholder is present in the template.
    # Users whose template doesn't use it get the body sent as-is.
    PLACEHOLDER = "&lt;company_name&gt;"
    if PLACEHOLDER in body:
        company = extract_company_name(recipient)
        personalised_body = body.replace(PLACEHOLDER, company)
    else:
        personalised_body = body

    # ── Send as HTML so the template renders correctly ───────
    msg.set_content(personalised_body, subtype="html")

    if attachment_path:
        with open(attachment_path, "rb") as f:
            data = f.read()
        filename = os.path.basename(attachment_path)
        msg.add_attachment(
            data,
            maintype="application",
            subtype="octet-stream",
            filename=filename
        )
    return msg


def send_emails(sender, app_password, recipients_file, attachment_path, subject, body, send_at):
    recipients = read_recipients(recipients_file)

    target = datetime.strptime(send_at, "%Y-%m-%d %H:%M").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")
    )
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    wait_seconds = (target - now).total_seconds()

    if wait_seconds > 0:
        print(f"Waiting until {target.isoformat()} ...")
        time.sleep(wait_seconds)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, app_password)

        for recipient in recipients:
            msg = build_message(sender, recipient, subject, body, attachment_path)
            server.send_message(msg)
            print(f"Sent to {recipient}")


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def validate_config(cfg: dict, logger: logging.Logger) -> None:
    """Validate required config. Calls sys.exit(1) on any fatal issue."""
    errors = []

    if not cfg["app_password"]:
        errors.append("GMAIL_APP_PASSWORD is not set.")

    if not Path(cfg["recipients_file"]).exists():
        errors.append(f"RECIPIENTS_FILE not found: '{cfg['recipients_file']}'")

    if cfg["html_template"] and not Path(cfg["html_template"]).exists():
        errors.append(f"HTML_TEMPLATE not found: '{cfg['html_template']}'")

    if cfg["attachment_path"] and not Path(cfg["attachment_path"]).exists():
        errors.append(f"ATTACHMENT_PATH not found: '{cfg['attachment_path']}'")

    if errors:
        for err in errors:
            logger.critical("Config error: %s", err)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = load_config()
    logger = setup_logging(cfg["log_file"], cfg["log_level"])

    logger.info("=" * 60)
    logger.info("Job Application Email Sender — run started")
    logger.info("=" * 60)

    # ── Validate ──────────────────────────────────────────────
    validate_config(cfg, logger)

    recipients_file  = cfg["recipients_file"]
    processed_file   = cfg["processed_file"]
    attachment_path  = cfg["attachment_path"] or None
    html_template    = cfg["html_template"]

    # ── Read recipients ───────────────────────────────────────
    try:
        recipients = read_recipients(recipients_file)
    except OSError as exc:
        logger.error("Cannot read recipients file '%s': %s", recipients_file, exc)
        sys.exit(1)

    if not recipients:
        logger.info("'%s' is empty — no emails to send today. Exiting.", recipients_file)
        sys.exit(0)

    logger.info("Loaded %d recipient(s) from '%s'.", len(recipients), recipients_file)
    logger.debug("Recipients: %s", recipients)

    # ── Read HTML body ────────────────────────────────────────
    body = ""
    if html_template:
        try:
            with open(html_template, "r", encoding="utf-8") as fh:
                body = fh.read()
            logger.debug("Loaded HTML template '%s' (%d bytes).", html_template, len(body))
        except OSError as exc:
            logger.error("Cannot read HTML template '%s': %s", html_template, exc)
            sys.exit(1)

    # ── Derive send_at as "right now" so send_emails() skips sleep ──
    # Cron/Task Scheduler owns the timing; we just fire immediately.
    tz = ZoneInfo(cfg["timezone"])
    send_at = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    logger.info(
        "Sending emails from '%s' | subject: '%s'",
        cfg["sender"],
        cfg["subject"],
    )

    # ── Send ──────────────────────────────────────────────────
    try:
        send_emails(
            sender=cfg["sender"],
            app_password=cfg["app_password"],
            recipients_file=recipients_file,
            attachment_path=attachment_path,
            subject=cfg["subject"],
            body=body,
            send_at=send_at,
        )
        logger.info("All %d email(s) sent successfully.", len(recipients))

    except smtplib.SMTPAuthenticationError:
        logger.critical(
            "SMTP authentication failed. Verify GMAIL_USER and GMAIL_APP_PASSWORD."
            " Recipients NOT moved — will retry on next run."
        )
        sys.exit(1)

    except smtplib.SMTPConnectError as exc:
        logger.critical(
            "Could not connect to Gmail SMTP: %s. Recipients NOT moved — will retry on next run.", exc
        )
        sys.exit(1)

    except smtplib.SMTPException as exc:
        logger.critical(
            "SMTP error: %s. Recipients NOT moved — will retry on next run.", exc
        )
        sys.exit(1)

    except OSError as exc:
        logger.critical(
            "File error during sending: %s. Recipients NOT moved — will retry on next run.", exc
        )
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        logger.critical(
            "Unexpected error: %s. Recipients NOT moved — will retry on next run.", exc,
            exc_info=True,
        )
        sys.exit(1)

    # ── Move processed recipients ─────────────────────────────
    # Only reached if send_emails() completed without raising.
    try:
        move_to_processed(recipients, processed_file, logger)
        clear_recipients(recipients_file, logger)
    except OSError as exc:
        logger.error(
            "Failed to update recipient files after sending: %s. "
            "Emails were sent but '%s' was NOT cleared — "
            "remove sent addresses manually to avoid duplicates.",
            exc,
            recipients_file,
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Run complete — %d email(s) processed.", len(recipients))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()