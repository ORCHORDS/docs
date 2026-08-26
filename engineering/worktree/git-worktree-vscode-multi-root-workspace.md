# VS Code Multi-Root Workspace with Git Worktrees

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are using multiple git worktrees (e.g., `main` and `feature/my-feature`) and run into:

- VS Code's Explorer only shows one worktree at a time; switching means closing and reopening a folder
- Extensions (ESLint, TypeScript language server) restart on every folder switch, losing context
- You cannot diff files from the flag-off branch against the flag-on branch directly in the IDE
- Each worktree needs its own terminal with the right CWD, but they all open in the same panel

VS Code's **multi-root workspace** feature solves this: one `.code-workspace` file lists all worktree roots so they appear as separate roots in a single Explorer tree.

---

## Context

A `.code-workspace` file is a JSON document that:
- Lists one or more folder roots
- Carries workspace-scoped settings that override user settings
- Can embed extension recommendations
- Is opened with `code myapp.code-workspace` and persisted by VS Code across sessions

Each root in the workspace gets its own Explorer section, its own Git source-control panel entry, and its own TypeScript server instance. Terminal profiles can be pre-configured to open in the right CWD.

---

## Section 1: Creating the .code-workspace File

```bash
# From the primary worktree root
git worktree add /path/to/project feature/my-feature
git worktree add /path/to/project hotfix/payment-bug
```

```jsonc
// /path/to/project
{
  "folders": [
    {
      "name": "myapp (main)",
      "path": "/path/to/project
    },
    {
      "name": "myapp-feat (feature/my-feature)",
      "path": "/path/to/project
    },
    {
      "name": "myapp-hotfix (hotfix/payment-bug)",
      "path": "/path/to/project
    }
  ],
  "settings": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "esbenp.prettier-vscode",
    "typescript.tsdk": "myapp (main)/node_modules/typescript/lib",
    "eslint.workingDirectories": [
      { "pattern": "/path/to/project }
    ],
    "git.autofetch": true,
    "files.exclude": {
      "**/node_modules": true,
      "**/.wrangler": true
    }
  },
  "extensions": {
    "recommendations": [
      "esbenp.prettier-vscode",
      "dbaeumer.vscode-eslint",
      "ms-vscode.vscode-typescript-next",
      "eamodio.gitlens"
    ]
  }
}
```

```bash
# Open the workspace
code /path/to/project
```

---

## Section 2: Shared Settings and Per-Root Overrides

Settings in the `.code-workspace` file apply workspace-wide. To override a setting for one root only, use a `.vscode/settings.json` inside that worktree's folder.

```jsonc
// /path/to/project
// Overrides for the feature branch worktree only
{
  "editor.rulers": [100],
  "typescript.preferences.importModuleSpecifier": "relative",
  "terminal.integrated.env.linux": {
    "FEATURE_NEW_PAYMENTS": "true",
    "NODE_ENV": "development"
  }
}
```

```jsonc
// /path/to/project
// Overrides for the main (flag-off) worktree
{
  "terminal.integrated.env.linux": {
    "FEATURE_NEW_PAYMENTS": "false",
    "NODE_ENV": "development"
  }
}
```

---

## Section 3: Separate Terminal Profiles Per Worktree

VS Code terminal profiles can be pre-configured to open in a specific worktree CWD. Add these to the workspace-level settings in `.code-workspace`:

```jsonc
// Add inside "settings" in myapp.code-workspace
{
  "terminal.integrated.profiles.linux": {
    "myapp-main": {
      "path": "/bin/bash",
      "args": ["--login"],
      "overrideName": true,
      "icon": "git-branch",
      "env": {
        "INIT_CWD": "/path/to/project
      }
    },
    "myapp-feat": {
      "path": "/bin/bash",
      "args": ["--login"],
      "overrideName": true,
      "icon": "beaker",
      "env": {
        "INIT_CWD": "/path/to/project
      }
    },
    "myapp-hotfix": {
      "path": "/bin/bash",
      "args": ["--login"],
      "overrideName": true,
      "icon": "bug",
      "env": {
        "INIT_CWD": "/path/to/project
      }
    }
  },
  "terminal.integrated.defaultProfile.linux": "myapp-main"
}
```

Then add to `~/.bashrc` or the shell's `rc` file so the terminal cds on start:

```bash
# ~/.bashrc – jump to INIT_CWD when set (VS Code worktree terminals)
if [ -n "$INIT_CWD" ] && [ -d "$INIT_CWD" ]; then
  cd "$INIT_CWD"
fi
```

---

## Section 4: Generating the Workspace File Programmatically

As worktrees are added and removed frequently, automate `.code-workspace` regeneration:

```typescript
// scripts/gen-workspace.ts
// Run with: npx tsx scripts/gen-workspace.ts
import { execSync } from "child_process";
import { writeFileSync } from "fs";
import path from "path";

interface WorktreeEntry {
  path: string;
  branch: string;
}

function listWorktrees(): WorktreeEntry[] {
  const raw = execSync("git worktree list --porcelain", { encoding: "utf8" });
  const entries: WorktreeEntry[] = [];
  let current: Partial<WorktreeEntry> = {};
  for (const line of raw.split("\n")) {
    if (line.startsWith("worktree ")) {
      current = { path: line.slice(9) };
    } else if (line.startsWith("branch refs/heads/")) {
      current.branch = line.slice(18);
    } else if (line === "") {
      if (current.path && current.branch) {
        entries.push(current as WorktreeEntry);
      }
      current = {};
    }
  }
  return entries;
}

function genWorkspace(worktrees: WorktreeEntry[], primaryPath: string): object {
  return {
    folders: worktrees.map((wt) => ({
      name: `${path.basename(wt.path)} (${wt.branch})`,
      path: wt.path,
    })),
    settings: {
      "editor.formatOnSave": true,
      "typescript.tsdk": `${primaryPath}/node_modules/typescript/lib`,
      "git.autofetch": true,
    },
    extensions: {
      recommendations: ["esbenp.prettier-vscode", "dbaeumer.vscode-eslint"],
    },
  };
}

const worktrees = listWorktrees();
const primaryPath = worktrees[0]?.path ?? process.cwd();
const workspace = genWorkspace(worktrees, primaryPath);
const outPath = path.join(primaryPath, "myapp.code-workspace");
writeFileSync(outPath, JSON.stringify(workspace, null, 2) + "\n", "utf8");
console.log(`Written: ${outPath}`);
console.log(`Roots: ${worktrees.map((w) => w.branch).join(", ")}`);
```

```bash
npx tsx scripts/gen-workspace.ts
code myapp.code-workspace
```

---

## Anti-patterns

- **Hardcoding absolute paths in `.code-workspace` and committing it** — paths are machine-specific; add `*.code-workspace` to `.gitignore` or use the generation script above and commit only the script.
- **Setting `typescript.tsdk` to a path in a secondary worktree** — the language server will restart every time that worktree changes branches, causing TypeScript to briefly report errors in other roots.
- **Opening each worktree as a separate VS Code window** — you lose cross-root diffing and extension instances multiply unnecessarily.
- **Using a single `.vscode/settings.json` at the repo root and relying on it for all worktrees** — only the worktree's own `.vscode/` is read; settings do not follow the `.git` directory.

---

## Gotchas

- The Git source-control panel shows one entry per root. If a worktree is on a detached HEAD (e.g., after `git worktree add -d`), VS Code shows it as "Detached" and some GitLens features are limited.
- ESLint's working directory detection may be confused by the multi-root layout. Explicitly setting `eslint.workingDirectories` (as shown in Section 1) resolves most cases.
- The TypeScript language server runs per root by default, which means two instances for two worktrees. On memory-constrained machines, consider setting `"typescript.enablePromptUseWorkspaceTsdk": true` to share one instance.
- Renaming a worktree path (via `git worktree move`) requires regenerating or updating the `.code-workspace` file.

---

## Verification

```bash
# Confirm workspace opens correctly
code myapp.code-workspace
# In VS Code: File > Open Recent should show the workspace
# Explorer should list all three roots

# Confirm TypeScript resolves from the shared tsdk
# In any .ts file, hover a type — status bar should show the typescript version
# from node_modules, not the VS Code bundled one

# Confirm terminal opens in the right CWD
# Open a new terminal using the myapp-feat profile
# pwd should print /path/to/project
```

---

## Related

- `documentation/categories/worktree/git-worktree-feature-flag-parallel-dev.md`
- `documentation/categories/worktree/git-worktree-shared-node-modules-symlink.md`
- `documentation/categories/worktree/git-worktree-git-hooks-isolation.md`

---

## Sources

- https://code.visualstudio.com/docs/editor/multi-root-workspaces
- https://code.visualstudio.com/docs/getstarted/settings
- https://git-scm.com/docs/git-worktree
- https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens
