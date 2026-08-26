# PostgreSQL Full-Text Search

PostgreSQL's built-in full-text search capabilities provide powerful text searching functionality without requiring external services. This guide covers tsvector, tsquery, indexing, ranking, and more.

## Symptom

When you need to search through large volumes of text data efficiently, but don't want to implement complex external solutions like Elasticsearch. You might experience slow searches, poor relevance ranking, or inability to handle multiple languages effectively.

## Gotchas

- Default text search configuration may not work well for your language
- Without proper indexing, performance degrades significantly with large datasets
- Ranking functions can be counterintuitive without understanding weight assignments
- Highlighting requires careful handling of HTML content
- Multi-language support needs explicit configuration

## Core Concepts

### tsvector and tsquery

```sql
-- tsvector: tokenized and normalized text
SELECT to_tsvector('english', 'The quick brown fox jumps over the lazy dog');

-- tsquery: search query in tsearch format
SELECT to_tsquery('english', 'fox & dog');
```

### GIN Indexes for Performance

```sql
-- Create GIN index for fast full-text search
CREATE INDEX idx_fts_content ON documents USING GIN(content_tsvector);

-- Query with index usage
SELECT * FROM documents
WHERE content_tsvector @@ to_tsquery('english', 'search & terms');
```

### Ranking and Relevance

```sql
-- Calculate relevance scores
SELECT title, ts_rank(content_tsvector, query) as rank
FROM documents, to_tsquery('english', 'postgres & database') query
WHERE content_tsvector @@ query
ORDER BY rank DESC;

-- Custom ranking with weights
SELECT title,
       ts_rank_cd(content_tsvector, query, 4) as rank
FROM documents, to_tsquery('english', 'postgres & database') query
WHERE content_tsvector @@ query
ORDER BY rank DESC;
```

### Text Highlighting

```sql
-- Highlight search terms in text
SELECT title,
       ts_headline('english', content, query) as highlighted_content
FROM documents, to_tsquery('english', 'postgres & database') query
WHERE content_tsvector @@ query;

-- Custom highlight settings
SELECT ts_headline(
    'english',
    content,
    query,
    'MaxFragments=3, MinWords=1, MaxWords=20'
) as highlighted
FROM documents, to_tsquery
