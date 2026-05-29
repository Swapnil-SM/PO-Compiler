import sqlite3
import os
import gspread
from google.oauth2.service_account import Credentials


def get_connection():
    base_path = "C:\\POFiles"
    os.makedirs(base_path, exist_ok=True)

    db_path = os.path.join(base_path, "po_compiler.db")
    conn = sqlite3.connect(db_path)
    return conn


def create_tables():
    conn = get_connection()
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
    cur.close()
    conn.close()


def sync_sku_master():
    print("🔄 Syncing SKU master from Google Sheet...")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    SERVICE_ACCOUNT_FILE = os.path.join(script_dir, 'starlit-tangent-411613-a5467af2ab19.json')

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)


    spreadsheet = client.open_by_key("1IJ2Vlx-tjiARH9ZwzK2807Du-xRQ-nUwH60q_D0Cc8I")

    sheet = spreadsheet.worksheet("mt_po_master")

    records = sheet.get_all_records()

    conn = get_connection()
    cur = conn.cursor()

    # clear old
    cur.execute("DELETE FROM mt_po_master")

    for row in records:
        code = str(row.get("code", "")).strip()
        sku = str(row.get("sku", "")).strip()
        customer = str(row.get("customer", "")).strip()

        if code:
            cur.execute(
                "INSERT OR REPLACE INTO mt_po_master (code, sku, customer) VALUES (?, ?, ?)",
                (code, sku, customer)
            )

    conn.commit()
    cur.close()
    conn.close()

    print(" SKU master sync complete.")


