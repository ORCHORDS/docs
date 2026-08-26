# ansible-idempotency-patterns

**Issue:** Writing idempotent Ansible playbooks that are safe to run repeatedly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Non-idempotent Ansible tasks cause inconsistent state and fail on re-runs. Idempotency means running the playbook ten times produces the same result as running it once.

## Pattern / Solution
Use state-aware modules instead of shell commands:
```yaml
# BAD — not idempotent
- name: Create user
  shell: useradd deploy

# GOOD — idempotent
- name: Create deploy user
  user:
    name: deploy
    state: present
    shell: /bin/bash
    groups: sudo
    append: yes
```

File content management:
```yaml
# BAD
- shell: echo "export PATH=$PATH:/opt/bin" >> /etc/profile

# GOOD — blockinfile adds/updates a marked block
- blockinfile:
    path: /etc/profile
    marker: "# {mark} ANSIBLE MANAGED — deploy PATH"
    block: |
      export PATH=$PATH:/opt/bin
```

Conditional task with register:
```yaml
- name: Check if app is installed
  stat:
    path: /usr/local/bin/myapp
  register: myapp_binary

- name: Install app
  get_url:
    url: "https://releases.myapp.io/v{{ app_version }}/myapp-linux-amd64"
    dest: /usr/local/bin/myapp
    mode: '0755'
  when: not myapp_binary.stat.exists or myapp_binary.stat.checksum != expected_checksum
```

Service management:
```yaml
- name: Ensure nginx is running and enabled
  service:
    name: nginx
    state: started
    enabled: yes
```

Check mode (dry run):
```bash
ansible-playbook playbook.yml --check --diff
```

## Gotchas
- `shell` and `command` modules are never idempotent by default; always add `creates` or `when` guards
- `lineinfile` can match and add the same line multiple times if the regexp is too broad; use `blockinfile` for multi-line content
- `changed_when: false` suppresses false change notifications from read-only commands but masks real changes if misused
- Handler `notify` only fires once per play even if triggered multiple times — safe for service restarts
- `ignore_errors: yes` hides failures silently; use `failed_when` with explicit conditions instead

## Related
- `ansible-vault-secrets.md`
- `deployment-approval-workflow.md`
