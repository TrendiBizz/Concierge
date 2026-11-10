# Spec — session auto-end and auto-push

Status: **BUILT 2026-11-10.** Implementation: `scripts/auto-end-session.py`.
Tests: `api/tests/test_auto_end_session.py` (34). Companion to
`HANDOFF_PORTAL_WORKFLOW_2026-11-10.md` §"Open asks from the owner", item 2.

Owner decisions (2026-11-10):

| Decision | Choice |
| --- | --- |
| Auto-end trigger | **Context size threshold** |
| Push preference | **Auto-commit and push to `origin/main`** |
| Build scope | Spec now, implement next session |

## 1. Why this is not a config change

There is no shipped auto-end or auto-push feature. Searched the installed harness
(`@deepseek-ai/dsh@0.2.1-rc.2`): no `autoPush`/`auto-push` symbol exists, and no
`session/end` auto-trigger. This has to be built.

Two things are already handled and must not be rebuilt:

- **Context overflow is already survivable.** `@deepseek-ai/dsh-compaction-basic`
  condenses history near the context limit and retries after a confirmed
  overflow error. It is mounted inside agent presets (`isolate.compaction`), with
  the tool-result pruner at `thresholdChars: 8192`. So "context is large" does not
  currently break anything — it is a *checkpoint* signal, not a failure.
- **Permission default is already fixed** (see §5); this spec is independent of it.

Consequence for the trigger: auto-end on context size is a policy choice about
when a session's *record* should close and be handed off, not a crash workaround.

## 2. Trigger

End the session when context pressure crosses a threshold.

- Signal: the token meter's current usage against the routed model's context
  window — the same measurement compaction already uses. Do **not** re-derive
  tokens by counting characters.
- Read the **`contextPressure`** projection (`pressureTokens` / `contextWindow`).
  Do **not** read the `tokenUsage` projection: that is a lifetime cumulative
  total with `addReplacing` folding, so it counts the whole conversation again on
  every turn and grows roughly quadratically with turn count. The two appear side
  by side in the Web status bar as e.g. `11.3M tok · 29%`, where 11.3M is the
  lifetime total and 29% is the live occupancy. On a 1,048,576-token window,
  11.3M is 1078% — the lifetime figure can never be compared to the window.
  A trigger wired to the lifetime number would fire on turn count by accident,
  which is the trigger the owner explicitly did not choose.
- Default threshold: `0.80` of the window, matching `compaction-basic`'s
  `thresholdRatio`. Expressed as a fraction, not an absolute token count, so it
  survives a model change.
- Fire **once** per session. Ending is idempotent: a second crossing while the
  end sequence is in flight must not start a second commit or push.
- Evaluated at turn boundaries only. Never mid-tool-call — a partial tool
  result must not be committed.

Why not turn count or elapsed time: neither correlates with whether the
conversation still has working room, and elapsed time fires during long
single-task runs where ending is actively harmful.

## 3. End sequence

Order matters. Each step fails closed — do not continue to the next step.

1. **Stop accepting new turns** for this session.
2. **Commit** the workspace: `git add -A` on the tracked worktree, then commit
   with a message naming the session id and the trigger.
3. **Push** to `origin/main`.
4. **Write the handoff** document — same shape as the existing
   `QA/verification/HANDOFF_*.md` files.
5. **Mark the session ended.**

If push is rejected (non-fast-forward), stop and report. Do **not** force-push,
and do **not** rebase automatically: a rejected push means someone else moved
`origin/main` and that decision is the owner's.

## 4. Push safety

Auto-push to `main` is the destructive part of this design. Guardrails:

- **Never** `push --force`, `reset --hard`, or `clean -fd`.
- **Never commit the excluded paths.** Already known-untracked and explicitly
  excluded from commits:
  - `QA/verification/HERMES_*` (4 files)
  - `office-shots/`
  - `tiktok-review/`
  Add these to the ignore list rather than relying on the operator to remember.
- **Refuse to push if the tree contains anything unexpected.** If `git status`
  shows stages beyond the known set, stop and ask. This is the failure mode that
  silently publishes credentials or large binaries.
- **Run the gate before committing:** `pytest api/tests -q`. A red gate must
  block the push, not be noted in the commit message. The current session had
  four tests pass against deliberately broken code — a green suite is evidence
  only if it can fail. The Rust gate was removed on 2026-11-10 when the Rust
  port was abandoned; `concierge-stack/` is reference only.
- **Never `docker cp` into a running container** as part of any verification
  step. Use bind mounts. This contaminated production once already.

## 5. Permission default — DONE (not part of this build)

Recorded here because the handoff left it open and it is now closed.

The handoff's option (b) — "confirm the config key that feeds
`sandboxPolicy.defaultMode`" — was **wrong**: no such key exists in the harness.
The real mechanism is `defaultPreset` on the `permission` loader entry, whose id
is `permission` and whose package is `@deepseek-ai/dsh-permission-presets`.

Applied to `~/.dsh/profiles/web/cordis.patch.yml`:

```yaml
- id: permission
  name: "@deepseek-ai/dsh-permission-presets"
  config:
    defaultPreset: workspace-write
```

Verified:

- `dsh --profile web --dump-config` shows the entry marked
  `patched by /Users/jo/.dsh/profiles/web/cordis.patch.yml` with
  `defaultPreset: workspace-write`; no patch warnings.
- `defaultPreset` is read by `defaultSettings()`, which `pinInitialPermission`
  consults only for a genuinely fresh session
  (`preset === null && sandbox === null && approval === null && !seeded`).
  Seeded or partially initialised sessions keep their own knobs — so this
  changes new sessions only and cannot rewrite existing ones.
- The UI route is equivalent, not different: the General settings row writes
  namespace `permission`, path `["defaultPreset"]`, via
  `remote.settings.mutate`. Same namespace, same key, same entry.
- Backed up first to
  `~/.dsh/profiles/web/cordis.patch.yml.bak-20261110-150553-preperms`.

Takes effect for sessions created **after** the harness restarts with this patch.
Existing sessions, including the long-running one, keep their pinned knobs.

## 6. Open questions for implementation

- **Where does the trigger live?** A DSH plugin, a wrapper script, or an external
  watcher on the session log. The token meter is the honest signal; a plugin gets
  it directly.
- **Restart requirement.** A profile patch is read at boot. Decide whether the
  implementation tolerates requiring a web-profile restart.
- **What does "end" mean for the GUI?** Whether the session closes in the
  sidebar, or is only marked in its log. The owner's phrasing was "end long
  sessions", which implies visible closure.
- **Handoff authorship.** Step 4 needs a model call or a template. A template
  risks producing a stale document that reads as verified; a model call costs a
  request. Prefer the model call, and require it to state what it did **not**
  verify.

## 7. Acceptance

- A session crossing the threshold ends exactly once, with one commit and one
  push.
- The trigger reads `contextPressure`, proven by a test that inflates the
  lifetime `tokenUsage` total without raising occupancy and asserts no end
  fires — and the inverse.
- A red gate blocks the push, and says so.
- The excluded paths never appear in a commit.
- A rejected push stops without force and reports.
- Existing sessions are untouched.

## 8. Build record (2026-11-10)

Implementation `scripts/auto-end-session.py`, tests
`api/tests/test_auto_end_session.py`.

Evidence, all run in this session:

| Check | Result |
| --- | --- |
| New tests | **33 passed** (34 before the Rust-gate test was removed) |
| Full suite | **506 passed** (was 470; +tests for the auto-end, no regressions) |
| Rust gate | removed — Rust port abandoned 2026-11-10 |
| Excluded paths | now `.gitignore`d, not left to operator memory |

Falsification — each guardrail was broken deliberately and the tests confirmed
red, because a test that cannot fail proves nothing:

| Broken | Tests that went red |
| --- | --- |
| `excluded()` returns False | 7 |
| `run_gates()` returns early | 2 |
| Rejected-push check disabled | 1 |

End-to-end against a throwaway repo with a **real bare remote**:

1. Below threshold — no commit, HEAD unchanged.
2. Excluded `HERMES_*` staged — refused, exit 1, HEAD unchanged.
3. Red gate (no tests collected) — refused, **nothing pushed**.
4. Green gate — committed `ffda562` and pushed; remote confirmed at the same
   SHA, `HERMES_*` absent from the remote tree.
5. Remote advanced behind us — push rejected, exit 1, **no force**, the new file
   absent from the remote.

Honest limitation found in case 5: the local commit is created *before* the push
attempt, so a rejected push leaves a local commit that is not on origin. This is
deliberate — the work stays recoverable and nothing false is published — but it
means a rejected push needs a human to reconcile, not an automatic retry. The
tool never retries and never forces.

Not wired to fire automatically: the tool is invoked with an explicit occupancy
reading. Hooking it to a live `agent/turn-stopping` signal is the remaining
integration step and is deliberately left manual until the trigger is observed
on real sessions, since an unattended auto-push to `main` is the destructive
half of this design.
