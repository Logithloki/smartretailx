"""Tests for the order summary PDF generation and presigned URL endpoint."""

from __future__ import annotations

from decimal import Decimal

import boto3
import jwt
import pytest
from urllib.parse import urlparse, parse_qs

from app.models import FulfilmentStatus, Order, OrderItem, OrderStatus
from app.pdf import generate_order_summary

from conftest import auth_header, SUMMARIES_BUCKET


def _order(**overrides) -> Order:
    defaults = dict(
        orderId="ord-test123",
        userId="user-1",
        status=OrderStatus.CONFIRMED,
        fulfilmentStatus=FulfilmentStatus.NOT_STARTED,
        items=[
            OrderItem(
                productId="prod-laptop-001",
                productName="Laptop",
                quantity=2,
                baseUnitPrice=Decimal("19.99"),
                effectiveUnitPrice=Decimal("17.99"),
                unitDiscount=Decimal("2.00"),
                lineDiscount=Decimal("4.00"),
                lineTotal=Decimal("35.98"),
                promotionId="promo-summer",
            ),
        ],
        subtotal=Decimal("39.98"),
        discountTotal=Decimal("4.00"),
        totalAmount=Decimal("35.98"),
    )
    defaults.update(overrides)
    return Order(**defaults)


def _payload():
    return {"items": [{"productId": "prod-laptop-001", "quantity": 1}]}


class TestPdfGeneration:
    def test_generates_valid_pdf_bytes(self):
        order = _order()
        pdf_bytes = generate_order_summary(order)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 500

    def test_pdf_has_single_page(self):
        order = _order()
        pdf_bytes = generate_order_summary(order)
        assert b"/Count 1" in pdf_bytes

    def test_pdf_with_many_items_still_valid(self):
        items = [
            OrderItem(
                productId=f"p{i}", productName=f"Product {i}", quantity=i + 1,
                baseUnitPrice=Decimal("10.00"), effectiveUnitPrice=Decimal("10.00"),
                unitDiscount=Decimal("0"), lineDiscount=Decimal("0"),
                lineTotal=Decimal(str(10 * (i + 1))), promotionId=None,
            )
            for i in range(15)
        ]
        order = _order(
            items=items,
            subtotal=Decimal("1200.00"),
            discountTotal=Decimal("0"),
            totalAmount=Decimal("1200.00"),
        )
        pdf_bytes = generate_order_summary(order)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_pdf_with_rejected_order(self):
        order = _order(
            status=OrderStatus.REJECTED,
            statusReason="Insufficient stock",
        )
        pdf_bytes = generate_order_summary(order)
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 500

    def test_pdf_without_discount(self):
        order = _order(
            items=[
                OrderItem(
                    productId="p1", productName="Widget", quantity=1,
                    baseUnitPrice=Decimal("10.00"), effectiveUnitPrice=Decimal("10.00"),
                    unitDiscount=Decimal("0"), lineDiscount=Decimal("0"),
                    lineTotal=Decimal("10.00"), promotionId=None,
                ),
            ],
            subtotal=Decimal("10.00"),
            discountTotal=Decimal("0"),
            totalAmount=Decimal("10.00"),
        )
        pdf_bytes = generate_order_summary(order)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_pdf_with_delivered_fulfilment(self):
        order = _order(fulfilmentStatus=FulfilmentStatus.DELIVERED)
        pdf_bytes = generate_order_summary(order)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_pdf_with_long_product_name(self):
        order = _order(
            items=[
                OrderItem(
                    productId="p1",
                    productName="A" * 100,
                    quantity=1,
                    baseUnitPrice=Decimal("10.00"),
                    effectiveUnitPrice=Decimal("10.00"),
                    unitDiscount=Decimal("0"),
                    lineDiscount=Decimal("0"),
                    lineTotal=Decimal("10.00"),
                    promotionId=None,
                ),
            ],
            subtotal=Decimal("10.00"),
            discountTotal=Decimal("0"),
            totalAmount=Decimal("10.00"),
        )
        pdf_bytes = generate_order_summary(order)
        assert pdf_bytes[:5] == b"%PDF-"


class TestSummaryEndpoint:
    def test_owner_can_download_summary(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        assert resp.status_code == 201
        order_id = resp.json()["orderId"]

        resp = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-1", "customer"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["orderId"] == order_id
        assert "url" in body
        assert body["url"].startswith("https://")

    def test_non_owner_gets_404(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        order_id = resp.json()["orderId"]

        resp = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-2", "customer"))
        assert resp.status_code == 404

    def test_admin_can_download_any_summary(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        order_id = resp.json()["orderId"]

        resp = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("admin-1", "admin"))
        assert resp.status_code == 200
        assert resp.json()["orderId"] == order_id

    def test_nonexistent_order_returns_404(self, client, settings):
        resp = client.get("/v1/orders/ord-doesnotexist/summary", headers=auth_header("user-1", "customer"))
        assert resp.status_code == 404

    def test_summary_is_idempotent(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        order_id = resp.json()["orderId"]

        resp1 = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-1", "customer"))
        resp2 = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-1", "customer"))
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        s3 = boto3.client("s3", region_name="eu-west-1")
        objects = s3.list_objects_v2(Bucket=SUMMARIES_BUCKET, Prefix=f"orders/{order_id}/")
        assert objects["KeyCount"] == 1

    def test_pdf_stored_in_s3(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        order_id = resp.json()["orderId"]

        client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-1", "customer"))

        s3 = boto3.client("s3", region_name="eu-west-1")
        objects = s3.list_objects_v2(Bucket=SUMMARIES_BUCKET, Prefix=f"orders/{order_id}/")
        assert objects["KeyCount"] >= 1
        key = objects["Contents"][0]["Key"]
        obj = s3.get_object(Bucket=SUMMARIES_BUCKET, Key=key)
        body = obj["Body"].read()
        assert body[:5] == b"%PDF-"
        assert obj["ContentType"] == "application/pdf"

    def test_presigned_url_contains_signature(self, client, settings):
        resp = client.post("/v1/orders", json=_payload(), headers=auth_header("user-1", "customer"))
        order_id = resp.json()["orderId"]

        resp = client.get(f"/v1/orders/{order_id}/summary", headers=auth_header("user-1", "customer"))
        url = resp.json()["url"]
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        assert "X-Amz-Signature" in qs or "Signature" in qs
        assert "X-Amz-Expires" in qs or "Expires" in qs
