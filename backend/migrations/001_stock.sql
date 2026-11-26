CREATE TABLE IF NOT EXISTS stock_products (
 id TEXT PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 unit TEXT NOT NULL CHECK(unit IN ('шт','кг','л')),
 type TEXT NOT NULL CHECK(type IN ('raw','packaging','finished','service')),
 min_stock_alert BIGINT NOT NULL DEFAULT 0 CHECK(min_stock_alert >= 0)
);
CREATE TABLE IF NOT EXISTS stock_warehouses (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, is_virtual INTEGER NOT NULL DEFAULT 0,
 allow_negative INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS stock_recipes (
 id TEXT PRIMARY KEY, output_product_id TEXT NOT NULL REFERENCES stock_products(id),
 output_qty_per_batch BIGINT NOT NULL CHECK(output_qty_per_batch > 0),
 version TEXT NOT NULL, is_active INTEGER NOT NULL,
 UNIQUE(output_product_id,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS stock_recipe_active ON stock_recipes(output_product_id) WHERE is_active=1;
CREATE TABLE IF NOT EXISTS stock_recipe_items (
 id TEXT PRIMARY KEY, recipe_id TEXT NOT NULL REFERENCES stock_recipes(id) ON DELETE CASCADE,
 component_product_id TEXT NOT NULL REFERENCES stock_products(id),
 warehouse_id TEXT NOT NULL REFERENCES stock_warehouses(id),
 qty_per_unit_output BIGINT NOT NULL CHECK(qty_per_unit_output > 0),
 UNIQUE(recipe_id,component_product_id,warehouse_id)
);
CREATE TABLE IF NOT EXISTS stock_documents (
 id TEXT PRIMARY KEY, doc_type TEXT NOT NULL CHECK(doc_type IN ('purchase','sale','move','writeoff','production','inventory','return')),
 number TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN ('draft','conducted','cancelled')),
 warehouse_from_id TEXT REFERENCES stock_warehouses(id), warehouse_to_id TEXT REFERENCES stock_warehouses(id),
 recipe_id TEXT REFERENCES stock_recipes(id), order_id TEXT, counterparty_id TEXT, source_collection TEXT, source_id TEXT,
 created_by TEXT NOT NULL, conducted_at TEXT, cancelled_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS stock_source_conducted ON stock_documents(source_collection,source_id,doc_type) WHERE status='conducted' AND source_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS stock_document_items (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES stock_documents(id) ON DELETE CASCADE,
 product_id TEXT NOT NULL REFERENCES stock_products(id), qty BIGINT NOT NULL CHECK(qty >= 0),
 unit_cost BIGINT CHECK(unit_cost >= 0), UNIQUE(document_id,product_id)
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES stock_products(id),
 warehouse_id TEXT NOT NULL REFERENCES stock_warehouses(id),
 qty BIGINT NOT NULL CHECK(qty <> 0), unit_cost BIGINT NOT NULL, value_delta BIGINT NOT NULL,
 document_id TEXT NOT NULL REFERENCES stock_documents(id), moved_at TEXT NOT NULL,
 reversal_of TEXT UNIQUE REFERENCES stock_movements(id)
);
CREATE INDEX IF NOT EXISTS stock_moves_balance ON stock_movements(warehouse_id,product_id);
CREATE INDEX IF NOT EXISTS stock_moves_report ON stock_movements(moved_at,product_id,warehouse_id);
CREATE INDEX IF NOT EXISTS stock_moves_product ON stock_movements(product_id,moved_at);
CREATE INDEX IF NOT EXISTS stock_moves_doc ON stock_movements(document_id);
CREATE TABLE IF NOT EXISTS stock_reservations (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES stock_products(id),
 warehouse_id TEXT NOT NULL REFERENCES stock_warehouses(id), order_id TEXT NOT NULL,
 qty BIGINT NOT NULL CHECK(qty > 0), expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_reservation_usage (
 document_id TEXT NOT NULL REFERENCES stock_documents(id),
 reservation_id TEXT NOT NULL REFERENCES stock_reservations(id),
 qty BIGINT NOT NULL CHECK(qty > 0), PRIMARY KEY(document_id,reservation_id)
);
CREATE INDEX IF NOT EXISTS stock_reservation_lookup ON stock_reservations(warehouse_id,product_id,expires_at,order_id);
CREATE TABLE IF NOT EXISTS stock_migrations (version INTEGER PRIMARY KEY);
