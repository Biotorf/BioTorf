"""Run from backend with python -m unittest discover -s tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sqlite3
import unittest

from fastapi import HTTPException

import crm
import stock


class StockTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(crm.SCHEMA_CRM)
        stock.init_tables(self.conn)
        self.raw = self.product("Raw", "raw", "кг")
        self.pack = self.product("Bottle", "packaging", "шт")
        self.finished = self.product("Agro", "finished", "шт")

    def tearDown(self):
        self.conn.close()

    def product(self, name, kind, unit):
        with crm.write_transaction(self.conn) as tx:
            return stock.put_catalog(tx, "products", dict(sku=name, name=name, type=kind, unit=unit))["id"]

    def draft(self, kind, product, qty, cost=None, **fields):
        with crm.write_transaction(self.conn) as tx:
            return stock.put_document(tx, dict(doc_type=kind, items=[dict(product_id=product, qty=qty,
                                                                       unit_cost=cost)], **fields), "qa")["id"]

    def conduct(self, rid, action="conduct"):
        with crm.write_transaction(self.conn) as tx:
            return stock.transition(tx, rid, action)

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]

    def test_draft_purchase_weighted_average_and_cancellation(self):
        first = self.draft("purchase", self.raw, "2.1000", "4", warehouse_to_id="raw")
        self.assertEqual(self.count(), 0)
        self.conduct(first)
        second = self.draft("purchase", self.raw, "2.1000", "8", warehouse_to_id="raw")
        self.conduct(second)
        self.assertEqual(stock.totals(self.conn, "raw", self.raw), (42000, 252000))
        self.conduct(second, "cancel")
        self.conduct(second, "cancel")
        self.assertEqual(stock.totals(self.conn, "raw", self.raw), (21000, 84000))
        self.assertEqual(self.count(), 3)

    def test_transfer_preserves_cost_and_is_atomic(self):
        self.conduct(self.draft("purchase", self.raw, 5, 8, warehouse_to_id="raw"))
        rid = self.draft("move", self.raw, 2, warehouse_from_id="raw", warehouse_to_id="reject")
        self.conduct(rid)
        self.conduct(rid)
        self.assertEqual(stock.totals(self.conn, "raw", self.raw), (30000, 240000))
        self.assertEqual(stock.totals(self.conn, "reject", self.raw), (20000, 160000))
        self.assertEqual(self.count(), 3)
        self.conduct(rid, "cancel")
        self.assertEqual(stock.totals(self.conn, "reject", self.raw), (0, 0))

    def test_sale_above_stock_rejected(self):
        self.conduct(self.draft("purchase", self.finished, 2, 4, warehouse_to_id="finished"))
        sale = self.draft("sale", self.finished, 3, warehouse_from_id="finished")
        with self.assertRaises(HTTPException) as err:
            self.conduct(sale)
        self.assertEqual(err.exception.status_code, 409)
        self.assertEqual(stock.document(self.conn, sale)["status"], "draft")
        self.assertEqual(self.count(), 1)

    def test_production_rolls_back_on_shortage_and_sums_cost(self):
        self.conduct(self.draft("purchase", self.raw, 4, 6, warehouse_to_id="raw"))
        with crm.write_transaction(self.conn) as tx:
            recipe = stock.put_catalog(tx, "recipes", dict(
                output_product_id=self.finished, output_qty_per_batch=2, version="v1", is_active=True, items=[
                    dict(component_product_id=self.raw, warehouse_id="raw", qty_per_unit_output="0.5"),
                    dict(component_product_id=self.pack, warehouse_id="packaging", qty_per_unit_output=1),
                ]))
        rid = self.draft("production", self.finished, 2, warehouse_to_id="finished", recipe_id=recipe["id"])
        with self.assertRaises(HTTPException) as err:
            self.conduct(rid)
        self.assertIn("Bottle", err.exception.detail)
        self.assertEqual(stock.totals(self.conn, "raw", self.raw), (40000, 240000))
        self.conduct(self.draft("purchase", self.pack, 2, 2, warehouse_to_id="packaging"))
        self.conduct(rid)
        self.assertEqual(stock.totals(self.conn, "finished", self.finished), (20000, 100000))
        self.conduct(rid, "cancel")
        self.assertEqual(stock.totals(self.conn, "finished", self.finished), (0, 0))

    def test_sale_consumes_assigned_reserve_and_storno_restores_it(self):
        with crm.write_transaction(self.conn) as tx:
            crm._write(tx, "orders", {"id": "order"}, "order")
        self.conduct(self.draft("purchase", self.finished, 3, 11, warehouse_to_id="finished"))
        def use_connection(request, operation):
            with crm.write_transaction(self.conn) as tx:
                return operation(tx)
        from unittest.mock import patch
        with patch.object(stock, "mutation", use_connection):
            stock.reserve(dict(warehouse_id="finished", product_id=self.finished, order_id="order", qty=2,
                         expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
                         SimpleNamespace())
        other_sale = self.draft("sale", self.finished, 2, warehouse_from_id="finished")
        with self.assertRaises(HTTPException):
            self.conduct(other_sale)
        our_sale = self.draft("sale", self.finished, 2, warehouse_from_id="finished", order_id="order")
        self.conduct(our_sale)
        self.assertEqual(stock.reserved(self.conn, "finished", self.finished), 0)
        self.conduct(our_sale, "cancel")
        self.assertEqual(stock.reserved(self.conn, "finished", self.finished), 20000)

    def test_negative_warehouse_accepts_replenishment_at_different_price(self):
        with crm.write_transaction(self.conn) as tx:
            stock.put_catalog(tx, "warehouses", {"name": "Готовая продукция", "allow_negative": True}, "finished")
        self.conduct(self.draft("purchase", self.finished, 1, 4, warehouse_to_id="finished"))
        self.conduct(self.draft("sale", self.finished, 2, warehouse_from_id="finished"))
        self.conduct(self.draft("purchase", self.finished, 2, 7, warehouse_to_id="finished"))
        self.assertEqual(stock.totals(self.conn, "finished", self.finished), (10000, 70000))

    def test_source_edit_and_delete_require_reversal(self):
        with crm.write_transaction(self.conn) as tx:
            crm._write(tx, "shipments", {"id": "dispatch"}, "dispatch")
        self.conduct(self.draft("purchase", self.finished, 3, 4, warehouse_to_id="finished"))
        sale = self.draft("sale", self.finished, 1, warehouse_from_id="finished",
                          source_collection="shipments", source_id="dispatch")
        self.conduct(sale)
        with self.assertRaises(HTTPException) as error:
            crm.upsert(self.conn, "shipments", {"status": "Отменена"}, "dispatch", merge=True)
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            crm.delete(self.conn, "shipments", "dispatch")
        self.conduct(sale, "cancel")
        self.assertTrue(crm.delete(self.conn, "shipments", "dispatch"))

    def test_inventory_adjusts_actual_value(self):
        self.conduct(self.draft("inventory", self.raw, 3, 4, warehouse_to_id="raw"))
        self.conduct(self.draft("inventory", self.raw, 1, warehouse_to_id="raw"))
        self.assertEqual(stock.totals(self.conn, "raw", self.raw), (10000, 40000))


if __name__ == "__main__":
    unittest.main()
