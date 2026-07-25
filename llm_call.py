import os
import sys
import json
import re
import pdfplumber
import pandas as pd
from datetime import datetime
from openai import OpenAI

from s3_downloader import S3Downloader
from mailer import fetch_pdf_from_mail, send_mail_with_pdf, databaseconnection
from excelgenerate import generate_excel, check_data_in_database, upload_po
from local_db import get_connection


import gspread
from google.oauth2.service_account import Credentials

import logging
logger = logging.getLogger("POCompiler")

def load_settings():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    settings_path = os.path.join(base_path, "posettings.json")

    with open(settings_path, "r") as f:
        return json.load(f)

#Initialize S3 Using posettings

settings = load_settings()
s3_settings = settings["AmazonS3"]

s3 = S3Downloader(
    bucket_name=s3_settings["BucketName"],
    access_key=s3_settings["AccessKeyId"],
    secret_key=s3_settings["SecretAccessKey"],
    region=s3_settings["Region"],
    base_path=s3_settings["BasePath"]
)


# Google Sheet Auth (same as old mrl.py)
script_dir = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(script_dir, 'starlit-tangent-411613-a5467af2ab19.json')

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

spreadsheet = client.open_by_key("1IJ2Vlx-tjiARH9ZwzK2807Du-xRQ-nUwH60q_D0Cc8I")
sheet = spreadsheet.worksheet("email_control")

def map_en_code_to_sku(en_code, company):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT sku FROM mt_po_master WHERE TRIM(LOWER(customer))=TRIM(LOWER(?)) AND TRIM(code)=TRIM(?)",
            (company.strip(), str(en_code).strip())
        )

        result = cur.fetchone()

        cur.close()
        conn.close()

        if result:
            return result[0]
        return "None"

    except Exception as e:
        print(f"SKU Mapping error for {en_code}: {e}")
        return "None"

class LLMPOExtractor:
    def __init__(self):
        try:
            api_key = s3.download_text_file("api.txt").strip()
            if not api_key:
                raise ValueError("API key file is empty")

            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1"
            )

        except Exception as e:
            raise RuntimeError(f"Failed to load API key from S3: {e}")
    # ---------------- LOAD PROMPT ----------------
    def load_prompt(self, retailer_key: str) -> str:
        try:
            prompt = s3.download_text_file(f"{retailer_key}.txt")
            if not prompt.strip():
                raise ValueError("Prompt file is empty")
            return prompt
        except Exception as e:
            raise RuntimeError(f"Failed to load prompt '{retailer_key}.txt' from S3: {e}")

    # ---------------- EXTRACT TEXT + TABLES ----------------
    def extract_pdf_content(self, pdf_path: str) -> str:
        content = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages[:4], start=1):
                text = page.extract_text()
                if text:
                    content += f"\n--- PAGE {page_num} TEXT ---\n{text}\n"

                tables = page.extract_tables()
                for table in tables:
                    if table:
                        content += f"\n--- PAGE {page_num} TABLE ---\n"
                        for row in table:
                            row_clean = [str(cell).strip().replace("\n", " ") if cell else "" for cell in row]
                            content += " | ".join(row_clean) + "\n"
        return content

    # ---------------- CALL LLM ----------------
    def call_llm(self, prompt_text: str, pdf_content: str) -> dict:
        final_prompt = f"""{prompt_text}
STRICT OUTPUT RULES:
- Output ONLY raw JSON
- Do NOT include explanations
- Do NOT include notes
- Do NOT wrap JSON in markdown
- JSON must start with {{ and end with }}

PURCHASE ORDER DOCUMENT CONTENT:
{pdf_content}
"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a structured data extraction engine."},
                    {"role": "user", "content": final_prompt}
                ],
                temperature=0,
                timeout=60  #  prevents silent connection hangs
            )
        except Exception as e:
            print("❌ LLM CONNECTION ERROR:", str(e))
            raise

        result_text = response.choices[0].message.content.strip()
        result_text = re.sub(r"```.*?```", "", result_text, flags=re.DOTALL).strip()
        # FIX: remove commas inside numbers
        result_text = re.sub(r'(?<=\d),(?=\d)', '', result_text)

        print("\n🔵 RAW LLM RESPONSE:\n", result_text[:2000])
        start = result_text.find("{")
        end = result_text.rfind("}")

        if start != -1 and end != -1:
            json_candidate = result_text[start:end + 1]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError as e:
                print("JSON PARSE ERROR:", e)
                print(" BROKEN JSON:\n", json_candidate[:1500])
                raise

        print("LLM RAW OUTPUT:\n", result_text[:1500])
        raise ValueError("LLM did not return valid JSON")

    # ---------------- MAIN PIPELINE ----------------
    def process_retailer(self, retailer_key, retailer_name, receiver_email, start_date, additional_path=""):
        company = retailer_name

        today_date = datetime.now().strftime("%d-%b-%Y")

        prompt_text = self.load_prompt(retailer_key)

        sender_email = []
        email_subject = []
        text_in_email = ""

        emailControlData = sheet.get_all_records()
        for emailData in emailControlData:
            if emailData['company'].strip().upper() == company.strip().upper():
                sender_email.append(emailData['senders_email'])
                email_subject.append(emailData['senders_subject'])
                text_in_email = emailData['text_in_email']

        print("📧 Searching mails from:", sender_email)
        print("📝 Subject filters:", email_subject)


        if additional_path:
            print("📎 Using manually uploaded file only")
            paths = [additional_path]
        else:
            print("📬 Fetching PO files from email")
            paths = fetch_pdf_from_mail(sender_email, email_subject, f"{start_date}", text_in_email)

        if not paths:
            print("❌ No PO emails found for selected date.")
            return "No PO emails found."

        podata = []

        for path in paths:
            try:
                print(f"📄 Processing PDF: {path}")

                pdf_content = self.extract_pdf_content(path)
                data = self.call_llm(prompt_text, pdf_content)

                po_number = data.get("po_number", "")
                po_exists = check_data_in_database(po_number)
                if po_exists:
                    print(f"⚠ PO {po_number} already exists. Skipping.")
                    continue

                # if po_exists:
                #     print(f"⚠ PO {po_number} already exists. INCLUDING for Excel test.")

                raw_address = data.get("shipping_address") or ""
                address_lines = [line.strip() for line in raw_address.split("\n") if line.strip()]
                shipping_address = ", ".join(address_lines[:2])[:250] if address_lines else "Not Available"

                full_gstin = data.get("supplier_gst", "")
                gstn = full_gstin[:2] if full_gstin else ""

                coads = []
                mapped_skus = []
                quantities = []

                for item in data.get("line_items", []):
                    en_code = item.get("en_code")
                    qty = item.get("quantity")

                    mapping_company = "Avenue Supermarts Ltd." if company.strip().upper() == "DMART" else company
                    sku_name = map_en_code_to_sku(en_code, mapping_company)

                    coads.append(en_code)
                    mapped_skus.append(sku_name)
                    quantities.append(qty)

                podata.append({
                    "PO_Number": po_number,
                    "Final_Address": shipping_address,
                    "Coad": coads,
                    "Mapped_SKUs": mapped_skus,
                    "Quantities": quantities,
                    "GSTN": gstn,
                    "Company": company,
                    "Date": today_date
                })

            except Exception as e:
                print(f"❌ Skipping file due to error: {path}")
                print("Reason:", str(e))
                continue

        df = pd.DataFrame(podata)

        if df.empty:
            po_list = [str(p.get("PO_Number", "")) for p in podata]
            po_text = ", ".join(po_list) if po_list else "Unknown PO"

            print(f"⚠ All POs already processed: {po_text}")
            return f"PO(s) {po_text} already processed. No email sent."

        upload_po(df)
        generate_excel(df, start_date)
        # Load PO settings to get correct base path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        posettings_path = os.path.join(script_dir, "posettings.json")

        with open(posettings_path, 'r') as json_file:
            settings = json.load(json_file)

        po_file_base = settings.get("POFilePath")
        upload_folder = os.path.join(po_file_base, "PO_Created_Files")

        filename = os.path.join(upload_folder, f"{company}_PO_File_{start_date}_to_{today_date}.xlsx")

        # build po list for success
        po_list = [str(p.get("PO_Number", "")) for p in podata]
        po_text = ", ".join(po_list) if po_list else "Unknown PO"

        mail_result = send_mail_with_pdf(receiver_email, filename, company, today_date)

        logger.info("📧 EMAIL SENT SUCCESSFULLY")
        logger.info(f"PO(s): {po_text}")
        logger.info(f"Excel File: {filename}")
        logger.info(f"Mail Result: {mail_result}")

        return f"PO(s) {po_text} → {mail_result}"


# ---------------- FUNCTION USED BY UI ----------------
def run_llm_po(recivers_email, start_date, additional_path, retailer_key=None, retailer_name=None):
    extractor = LLMPOExtractor()
    return extractor.process_retailer(
        retailer_key=retailer_key,
        retailer_name=retailer_name,
        receiver_email=recivers_email,
        start_date=start_date,
        additional_path=additional_path
    )


