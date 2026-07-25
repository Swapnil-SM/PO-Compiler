import os
import json
import smtplib
import imaplib
import email
import sys

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Add project path
sys.path.append(r"C:\Users\HP\Documents\POcompilation")

# Import database utilities
from local_db import get_connection, create_tables

# Load settings
script_dir = os.path.dirname(__file__)
posettings = os.path.join(script_dir, "posettings.json")

with open(posettings, "r") as json_file:
    data = json.load(json_file)

# Create database tables (if they don't exist)
create_tables()

# Paths
po_file_path = data.get("POFilePath")
download_folder = os.path.join(po_file_path, "PO_Downloaded_Files")
os.makedirs(download_folder, exist_ok=True)

# Email credentials
imap_host = "imap.gmail.com"
imap_user = data["POLogin"]["mail"]
imap_password = data["POLogin"]["password"]


def fetch_pdf_from_mail(sender_mail, email_subject, start_date_str, text_in_mail):
    """
    Fetch PDF/Excel/ZIP attachments from Gmail based on
    sender, subject, date and email body text.
    """

    paths = []

    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(imap_user, imap_password)
    mail.select("INBOX")

    for sender in sender_mail:
        for subject in email_subject:

            if subject:
                search_query = (
                    f'(FROM "{sender}") '
                    f'(SUBJECT "{subject}") '
                    f'(SINCE "{start_date_str}")'
                )
            else:
                search_query = (
                    f'(FROM "{sender}") '
                    f'(SINCE "{start_date_str}")'
                )

            result, data = mail.search(None, search_query)

            for num in data[0].split():

                result, email_data = mail.fetch(num, "(RFC822)")

                raw_email = email_data[0][1]

                msg = email.message_from_bytes(raw_email)

                email_content = ""

                if msg.is_multipart():

                    for part in msg.walk():

                        if part.get_content_type() == "text/plain":
                            email_content += (
                                part.get_payload(decode=True)
                                .decode(errors="ignore")
                            )

                else:

                    email_content = (
                        msg.get_payload(decode=True)
                        .decode(errors="ignore")
                    )

                if text_in_mail in email_content:

                    for part in msg.walk():

                        if part.get_content_type() in [
                            "application/pdf",
                            "application/vnd.ms-excel",
                            "application/octet-stream",
                            "application/zip",
                        ]:

                            filename = os.path.join(
                                download_folder,
                                part.get_filename()
                            )

                            with open(filename, "wb") as f:
                                f.write(part.get_payload(decode=True))

                            print(f"Downloaded: {filename}")

                            paths.append(filename)

    mail.logout()

    return paths


def send_mail_with_pdf(emails, filename, company, today_date):
    """
    Send generated Excel/PDF to recipients.
    """

    print(emails)

    if not os.path.exists(filename):
        return "There is no mail or file does not exist"

    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    sender_email = imap_user
    sender_password = imap_password

    subject = f"{company} PO Excel {today_date}"

    msg = MIMEMultipart()

    msg["From"] = sender_email
    msg["To"] = ", ".join(emails)
    msg["Subject"] = subject

    body = f"{company} PO Automated"

    msg.attach(MIMEText(body, "plain"))

    with open(filename, "rb") as attachment:

        part = MIMEBase("application", "octet-stream")

        part.set_payload(attachment.read())

        encoders.encode_base64(part)

        part.add_header(
            "Content-Disposition",
            f'attachment; filename={os.path.basename(filename)}'
        )

        msg.attach(part)

    server = None

    try:

        server = smtplib.SMTP(smtp_server, smtp_port)

        server.starttls()

        server.login(sender_email, sender_password)

        print(sender_email)

        server.sendmail(
            sender_email,
            emails,
            msg.as_string()
        )

        return "Mail sent successfully!"

    except Exception as e:

        return f"Error: {e}"

    finally:

        if server:
            server.quit()
