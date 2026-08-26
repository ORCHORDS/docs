# Zero-Downtime Database Migrations

## Symptom

Database migrations causing application downtime during schema changes can severely impact user experience and business operations. When developers attempt to modify database schemas, they often encounter locking issues, long-running transactions, or service interruptions that require application shutdowns.

## Gotchas

- **Locking Issues**: Traditional ALTER TABLE commands lock tables, preventing read/write operations
- **Long Running Transactions**: Schema changes can take minutes, blocking concurrent operations
- **Application Crashes**: Unexpected downtime during migration window
- **Data Consistency**: Risk of data corruption during concurrent operations
- **Rollback Complexity**: Difficult to revert failed migrations without downtime

## Solutions

### Expand-Contract Pattern

The expand-contract approach involves adding new columns/tables and gradually migrating data:

```sql
-- Add new column with default value
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT false;

-- Create index concurrently (PostgreSQL)
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- Migrate existing data in batches
UPDATE users SET email_verified = true WHERE email IS NOT NULL;
```

### Backward Compatible Changes

Ensure all schema modifications maintain compatibility with older application versions:

```sql
-- Add column with default, maintain backward compatibility
ALTER TABLE products ADD COLUMN category_id INTEGER DEFAULT 1;

-- Create index concurrently to avoid blocking
CREATE INDEX CONCURRENTLY idx_products_category ON products(category_id);

-- Add foreign key constraint (PostgreSQL)
ALTER TABLE products ADD CONSTRAINT fk_category
FOREIGN KEY (category_id) REFERENCES categories(id);
```

### Add Column with Default Values

Modern databases support adding columns with default values without locking:

```sql
-- PostgreSQL example
ALTER TABLE orders ADD COLUMN status VARCHAR(20) DEFAULT 'pending';

-- MySQL example
ALTER TABLE orders ADD COLUMN status VARCHAR(20) DEFAULT 'pending' COMMENT 'Order status';

-- SQL Server example
ALTER TABLE orders ADD status VARCHAR(20) DEFAULT 'pending';
```

### Create Index Concurrently

Use concurrent index creation to avoid table locks:

```sql
-- PostgreSQL - creates index without blocking writes
CREATE INDEX CONCURRENTLY idx_orders_created_at ON orders(created_at);

-- MySQL 8.0+ - online DDL
ALTER TABLE orders ADD INDEX idx_status (status), ALGORITHM=INPLACE, LOCK=NONE;

-- Oracle - online redefinition
BEGIN
  DBMS_REDEFINITION.START_REDEF_TABLE(
    uname
