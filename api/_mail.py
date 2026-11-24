"""Outgoing email (password reset and email verification links) over SMTP.

Settings come from environment variables:
    SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASSWORD, MAIL_FROM
For Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=<the Gmail address>,
SMTP_PASSWORD=<a 16-character app password, not the Gmail password>.

Local development without SMTP: MAIL_DEV_LOG=1 writes the message (with its link) to the
server console instead of sending it. It is ignored on Vercel, so links never reach the
production logs.
"""
import html as _html_lib
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("lawliet.mail")


class MailNotConfigured(Exception):
    pass


class MailFailed(Exception):
    pass


def _dev_log_enabled() -> bool:
    return os.environ.get("MAIL_DEV_LOG") == "1" and not os.environ.get("VERCEL")


def mail_configured() -> bool:
    smtp = all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
    return smtp or _dev_log_enabled()


def send_mail(to: str, subject: str, text: str, html: str) -> None:
    """Raises MailNotConfigured or MailFailed. Never logs the SMTP password."""
    if not mail_configured():
        raise MailNotConfigured()
    if not os.environ.get("SMTP_HOST") and _dev_log_enabled():
        log.warning("MAIL_DEV_LOG: email to %s\nSubject: %s\n\n%s", to, subject, text)
        return

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    sender = os.environ.get("MAIL_FROM") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("L-Lawliet", sender))
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as smtp:
                smtp.login(user, os.environ["SMTP_PASSWORD"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls(context=context)
                smtp.login(user, os.environ["SMTP_PASSWORD"])
                smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        log.error("Sending email failed: %s", type(exc).__name__)
        raise MailFailed() from exc


def _html(heading: str, intro: str, link: str, button: str, footer: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#0A0A0F;font-family:Inter,Arial,sans-serif;color:#F5F5F7">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#12121A;border:1px solid #26262F;border-radius:16px;padding:32px">
<tr><td>
<p style="margin:0 0 8px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#F05A72">L-Lawliet account</p>
<h1 style="margin:0 0 16px;font-size:24px;line-height:1.25;color:#F5F5F7">{heading}</h1>
<p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#B4B4BE">{intro}</p>
<p style="margin:0 0 24px"><a href="{link}" style="display:inline-block;background:#DC143C;color:#fff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:10px">{button}</a></p>
<p style="margin:0 0 8px;font-size:13px;line-height:1.6;color:#8A8A96">If the button does not work, copy this link into your browser:</p>
<p style="margin:0 0 24px;font-size:13px;word-break:break-all;color:#B4B4BE">{link}</p>
<p style="margin:0;font-size:13px;line-height:1.6;color:#8A8A96">{footer}</p>
</td></tr></table></td></tr></table></body></html>"""


def reset_password_email(link: str, username: str, minutes: int) -> tuple[str, str, str]:
    subject = "Reset your L-Lawliet password"
    text = (
        f"Hi {username},\n\nSomeone asked to reset the password for your L-Lawliet account "
        f"(the same account works on JurisCards and JurisCards Arena).\n\n"
        f"Open this link within {minutes} minutes to choose a new password:\n{link}\n\n"
        "If you did not ask for this, ignore this email. Your password stays the same."
    )
    html = _html(
        "Reset your password",
        f"Hi {_html_lib.escape(username)}, someone asked to reset the password for your account. "
        f"The link works once and expires in {minutes} minutes.",
        link, "Choose a new password",
        "If you did not ask for this, ignore this email. Your password stays the same.",
    )
    return subject, text, html


def verify_email_email(link: str, username: str, hours: int) -> tuple[str, str, str]:
    subject = "Confirm your email for L-Lawliet"
    text = (
        f"Hi {username},\n\nConfirm this email address for your L-Lawliet account so you can "
        f"reset your password if you forget it.\n\nOpen this link within {hours} hours:\n{link}\n\n"
        "If you did not add this email, ignore this message."
    )
    html = _html(
        "Confirm your email",
        f"Hi {_html_lib.escape(username)}, confirm this address so you can reset your password if you ever forget it. "
        f"The link expires in {hours} hours.",
        link, "Confirm email",
        "If you did not add this email to an L-Lawliet account, ignore this message.",
    )
    return subject, text, html
