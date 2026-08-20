"""S3-backed order summary document store.

Generates the PDF on first request, caches it in S3, and returns a
short-lived presigned URL. Regenerates when the order's updatedAt
timestamp changes (status/fulfilment progression).
"""

from __future__ import annotations

import hashlib
import logging

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .models import Order
from .pdf import generate_order_summary

logger = logging.getLogger(__name__)

PRESIGNED_TTL_SECONDS = 300


def _object_key(order: Order) -> str:
    version = hashlib.sha256(order.updatedAt.isoformat().encode()).hexdigest()[:12]
    return f"orders/{order.orderId}/summary-{version}.pdf"


class DocumentStore:
    def __init__(self, settings):
        self._settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            # Force SigV4 so presigned URLs carry X-Amz-Signature. boto3's
            # default in legacy regions (eu-west-1 included) is SigV2, which
            # produces AWSAccessKeyId/Signature-style URLs that some clients
            # and our newman/E2E contract tests do not accept.
            self._client = boto3.client(
                "s3",
                config=Config(signature_version="s3v4"),
                **self._settings.boto_kwargs(),
            )
        return self._client

    @property
    def bucket(self) -> str:
        return self._settings.order_summaries_bucket

    def _exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("403", "404", "NoSuchKey"):
                return False
            raise

    def get_summary_url(self, order: Order) -> str:
        key = _object_key(order)
        if not self._exists(key):
            pdf_bytes = generate_order_summary(order)
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=pdf_bytes,
                ContentType="application/pdf",
                ContentDisposition=f'attachment; filename="order-summary-{order.orderId}.pdf"',
            )
            logger.info("order summary generated", extra={"orderId": order.orderId, "key": key})

        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=PRESIGNED_TTL_SECONDS,
        )
