import boto3

class S3Downloader:
    def __init__(self, bucket_name, access_key, secret_key, region, base_path):
        self.bucket = bucket_name
        self.base_path = base_path  # offline/pocompilerfiles/

        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )

    def download_text_file(self, filename):
        key = f"{self.base_path}{filename}"
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read().decode("utf-8")

