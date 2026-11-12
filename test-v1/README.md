# test-v1 — sandbox workspace for the proposal-v1 loop

This folder is a throwaway workspace where the whole approve/reject loop runs
end-to-end, locally, with no external IDE assistant required.

Contents:

- `agent.py` — a **simulated coding assistant** (an MCP client). It spawns the
  IDE3 MCP server, calls `capture_intent`, blocks for your decision, and on
  approval writes a stub file into `generated/`.
- `AGENTS.md` — the rules a real assistant must follow in this workspace.
- `.ide3/proposal.json` — created at runtime; the shared review document.
- `generated/` — created at runtime; where approved code lands.

## Run the loop

Prereqs (one-time): the MCP server's venv exists — see
`../src/ide3-mcp/README.md`. Then:

### Option A — with the VS Code panel (the real UX)

1. Open `src/ide3-extension` in VS Code and press **F5**. This launches the
   Extension Development Host already pointed at this `test-v1/` workspace.
2. In a terminal, from the repo root, start the assistant:

   ```bash
   src/ide3-mcp/.venv/bin/python test-v1/agent.py "add a dark mode toggle"
   ```

3. The **IDE3.0** panel (checkmark icon in the activity bar) shows the extracted
   functional requirements and quality constraints as expand/collapse rows.
   Click **Approve** (or **Reject**).
4. On approve, the assistant unblocks and writes `generated/<proposal-id>.py`.

### Option B — headless (no panel)

Run the assistant as above, then in another terminal approve via the store:

```bash
cd src/ide3-mcp
./.venv/bin/python -c "from ide3.persistence import ProposalStore; \
s=ProposalStore('../../test-v1'); p=s.load(); p.approve(); s.save(p)"
```
