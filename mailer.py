import os
import json
import smtplib
import imaplib
import email
import sys
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
# sys.path.append('/opt/airflow/scripts/Pocompilation/')
import sys
sys.path.append(r"C:\Users\HP\Documents\POcompilation")
script_dir = os.path.dirname(__file__)
posettings = os.path.join(script_dir, 'posettings.json')

with open(posettings, 'r') as json_file:
    data = json.load(json_file)
    
import sqlite3
import os


def databaseconnection():
    # DB will be created on client machine
    base_path = "C:\\POFiles"
    os.makedirs(base_path, exist_ok=True)

    db_path = os.path.join(base_path, "po_compiler.db")

    conn = sqlite3.connect(db_path)

    # create tables if not exist
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS compiledpurchaseorder (
        ponumber TEXT,
        address TEXT,
        code TEXT,
        sku TEXT,
        quantity INTEGER,
        gst TEXT,
        company TEXT,
        valuationdate TEXT,
        PRIMARY KEY (ponumber, code)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mt_po_master (
        code TEXT,
        sku TEXT,
        customer TEXT,
        PRIMARY KEY (code, customer)
    )
    """)

    conn.commit()

    return conn

# Load settings




po_file_path = data.get('POFilePath')
download_folder = os.path.join(po_file_path, "PO_Downloaded_Files")
os.makedirs(download_folder, exist_ok=True)

#Email credentials
imap_host = 'imap.gmail.com'
imap_user = data["POLogin"]["mail"]
imap_password = data["POLogin"]["password"]
def fetch_pdf_from_mail(sender_mail, email_subject, start_date_str, text_in_mail): # text_in_mail="PO Attached"


    paths = []
    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(imap_user, imap_password)
    mail.select('INBOX')

    for sender in sender_mail:
        for subject in email_subject:
            if subject:
                search_query = f'(FROM "{sender}") (SUBJECT "{subject}") (SINCE "{start_date_str}")'
            else:
                search_query = f'(FROM "{sender}") (SINCE "{start_date_str}")'   
            
            result, data = mail.search(None, search_query)

            for num in data[0].split():
                result, email_data = mail.fetch(num, '(RFC822)')
                raw_email = email_data[0][1]
                #convert raw email into readable format
                msg = email.message_from_bytes(raw_email)

                email_content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == 'text/plain':
                            email_content += part.get_payload(decode=True).decode(errors='ignore')
                else:
                    email_content = msg.get_payload(decode=True).decode(errors='ignore')

                if text_in_mail in email_content:
                    for part in msg.walk():
                        #print(part.get_content_type())
                        if part.get_content_type() in ['application/pdf', 'application/vnd.ms-excel','application/octet-stream','application/zip']:
                            filename = os.path.join(download_folder, part.get_filename())
                            with open(filename, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            print(f"Downloaded: {filename}")
                            paths.append(filename)

    mail.logout()
    return paths

def send_mail_with_pdf(emails, filename, company, today_date):
    print(emails)
    if os.path.exists(filename):
        with open(posettings, 'r') as json_file:
            data = json.load(json_file)
        
        smtp_server = 'smtp.gmail.com'
        smtp_port = 587
        sender_email = imap_user
        sender_password = imap_password  
        recipient_emails = data["MailSendTo"]["mailid"]
        subject = f'{company} PO Excel {today_date}'
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(emails)
        msg['Subject'] = subject
        
        body = f"{company} PO Automated"
        msg.attach(MIMEText(body, "plain"))
        
        with open(filename, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(filename)}')
            msg.attach(part)
        
        try:
            #Connects to Gmail server and logs in.
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, sender_password)
            print(sender_email)
            server.sendmail(sender_email, emails, msg.as_string())
            return "Mail sent successfully!"
        except Exception as e:
            return f"Error: {e}"
        finally: 
            server.quit()
    else:
        return "There is no mail or file does not exist"


# start_date =  (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
# fetch_pdf_from_mail(["noreply@b2be.com"],["LOTS Wholesale - RELEASED PURCHASE ORDERS"],f"{start_date}","") 
