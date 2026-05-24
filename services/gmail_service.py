import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

def send_email(to, subject, body):

    msg = MIMEText(body)

    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)

    server.login(EMAIL, PASSWORD)

    server.sendmail(EMAIL, to, msg.as_string())

    server.quit()