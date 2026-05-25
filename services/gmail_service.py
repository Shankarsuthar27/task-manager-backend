import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL    = os.getenv("GMAIL_SENDER_EMAIL")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def _build_html(subject: str, body: str) -> str:
    """Wrap plain-text body in a clean HTML email template."""
    # Convert newlines to <br> tags and indent blocks
    html_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_body = html_body.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{subject}</title>
  <style>
    body {{ margin:0; padding:0; background:#0f0f1a; font-family:'Segoe UI',Arial,sans-serif; }}
    .wrapper {{ max-width:560px; margin:40px auto; background:#1a1a2e; border-radius:16px;
               overflow:hidden; box-shadow:0 8px 32px rgba(0,0,0,.5); }}
    .header {{ background:linear-gradient(135deg,#6366f1,#8b5cf6); padding:32px 40px; }}
    .header h1 {{ margin:0; color:#fff; font-size:22px; font-weight:700; letter-spacing:-.3px; }}
    .header p  {{ margin:4px 0 0; color:rgba(255,255,255,.75); font-size:13px; }}
    .body   {{ padding:32px 40px; color:#e2e8f0; font-size:15px; line-height:1.7; }}
    .card   {{ background:#252542; border-radius:12px; padding:20px 24px; margin:20px 0;
               border-left:4px solid #6366f1; }}
    .footer {{ padding:20px 40px; text-align:center; color:#4a4a6a; font-size:12px;
               border-top:1px solid #252542; }}
    a {{ color:#818cf8; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>✓ TaskFlow</h1>
      <p>Task Management &amp; Collaboration</p>
    </div>
    <div class="body">
      <div class="card">{html_body}</div>
      <p style="color:#64748b;font-size:13px;margin-top:24px;">
        Log in to <a href="#">TaskFlow</a> to view and manage your tasks.
      </p>
    </div>
    <div class="footer">© 2026 TaskFlow · You received this because you are part of a task.</div>
  </div>
</body>
</html>"""


def send_email(to: str, subject: str, body: str) -> None:
    if not EMAIL or not PASSWORD:
        print("Email credentials not configured. Skipping email send.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"TaskFlow <{EMAIL}>"
    msg["To"]      = to

    # Plain-text part (fallback)
    msg.attach(MIMEText(body, "plain"))

    # HTML part (preferred)
    msg.attach(MIMEText(_build_html(subject, body), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL, PASSWORD)
            server.sendmail(EMAIL, to, msg.as_string())
        print(f"Email sent successfully to {to}")
    except smtplib.SMTPAuthenticationError:
        print("SMTP Authentication failed. Check your Gmail App Password.")
    except smtplib.SMTPException as e:
        print(f"Failed to send email: {e}")
    except Exception as e:
        print(f"Unexpected error sending email: {e}")