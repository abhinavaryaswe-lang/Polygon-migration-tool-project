"""Storage interface and Cloudflare R2 implementation for migrated files."""

from typing import Protocol

import boto3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class TestCaseStorage(Protocol):
    """Provider-neutral operations used by the Polygon migration flow."""

    def upload_test_case(self, problem_id, test_number, input_data, output_data): ...

    def upload_bytes(self, key, data): ...

    def delete_problem_files(self, problem_id): ...


class R2Storage:
    """Store test cases in a Cloudflare R2 bucket through its S3 API."""

    def __init__(self):
        account_id = settings.R2_ACCOUNT_ID
        access_key_id = settings.R2_ACCESS_KEY_ID
        secret_access_key = settings.R2_SECRET_ACCESS_KEY
        self.bucket_name = settings.R2_BUCKET_NAME
        endpoint_url = settings.R2_ENDPOINT_URL or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )

        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", account_id),
                ("R2_ACCESS_KEY_ID", access_key_id),
                ("R2_SECRET_ACCESS_KEY", secret_access_key),
                ("R2_BUCKET_NAME", self.bucket_name),
                ("R2_ENDPOINT_URL", endpoint_url),
            )
            if not value
        ]
        if missing:
            raise ImproperlyConfigured(
                "Missing R2 configuration: " + ", ".join(missing)
            )

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=settings.R2_REGION,
        )

    def upload_test_case(self, problem_id, test_number, input_data, output_data):
        input_key = f"test_cases/{problem_id}/{test_number:02d}"
        output_key = f"test_cases/{problem_id}/{test_number:02d}.a"
        self.upload_bytes(input_key, input_data)
        self.upload_bytes(output_key, output_data)

    def upload_bytes(self, key, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.client.put_object(Bucket=self.bucket_name, Key=key, Body=data)

    def delete_problem_files(self, problem_id):
        prefix = f"test_cases/{problem_id}/"
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if not objects:
                continue
            response = self.client.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": objects, "Quiet": True},
            )
            errors = response.get("Errors", [])
            if errors:
                raise RuntimeError(
                    f"Could not delete all R2 objects under {prefix}: {errors}"
                )
