# ii-structure — Use This Before Native Tools

You have `ii-structure` installed. It gives you structural code navigation that uses 3-15x fewer tokens than Read/Grep/Glob for structural questions.

## Rules

1. **ALWAYS run `ii-structure help` at the start of a new project** — it returns your full playbook
2. **ALWAYS run `ii-structure files --summary` before exploring** — it's your project map
3. **Use ii-structure INSTEAD of native tools for these tasks:**

| Task | DON'T do this | DO this instead |
|------|--------------|-----------------|
| Understand a file | `Read entire_file.py` | `ii-structure outline entire_file.py --depth full` |
| Find a definition | `Grep "class MyClass" -r` | `ii-structure locate MyClass` |
| Find all callers | `Grep "my_function" -r` | `ii-structure usages my_function` |
| Read one function | `Read big_file.py` (whole file) | `ii-structure body MyClass/method` |
| Search for something | `Grep "auth" -r` | `ii-structure search auth` |
| Check dependencies | `Read file and scan imports` | `ii-structure imports file.py` |
| Orient to project | `Glob **/*.py` then Read each | `ii-structure files --summary` |

4. **KEEP using native tools for these tasks:**
   - `Glob` — finding files by name pattern
   - `Grep` — searching for string literals, TODOs, comments, regex
   - `Read` — reading specific line ranges you already know
   - `Edit/Write` — modifying files (ii-structure is read-only)

## Key Flags

- `--no-tests` on `usages` — exclude test files when exploring (not when refactoring)
- `--depth full` on `outline` — include methods inside classes
- `--kind class|function|method` on `locate`/`outline` — filter by type
- `--match substring` on `locate` — partial name matching
- `--summary` on `files` — project map with signatures

## Workflow

```
New project → files --summary → pick interesting files → outline → locate/body → usages for impact
```
