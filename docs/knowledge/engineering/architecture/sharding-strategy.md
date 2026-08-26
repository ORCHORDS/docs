# sharding-strategy

Database sharding distributes data across multiple database instances to improve performance and scalability. Here are practical strategies with real-world implications.

## Horizontal Partitioning

Horizontal partitioning splits rows of a table across different shards based on specific criteria. Unlike vertical partitioning (splitting columns), horizontal partitioning maintains complete rows but distributes them across servers.

```sql
-- Example: Customer table sharded by customer_id range
-- Shard 1: customer_id 1-1000000
-- Shard 2: customer_id 1000001-2000000
-- Shard 3: customer_id 2000001-3000000

SELECT * FROM customers WHERE customer_id = 1500000;
-- This query hits shard 2 only
```

## Hash-Based Sharding

Hash-based sharding uses a hash function to determine which shard stores a record. This approach provides even distribution but makes range queries difficult.

```python
# Python example of hash-based sharding
def get_shard_id(key, num_shards=4):
    return hash(str(key)) % num_shards

# Example: customer_id = 123456789
shard_id = get_shard_id(123456789, 4)  # Returns 1
# All records with same hash go to same shard
```

**Tradeoffs**: Even distribution vs. range query performance. Hash sharding works great for point lookups but fails on queries like "find all customers born in 2023."

## Range-Based Sharding

Range-based sharding assigns data to shards based on value ranges. This approach supports efficient range queries but can create uneven load distribution.

```sql
-- Example: User sessions sharded by date ranges
-- Shard 1: 2023-01-01 to 2023-03-31
-- Shard 2: 2023-04-01 to 2023-06-30
-- Shard 3: 2023-07-01 to 2023-09-30

SELECT * FROM user_sessions
WHERE session_start BETWEEN '2023-05-01' AND '2023-05-31';
-- This query hits shard 2 only
```

**Tradeoffs**: Range queries work well, but hotspots can occur if data distribution is uneven. For example, a new product launch might cause all sessions to go to one shard.

## Geo-Sharding

Geo-sharding distributes data based on geographic location, reducing latency for users in specific regions.

```python
# Example: User data sharded by country code
def get_shard_for_user(user_id, country_code):
    # Use country code as shard key
    return hash(country_code) % num_shards

# Users from US go to shard 1, EU to shard 2, Asia to shard 3
```

**Real-world gotcha**: If your user base is concentrated in one region, geo-sharding may not provide benefits. Also, cross-region queries become complex and expensive.

## Resharding

Resharding involves redistributing data when shard configuration changes. This is a complex operation requiring careful planning.

```python
# Example resharding workflow
def reshard_data(old_shard, new_shards):
    # 1. Read all data from old shard
    # 2. Calculate new shard assignments
    # 3. Write to new shards
    # 4. Update routing logic
    # 5. Validate consistency

    for record in read_from_old_shard(old_shard):
