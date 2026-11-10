-- Database: mwananchi_shop_db

CREATE TABLE IF NOT EXISTS mpesa_transactions (
    id SERIAL PRIMARY KEY,
    merchant_request_id VARCHAR(100) UNIQUE,
    checkout_request_id VARCHAR(100) UNIQUE NOT NULL,
    phone_number VARCHAR(15) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    account_reference VARCHAR(100) DEFAULT 'Mwananchi Shop',
    transaction_status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, SUCCESS, FAILED, CANCELLED
    mpesa_receipt_number VARCHAR(50),
    result_code INT,
    result_desc TEXT,
    transaction_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_checkout_id ON mpesa_transactions (checkout_request_id);
CREATE INDEX idx_phone_number ON mpesa_transactions (phone_number);

-- Example tunnel command:
-- ngrok http 5000