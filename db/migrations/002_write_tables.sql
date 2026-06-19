BEGIN;

CREATE TABLE IF NOT EXISTS restock_requests (
    request_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      VARCHAR(20) NOT NULL REFERENCES products(product_id),
    region          VARCHAR(50) NOT NULL,
    quantity        INTEGER     NOT NULL CHECK (quantity > 0),
    priority        VARCHAR(20) NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_progress', 'fulfilled', 'cancelled')),
    requested_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
    fulfilled_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_restock_requests_product ON restock_requests(product_id);
CREATE INDEX IF NOT EXISTS idx_restock_requests_region  ON restock_requests(region);
CREATE INDEX IF NOT EXISTS idx_restock_requests_status  ON restock_requests(status);

CREATE TABLE IF NOT EXISTS discount_applications (
    application_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id       VARCHAR(20)  NOT NULL REFERENCES products(product_id),
    discount_percent NUMERIC(5,2) NOT NULL CHECK (discount_percent BETWEEN 1 AND 50),
    duration_days    INTEGER      NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
    reason           TEXT         NOT NULL DEFAULT '',
    status           VARCHAR(20)  NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'expired', 'cancelled')),
    applied_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMP    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_discount_applications_product ON discount_applications(product_id);
CREATE INDEX IF NOT EXISTS idx_discount_applications_status  ON discount_applications(status);
CREATE INDEX IF NOT EXISTS idx_discount_applications_expires ON discount_applications(expires_at);

COMMIT;