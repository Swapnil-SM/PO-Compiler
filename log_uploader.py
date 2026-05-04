import os
import socket
import boto3
from datetime import datetime
import json
import sys


def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def load_settings():
    base = get_base_path()
    with open(os.path.join(base, "posettings.json"), "r") as f:
        return json.load(f)


def upload_logs_to_s3():
    try:
        settings = load_settings()
        s3_settings = settings["AmazonS3"]

        bucket = s3_settings["BucketName"]
        region = s3_settings["Region"]
        access = s3_settings["AccessKeyId"]
        secret = s3_settings["SecretAccessKey"]
        base_path = s3_settings.get("BasePath", "offline/pocompilerfiles/")

        # ---- Local log file ----
        today = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join("logs", f"po_compiler_{today}.log")

        if not os.path.exists(log_file):
            print("ℹ No log file found for today. Skipping upload.")
            return

        # ---- Identify machine ----
        machine = socket.gethostname()

        # ---- Final S3 key ----
        s3_key = f"{base_path}logs/{machine}/po_compiler_{today}.log"

        # ---- S3 client ----
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=region
        )

        # ---- Upload ----
        s3.upload_file(log_file, bucket, s3_key)

        print(f"☁ Log uploaded successfully → s3://{bucket}/{s3_key}")

    except Exception as e:
        # ❗ Logging must NEVER break the application
        print("⚠ Log upload failed (ignored):", str(e))

