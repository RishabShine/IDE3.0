# Coding-assistant rules for IDE3.0 (proposal-v1)

This workspace is governed by the IDE3.0 requirement-capture flow. Any coding
assistant operating here (Cursor, Claude Code, Copilot, or the simulated
`agent.py` in this folder) MUST obey the following:

1. **Capture before code.** When the user requests a feature, you MUST first
   call the `capture_intent(user_query)` tool exposed by the IDE3 MCP server.
   Do not write, edit, or propose any code before doing so.

2. **Wait for the decision.** `capture_intent` blocks until the user reviews the
   extracted requirements in the IDE3.0 panel and approves or rejects them. Do
   not proceed until it returns.

3. **On `approved`.** Implement exactly the approved functional requirements,
   honouring the listed quality constraints — nothing more, nothing less.

4. **On `rejected`.** Do not implement anything. Ask the user how they would
   like to revise the request, then start again at step 1.

The approved/rejected decision and the requirement drafts live in
`.ide3/proposal.json`, written by the panel and the MCP server.
