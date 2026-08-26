# Database Branching for Preview Environments

## Overview

Database branching is a critical practice for modern development workflows, enabling teams to create isolated preview environments without affecting production data. This approach supports continuous integration/continuous deployment (CI/CD) pipelines, reduces risk during feature development, and provides developers with realistic testing environments.

## Neon Branches

Neon provides robust branching capabilities through its serverless architecture. When creating preview environments, you can branch from your main database using the `CREATE DATABASE` command with specific parameters:

```sql
-- Create a new branch from main database
CREATE DATABASE preview_env FROM main_db;

-- Clone with specific configuration
CREATE DATABASE preview_env
FROM main_db
WITH (branch_name = 'feature-branch', retention_period = 7);
```

Neon's branching leverages copy-on-write technology, ensuring that each branch shares the same underlying data until changes occur, significantly reducing storage overhead.

## PlanetScale Branches

PlanetScale offers database branching through its branching feature, which creates lightweight copies of your production database. The process involves:

```sql
-- Create a new branch from main database
CREATE BRANCH preview_branch FROM main_db;

-- Configure branch settings
ALTER BRANCH preview_branch
SET (max_connections = 100, timezone = 'UTC');
```

PlanetScale's branching is particularly efficient for preview environments as it maintains consistency with production schema while allowing independent development.

## Turso

Turso implements database branching through its SQLite-based approach with copy-on-write semantics:

```sql
-- Create branch from base database
CREATE BRANCH preview_db FROM main_db;

-- Query branch with parameterized inputs
SELECT * FROM users WHERE id = ? AND status = ?;
```

Turso's architecture makes it ideal for preview environments due to its lightweight nature and fast branching capabilities.

## Ephemeral Database per PR

Implementing ephemeral databases per pull request ensures complete isolation between feature branches:

```sql
-- Create temporary database for PR
CREATE DATABASE pr_1234
FROM main_db
WITH (lifecycle = 'ephemeral', cleanup_after = '24h');

-- Parameterized cleanup query
DELETE FROM test_data WHERE created_at < ?;
```

This approach eliminates data contamination between different development efforts and ensures clean testing environments.

## Copy-on-Write Technology

Copy-on-write technology is fundamental to efficient database branching. When a branch is created, it initially shares the same data pages as the parent database:

```sql
-- Monitor copy-on-write usage
SELECT
    branch_name,
    shared_pages,
    modified_pages,
    total_size
FROM database_branches
WHERE branch_name = ?;

-- Create parameterized branch with monitoring
CREATE DATABASE ? FROM ? WITH (monitoring_enabled = true);
```

This approach minimizes storage requirements while maintaining data consistency and performance.

## Cleanup Strategies

Proper cleanup is essential for maintaining cost efficiency and environment hygiene:

```sql
-- Automated cleanup query
