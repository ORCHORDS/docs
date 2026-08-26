# Database Migration Deploy Strategy

## Overview

Database migrations require careful planning to ensure smooth deployments without downtime or data loss. This article covers essential strategies for safe database deployment including the expand-contract pattern, backward-compatible migrations, zero-downtime changes, and rollback safety measures.

## Expand-Contract Pattern

The expand-contract pattern minimizes downtime by first adding new infrastructure, then switching traffic, and finally removing old components.

```sql
-- Step 1: Add new columns (expand)
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN verification_token VARCHAR(255);

-- Step 2: Update application logic to use new columns
-- Application now writes to both old and new columns during transition

-- Step 3: Remove old columns (contract)
ALTER TABLE users DROP COLUMN legacy_email_status;
```

## Backward-Compatible Migrations

Ensure migrations work with both old and new application versions to prevent breaking existing functionality.

```sql
-- Safe migration that maintains compatibility
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    preference_key VARCHAR(100) NOT NULL,
    preference_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- Add index only if it doesn't exist
    INDEX idx_user_preference (user_id, preference_key)
);

-- Handle existing data during migration
INSERT INTO user_preferences (user_id, preference_key, preference_value)
SELECT id, 'default_theme', 'light' FROM users WHERE id NOT IN (
    SELECT DISTINCT user_id FROM user_preferences
);
```

## Zero-Downtime Schema Changes

Implement changes that don't require stopping the application.

```sql
-- Use online DDL for MySQL 5.6+
ALTER TABLE orders
ADD COLUMN shipping_address TEXT,
ALGORITHM=INPLACE, LOCK=NONE;

-- For PostgreSQL, use partial indexes and concurrent operations
CREATE INDEX CONCURRENTLY idx_orders_status_created
ON orders (status, created_at)
WHERE status IN ('pending', 'processing');

-- Add foreign key constraints without blocking
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order_id
FOREIGN KEY (order_id) REFERENCES orders(id)
NOT VALID;

-- Validate constraint later when safe
ALTER TABLE order_items VALIDATE CONSTRAINT fk_order_items_order_id;
```

## Rollback Safety

Always plan for rollback scenarios
