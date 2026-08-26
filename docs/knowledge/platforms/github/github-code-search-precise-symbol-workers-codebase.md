# GitHub Code Search Precise Symbol Search for Workers Codebases

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain a large Cloudflare Workers / TypeScript monorepo and need to:
- Find every call-site of an exported function before renaming it
- Audit all places a specific type or interface is referenced
- Identify which Workers import a deprecated binding helper
- Build a code-intelligence dashboard that answers "where is `DurableObjectState` used?"

GitHub's standard keyword search returns too many false positives (string literals, comments,
docs). You need **precise symbol search** backed by GitHub's Kythe-based code-intelligence index.

---

## Context

GitHub Code Search (github.com › Search › Code) gained a tree-sitter + Kythe index in 2023 that
supports language-aware **symbol** queries. As of 2026 it covers TypeScript, JavaScript, Go, Python,
Ruby, Java, C/C++, C#, Rust, and Kotlin. Workers TypeScript projects are fully indexed.

Key qualifiers:

| Qualifier | Meaning |
|-----------|---------|
| `symbol:FunctionName` | Match declarations **and** call-sites of the named symbol |
| `symbol:/regex/` | Regex over symbol names |
| `language:TypeScript` | Scope to `.ts` / `.tsx` files |
| `path:src/workers/` | Limit to a directory subtree |
| `repo:owner/name` | Scope to one repository |
| `org:myorg` | Scope to all repos in an org |
| `NOT symbol:…` | Boolean negation |

Symbol search goes through the parsed AST — it matches **identifiers** in definition and usage
positions, not arbitrary text. A search for `symbol:fetch` in a TypeScript repo will not match the
string `"fetch"` inside a comment or log statement.

---

## Using the Web UI

```
# Find every call-site of a custom `handleRequest` export in your org
org:acme-corp symbol:handleRequest language:TypeScript

# Find all usages of the `Env` interface across Workers in one repo
repo:acme-corp/api-gateway symbol:Env language:TypeScript

# Regex: any symbol starting with `use` (React-style hooks in Workers Pages)
repo:acme-corp/frontend symbol:/^use[A-Z]/ language:TypeScript
```

Results show:
- **Definition** rows (function declaration, class definition, interface, type alias)
- **Reference** rows (call expression, import specifier, type annotation)

Click any row to jump to the file with the relevant lines highlighted.

---

## GitHub Code Search REST API

The same index is exposed via the REST API. Use it from a Cloudflare Worker to build
code-intelligence tooling or automated refactor audits.

```typescript
// src/workers/code-search.ts
export interface Env {
  GITHUB_TOKEN: KVNamespace; // Store token in KV, not plain env
  RESULTS_DB: D1Database;
}

interface CodeSearchItem {
  name: string;
  path: string;
  repository: { full_name: string };
  url: string;
  score: number;
  text_matches?: Array<{
    fragment: string;
    matches: Array<{ text: string; indices: [number, number] }>;
  }>;
}

async function searchSymbol(
  token: string,
  query: string,
  perPage = 30,
): Promise<CodeSearchItem[]> {
  const url = new URL("https://api.github.com/search/code");
  url.searchParams.set("q", query);
  url.searchParams.set("per_page", String(perPage));

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github.text-match+json", // enable text_matches
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "acme-code-intelligence/1.0",
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub Code Search failed ${res.status}: ${body}`);
  }

  const data = (await res.json()) as { items: CodeSearchItem[]; total_count: number };
  return data.items;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get("symbol");
    const repo = searchParams.get("repo");

    if (!symbol || !repo) {
      return new Response("Missing ?symbol= and ?repo=", { status: 400 });
    }

    const token = await env.GITHUB_TOKEN.get("pat");
    if (!token) return new Response("No token configured", { status: 500 });

    // Precise symbol query — note the "symbol:" qualifier
    const query = `symbol:${symbol} repo:${repo} language:TypeScript`;
    const items = await searchSymbol(token, query);

    // Persist results to D1 for trend tracking
    const stmt = env.RESULTS_DB.prepare(
      `INSERT OR REPLACE INTO symbol_refs
         (symbol, repo, path, url, captured_at)
       VALUES (?, ?, ?, ?, datetime('now'))`,
    );
    const batch = items.map((item) =>
      stmt.bind(symbol, item.repository.full_name, item.path, item.url),
    );
    await env.RESULTS_DB.batch(batch);

    return Response.json({ symbol, repo, count: items.length, items });
  },
};
```

---

## Paginating Large Result Sets

The Code Search API caps at **1 000 results per query** and **100 per page**. If your codebase has
more usages than that, split by path prefix or by sub-directory.

```typescript
async function paginateSearch(
  token: string,
  baseQuery: string,
): Promise<CodeSearchItem[]> {
  const all: CodeSearchItem[] = [];
  let page = 1;
  const perPage = 100;

  while (true) {
    const url = new URL("https://api.github.com/search/code");
    url.searchParams.set("q", baseQuery);
    url.searchParams.set("per_page", String(perPage));
    url.searchParams.set("page", String(page));

    const res = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "acme-code-intelligence/1.0",
      },
    });

    // Respect secondary rate limits
    const retryAfter = res.headers.get("Retry-After");
    if (res.status === 429 || res.status === 403) {
      const delay = retryAfter ? parseInt(retryAfter, 10) * 1000 : 60_000;
      await new Promise((r) => setTimeout(r, delay));
      continue; // retry same page
    }

    const data = (await res.json()) as { items: CodeSearchItem[]; total_count: number };
    all.push(...data.items);

    if (all.length >= data.total_count || data.items.length < perPage) break;
    page++;

    // Code Search secondary rate limit: 10 requests/minute for authenticated
    await new Promise((r) => setTimeout(r, 6_100));
  }

  return all;
}
```

---

## GraphQL Code Search (Search v2)

For org-wide queries with richer metadata, use GraphQL `searchResultItem`:

```graphql
query PreciseSymbolSearch($query: String!, $after: String) {
  search(query: $query, type: CODE, first: 10, after: $after) {
    codeCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        ... on SearchResultItemConnection { __typename }
        ... on Repository { nameWithOwner }
      }
      textMatches {
        fragment
        highlights { text beginIndentation }
      }
    }
  }
}
```

Variables: `{ "query": "symbol:handleRequest org:acme-corp language:TypeScript" }`

> Note: GraphQL code search is in public beta as of 2026-Q1 and requires
> `X-Github-Next-Global-ID: 1` header for stable global IDs.

---

## GitHub Actions: Pre-rename Symbol Audit

Run a symbol search in CI before merging a rename PR to ensure all call-sites are updated:

```yaml
# .github/workflows/symbol-audit.yml
name: Pre-rename symbol audit
on:
  pull_request:
    paths:
      - "src/**/*.ts"

jobs:
  audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Check for stale usages of renamed symbol
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          OLD_SYMBOL="handleRequestLegacy"
          REPO="${{ github.repository }}"

          COUNT=$(gh api "search/code?q=symbol:${OLD_SYMBOL}+repo:${REPO}+language:TypeScript" \
            --jq '.total_count')

          if [ "$COUNT" -gt "0" ]; then
            echo "::error::Found $COUNT usage(s) of deprecated symbol '$OLD_SYMBOL'"
            gh api "search/code?q=symbol:${OLD_SYMBOL}+repo:${REPO}+language:TypeScript" \
              --jq '.items[] | "  - " + .path + " (" + .url + ")"'
            exit 1
          fi
          echo "No stale usages found."
```

---

## Anti-patterns

- **Using keyword search as a substitute** — `fetch` as a keyword search returns thousands of
  irrelevant matches (comments, strings, variable names that happen to contain "fetch"). Always
  use `symbol:fetch` for precise results.

- **Querying without a `repo:` or `org:` scope** — public GitHub search is noisy across all repos;
  always scope to your organization.

- **Polling code search from a Worker on every request** — Code Search has a secondary rate limit
  of 10 req/min. Cache results in KV or D1 with a reasonable TTL (e.g., 1 hour).

- **Relying on `total_count` as an exact count** — GitHub may return an approximate count for
  large result sets. Always paginate to get the real number.

- **Ignoring the index lag** — the Kythe index is updated asynchronously after a push. Expect up
  to 30 minutes of lag on a newly pushed branch before symbol changes are reflected.

---

## Gotchas

- **Default branch only** — The precise symbol index covers only the **default branch** of a
  repository. You cannot run a symbol search scoped to a feature branch via the API.

- **Minified / generated files** — Auto-generated `.js` or `.d.ts` files in `dist/` are indexed
  and may inflate result counts. Add `NOT path:dist/` to exclude them.

- **Private repos** — Require a PAT with `repo` scope or a GitHub App token with `contents:read`.
  The `GITHUB_TOKEN` in Actions has sufficient scope for the repo it runs in.

- **Rate limits** — Authenticated: 30 requests/min (REST), secondary limit of 10 code-search
  req/min. Unauthenticated: 10 req/min total. Always send an `Authorization` header.

- **TypeScript generics** — A search for `symbol:Array` will match both your custom `Array`
  utility type and built-in `Array` references. Combine with `path:` filters or review matches.

---

## Verification

```bash
# CLI smoke test — requires gh CLI and repo read access
gh api "search/code?q=symbol:handleRequest+repo:acme-corp/api-gateway+language:TypeScript" \
  --jq '.total_count, (.items[] | .path)'

# Expected: integer count, then a list of file paths
# Zero results means either the symbol doesn't exist on the default branch
# or the index hasn't caught up yet (wait 30 min and retry)
```

---

## Related

- `github-code-scanning-codeql-workers-typescript.md` — static analysis vs. symbol search
- `github-actions-monorepo-affected.md` — affected-package detection
- `github-graphql-api-patterns.md` — GraphQL pagination patterns
- `github-api-rate-limits.md` — rate limit handling

---

## Sources

- https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax
- https://docs.github.com/en/rest/search/search#search-code
- https://github.blog/2023-02-06-the-technology-behind-githubs-new-code-search/
- https://docs.github.com/en/graphql/overview/changelog (Search v2 GraphQL beta)
