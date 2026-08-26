# graph-database-neo4j

**Issue:** Relational databases require expensive self-joins for graph traversal queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Social graph, recommendation engine, or fraud detection needing shortest-path or friend-of-friend queries. Recursive CTEs in Postgres hitting depth limits.

## Pattern / Solution
Neo4j stores data as nodes and relationships with properties. Cypher query language for graph traversal. Index nodes by property. APOC library adds graph algorithms (PageRank, community detection, shortest path).

## Gotchas
- Neo4j community edition is single instance; clustering requires Enterprise
- Property values must be primitives -- no nested objects
- Dense nodes (millions of relationships) are a known performance issue
- For simple hierarchies, Postgres ltree or recursive CTE may be sufficient without adding Neo4j

## Related
- cte-common-table-expressions
- lateral-joins
- mongodb-schema-design
