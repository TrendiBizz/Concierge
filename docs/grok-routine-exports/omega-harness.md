# Omega Harness routines (export for Hermes port)

Exported 2026-11-18 12:08 NZDT by Omega Harness, using UpdateRoutine get. Both routines are PAUSED on Grok (Jo paused all Grok routines on 2026-11-17 at 15:01 NZDT) and were not changed. There are no secrets in the prompts. The scripts below reference a filename (admin.key) but contain no key material. The working directory for all of them is /workspace/omega_harness on the box.

## 1. Box restore guard

- id: box-restore-guard
- status: paused
- schedule: `CRON_TZ=Pacific/Auckland 0 8,20 * * *`
- timing: flexible, earlyMinutes 15, lateMinutes 15 (server picked firesAt `46 7,19 * * *`)

Saved prompt (verbatim):

```text
Role: twice-daily box integrity guard for /workspace/omega_harness. Script-only; no browser, no computer use, no connectors.

Input: none beyond the box filesystem and the harness tools.

Steps, in order, from /workspace/omega_harness:
1. Run tools/boot_rehydrate.sh (recreates the out/ symlink to the persistent store, restores data_ro from snapshot blobs, checks out deleted tracked */out/* in worktrees; never overwrites newer files). If out/ is a plain directory, run tools/ensure_live_out.sh instead of recreating it.
2. Run tools/restore_check.sh.
3. If healthy: run `BOX_SNAPSHOT_KEEP=1000 bash tools/box_snapshot.sh`. Never use default rotation (it deletes).
4. If still unhealthy after rehydrate: dry-run tools/restore_from_snapshot.sh only. Do not --apply and do not snapshot over the last good copy.
5. If either script is missing: tar-backup out/ into /workspace/omega_harness_backups (not backup_out.sh) and report that.

Hard stops: never push, deploy, delete, or touch the VPSs. pulled/ is not in snapshots.

Output to Jo in this chat only when: a script failed, rehydrate repaired something after a reset, or the check is still unhealthy (briefly: what vanished, what the dry-run would restore, ask before --apply). When healthy and nothing was repaired: message nobody.
```

## 2. Box boot check

- id: box-boot-check
- status: paused
- schedule: `CRON_TZ=Pacific/Auckland */15 * * * *`
- timing: flexible, earlyMinutes 7, lateMinutes 7 (server picked firesAt `6,21,36,51 * * * *`)

Saved prompt (verbatim):

```text
Catch a box rebuild or silent loss within 15 minutes. Runs around the clock on purpose: the platform rebuilds the box at any hour (e.g. 13:52 NZDT on 19 Oct 2026) and its copy skips out/, build, coverage and /tmp. From /workspace/omega_harness run `bash tools/boot_check.sh` (one JSON line; ~0.25 s).
- Exit 0 (OK): do nothing and send nothing. Stay completely silent.
- Exit 10 (NEW_BOOT) or 20 (DAMAGE): run tools/boot_rehydrate.sh, then tools/restore_check.sh, then tools/restore_from_snapshot.sh in dry-run mode only. Tell Jo once in this chat, briefly: that the box was rebuilt or what is damaged, what rehydrate repaired, and what's still missing that the snapshot could bring back. Use --apply only after Jo says yes. When restore_check is healthy, run `bash tools/boot_check.sh --record` and take a snapshot with `BOX_SNAPSHOT_KEEP=1000 bash tools/box_snapshot.sh`. Never use the default rotation, which deletes old snapshots.
- Exit 2 or a missing script: tell Jo the boot check itself is broken.
Never delete anything, push, deploy, touch the VPSs or use paid keys. Never recreate out/ as a plain directory (use tools/ensure_live_out.sh).
```

## Port note

Both routines are pure shell scripts and need no Grok memory, connectors or browser. The boot check exits 0 silently, so it is cheap to run as a cron or launchd job. The only Grok-specific part is "tell Jo in this chat", which needs a notification channel on Hermes. These scripts act on the box filesystem (/workspace/omega_harness and the persistent store), so they only make sense wherever that box lives.

## Scripts they call (full contents, from /workspace/omega_harness/tools)


### tools/boot_rehydrate.sh

```bash
#!/usr/bin/env bash
# Boot / SessionStart recovery after a box reset that drops out/ and data_ro/.
# see tools/boxsafe.py rehydrate
cd "$(dirname "$0")/.." && exec python3 tools/boxsafe.py rehydrate "$@"

```

### tools/ensure_live_out.sh

```bash
#!/usr/bin/env bash
# Make harness out/ a symlink to the persistent store live/out (source of truth).
cd "$(dirname "$0")/.." && exec python3 tools/boxsafe.py ensure-live "$@"

```

### tools/restore_check.sh

```bash
#!/usr/bin/env bash
# see tools/boxsafe.py
cd "$(dirname "$0")/.." && exec python3 tools/boxsafe.py check "$@"

```

### tools/box_snapshot.sh

```bash
#!/usr/bin/env bash
# see tools/boxsafe.py
cd "$(dirname "$0")/.." && exec python3 tools/boxsafe.py snapshot "$@"

```

### tools/restore_from_snapshot.sh

```bash
#!/usr/bin/env bash
# see tools/boxsafe.py
cd "$(dirname "$0")/.." && exec python3 tools/boxsafe.py restore "$@"

```

### tools/boot_check.sh

```bash
#!/usr/bin/env bash
# see tools/boot_check.py  (exit 0 OK, 10 NEW_BOOT, 20 DAMAGE, 2 error)
cd "$(dirname "$0")/.." && exec python3 tools/boot_check.py "$@"

```

### tools/boxsafe.py

```python
#!/usr/bin/env python3
"""Box restore safety: snapshot / check / restore / rehydrate.  Added 2026-10-17 after the 15:53-15:57 NZDT box restore
dropped every directory named `out` (and harness data_ro/) and broke the llmgate worktree.

  boxsafe.py snapshot            -> STORE/<ts>/ (harness, data_ro blobs, per-worktree patches/untracked/ignored-out,
                                    per-repo bundles of commits not on any remote), SHA256SUMS, manifest.json, rotation
  boxsafe.py check [--accept]    -> compare box to STORE/canary.json; LOUD + exit 1 on loss; update canary only if healthy
  boxsafe.py restore [--snapshot TS] [--apply]   -> dry-run by default; never overwrites existing files
  boxsafe.py ensure-live         -> make harness out/ a symlink to the persistent LIVE/out (source of truth)
  boxsafe.py sync-live           -> copy any local out/ files into LIVE/out (skip >40 MB; never overwrite newer)
  boxsafe.py rehydrate           -> boot recovery: recreate out symlink, restore data_ro from blobs, git-checkout
                                    deleted tracked *out* files in worktrees. Never overwrites a newer file.

Why ensure-live (2026-10-18): Reset Bot's Computer restores a snapshot that skips directories named `out` and
`data_ro`. Detection alone was not enough — work still lived only on box disk. LIVE/out on the persistent store
survives the reset; rehydrate recreates the symlink on boot / SessionStart.

Quiet on success: one summary line. Paths overridable for tests: BOXSAFE_STORE, BOXSAFE_LIVE, BOXSAFE_ROOT, BOXSAFE_HARNESS.
Nothing here touches a VPS, pushes, commits, resets or deletes tracked work.
"""
import os, sys, json, time, hashlib, tarfile, gzip, shutil, subprocess, argparse, io

STORE   = os.environ.get("BOXSAFE_STORE",   "/cursor/stores/store-805fd633-ada0-483b-9914-93d4a439f09c/box_snapshots")
# LIVE holds the durable copy of out/. Parent of box_snapshots by default (same persistent store).
LIVE    = os.environ.get("BOXSAFE_LIVE",    os.path.join(os.path.dirname(STORE.rstrip("/")), "live"))
LIVE_OUT = os.path.join(LIVE, "out")
ROOT    = os.environ.get("BOXSAFE_ROOT",    "/workspace")
HARNESS = os.environ.get("BOXSAFE_HARNESS", "/workspace/omega_harness")
KEEP    = int(os.environ.get("BOX_SNAPSHOT_KEEP", "12"))
FILE_CAP = 50 * 1024**2          # skip single files above this (logged)
LIVE_FILE_CAP = 40 * 1024**2     # FUSE store rejects ~100MB+ writes (Errno 22); keep live files smaller
WT_IGNORED_CAP = 200 * 1024**2   # per-worktree cap for gitignored out/ content
STORE_WARN = 3 * 1024**3
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".mlvenv", ".sshvenv", ".ytv", "omega_harness_backups"}
HARNESS_EXCLUDE_TOP = {
    "data_ro",       # content-addressed blobs instead
    "data_xerj",     # regenerable index; never snapshotted
    "data_xerj_src", # regenerable; admin.key lives here (secret)
    "pulled",        # human-copied VPS/Drive dumps Jo can restore from Mac or Drive; grew past FUSE write limits (2026-10-18)
}

def sh(args, cwd=None, check=False, text=True, timeout=600):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=text, timeout=timeout)
    if check and r.returncode: raise RuntimeError(f"{args}: {r.stderr.strip()[:300]}")
    return r

def sha256(p, bs=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(bs), b""): h.update(b)
    return h.hexdigest()

def du(p):
    t = 0
    for dp, dn, fn in os.walk(p):
        for f in fn:
            try: t += os.lstat(os.path.join(dp, f)).st_size
            except OSError: pass
    return t

# ---------------------------------------------------------------- discovery
def find_worktrees():
    """Every dir under ROOT (depth<=4) holding a .git file or dir. Returns [(path, status, gitdir_or_reason)]."""
    out = []
    def walk(d, depth):
        try: ents = list(os.scandir(d))
        except OSError: return
        names = {e.name for e in ents}
        if ".git" in names:
            g = os.path.join(d, ".git")
            if os.path.isfile(g):
                try: tgt = open(g).read().strip().split("gitdir:", 1)[1].strip()
                except Exception: tgt = "?"
                if not os.path.isdir(tgt): out.append((d, "broken", tgt)); return
            r = sh(["git", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir"])
            out.append((d, "ok", r.stdout.strip()) if r.returncode == 0 else (d, "broken", r.stderr.strip()[:200]))
            return  # don't descend into a worktree
        if depth >= 4: return
        for e in ents:
            if e.is_dir(follow_symlinks=False) and e.name not in SKIP_DIRS:
                walk(e.path, depth + 1)
    walk(ROOT, 0)
    return sorted(out)

def outside_worktrees(wts, root=None):
    """Worktrees registered in any common git dir we know of that live outside ROOT
    (e.g. /tmp/...) or are prunable. Those do not survive a box rebuild."""
    root = os.path.abspath(root or ROOT)
    commons = sorted({info for p, st, info in wts if st == "ok" and info})
    res = []
    for c in commons:
        r = sh(["git", "--git-dir", c, "worktree", "list", "--porcelain"])
        if r.returncode: continue
        cur = None
        for line in r.stdout.splitlines() + [""]:
            if line.startswith("worktree "): cur = {"path": line[9:], "prunable": False, "bare": False}
            elif cur is not None and line.startswith("prunable"): cur["prunable"] = True
            elif cur is not None and line == "bare": cur["bare"] = True
            elif line == "" and cur is not None:
                p = os.path.abspath(cur["path"])
                if not cur["bare"] and (cur["prunable"] or not (p == root or p.startswith(root + os.sep))):
                    why = "prunable (directory gone)" if cur["prunable"] else f"outside {root}"
                    res.append(f"{p} [{why}; registered in {c}]")
                cur = None
    return sorted(set(res))

def wt_name(p): return os.path.relpath(p, ROOT).replace("/", "__")

def git_lines(d, *args, z=False):
    r = sh(["git", "-C", d, *args])
    if r.returncode: return []
    return [x for x in (r.stdout.split("\0") if z else r.stdout.splitlines()) if x]

def is_out_path(rel): return "out" in rel.rstrip("/").split("/")

def harness_files():
    for dp, dn, fn in os.walk(HARNESS):
        rel = os.path.relpath(dp, HARNESS)
        top = rel.split("/")[0]
        if top in HARNESS_EXCLUDE_TOP: dn[:] = []; continue
        dn[:] = [x for x in dn if x != "__pycache__"]
        for f in fn: yield os.path.join(dp, f)

def out_files():
    o = os.path.join(HARNESS, "out")
    if not os.path.isdir(o): return None
    res = []
    for dp, dn, fn in os.walk(o):
        dn[:] = [x for x in dn if x != "__pycache__"]
        res += [os.path.relpath(os.path.join(dp, f), HARNESS) for f in fn]
    return sorted(res)

def data_ro_state():
    d = os.path.join(HARNESS, "data_ro")
    if not os.path.isdir(d): return None
    return {f: sha256(os.path.join(d, f)) for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f))}

def add_files(tf, base, rels, skipped, label, cap_total=None):
    tot = 0
    for rel in rels:
        p = os.path.join(base, rel)
        try: st = os.lstat(p)
        except OSError: continue
        if os.path.isdir(p) and not os.path.islink(p): continue
        if st.st_size > FILE_CAP: skipped.append(f"{label}: {rel} ({st.st_size/1e6:.0f} MB > 50 MB cap)"); continue
        if cap_total and tot + st.st_size > cap_total: skipped.append(f"{label}: {rel} (worktree ignored-out cap 200 MB reached)"); continue
        try: tf.add(p, arcname=rel, recursive=False); tot += st.st_size
        except OSError as e: skipped.append(f"{label}: {rel} ({e})")
    return tot

# ---------------------------------------------------------------- snapshot
def snapshot(a):
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(STORE, exist_ok=True); os.makedirs(os.path.join(STORE, "blobs"), exist_ok=True)
    # NB: the store (FUSE->S3) cannot rename files >~16 MB, so write final names directly and mark completion last.
    tmp = os.path.join(STORE, ts); os.makedirs(os.path.join(tmp, "worktrees")); os.makedirs(os.path.join(tmp, "repos"))
    skipped, man = [], {"ts": ts, "created": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "root": ROOT, "harness": HARNESS,
                        "worktrees": {}, "repos": {}, "data_ro": {}, "broken": []}
    # harness (everything except HARNESS_EXCLUDE_TOP, capped)
    with tarfile.open(os.path.join(tmp, "harness.tgz"), "w:gz") as tf:
        add_files(tf, HARNESS, [os.path.relpath(p, HARNESS) for p in harness_files()], skipped, "harness")
    man["harness_out_files"] = out_files()
    # data_ro: content-addressed blobs (stored once)
    dro = data_ro_state() or {}
    for f, h in dro.items():
        b = os.path.join(STORE, "blobs", h + ".gz")
        if not os.path.exists(b + ".ok"):
            with open(os.path.join(HARNESS, "data_ro", f), "rb") as src, gzip.open(b, "wb", compresslevel=6) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            open(b + ".ok", "w").write(h + "\n")
        man["data_ro"][f] = h
    # worktrees
    commons = {}
    for path, status, info in find_worktrees():
        n = wt_name(path)
        if status != "ok":
            man["broken"].append({"path": path, "gitdir": info}); skipped.append(f"BROKEN worktree {path} -> {info} (not snapshotted by git; fix it)"); continue
        commons.setdefault(info, []).append(path)
        e = {"path": path, "common": info,
             "head": (git_lines(path, "rev-parse", "HEAD") or ["?"])[0],
             "branch": (git_lines(path, "symbolic-ref", "-q", "--short", "HEAD") or [""])[0],
             "deleted": git_lines(path, "ls-files", "--deleted", "-z", z=True)}
        for kind, args in (("unstaged", ["diff", "--binary"]), ("staged", ["diff", "--cached", "--binary"])):
            r = subprocess.run(["git", "-C", path, *args], capture_output=True)
            if r.stdout:
                if len(r.stdout) > FILE_CAP: skipped.append(f"{n}: {kind} patch {len(r.stdout)/1e6:.0f} MB > cap, not saved")
                else:
                    open(os.path.join(tmp, "worktrees", f"{n}.{kind}.patch"), "wb").write(r.stdout); e[kind] = f"worktrees/{n}.{kind}.patch"
        unt = git_lines(path, "ls-files", "--others", "--exclude-standard", "-z", z=True)
        if unt:
            with tarfile.open(os.path.join(tmp, "worktrees", f"{n}.untracked.tgz"), "w:gz") as tf:
                add_files(tf, path, unt, skipped, f"{n} untracked")
            e["untracked"] = f"worktrees/{n}.untracked.tgz"; e["untracked_n"] = len(unt)
        ign = [x for x in git_lines(path, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", z=True) if is_out_path(x)]
        if ign:
            with tarfile.open(os.path.join(tmp, "worktrees", f"{n}.ignored_out.tgz"), "w:gz") as tf:
                add_files(tf, path, ign, skipped, f"{n} ignored-out", WT_IGNORED_CAP)
            e["ignored_out"] = f"worktrees/{n}.ignored_out.tgz"; e["ignored_out_n"] = len(ign)
        man["worktrees"][path] = e
    # repos: refs + bundle of commits on no remote (branches + stash)
    for common, paths in sorted(commons.items()):
        rn = os.path.relpath(os.path.dirname(common) if common.endswith("/.git") else common, ROOT).replace("/", "__")
        g = ["git", "--git-dir", common]
        refs = sh(g + ["for-each-ref", "--format=%(objectname) %(refname)"]).stdout
        open(os.path.join(tmp, "repos", f"{rn}.refs.txt"), "w").write(refs)
        remote = sh(g + ["remote", "get-url", "origin"]).stdout.strip()
        tips = ["--branches"] + (["refs/stash"] if " refs/stash\n" in refs else [])
        cnt = int((sh(g + ["rev-list", "--count", *tips, "--not", "--remotes"]).stdout.strip() or "0"))
        ent = {"common": common, "worktrees": paths, "origin": remote, "unpushed_commits": cnt, "refs": f"repos/{rn}.refs.txt"}
        if cnt:
            bf = os.path.join(tmp, "repos", f"{rn}.bundle")
            r = sh(g + ["bundle", "create", bf, *tips, "--not", "--remotes"])
            if r.returncode == 0 and os.path.exists(bf):
                if os.path.getsize(bf) > 500 * 1024**2: os.remove(bf); skipped.append(f"repo {rn}: bundle > 500 MB, not kept")
                else: ent["bundle"] = f"repos/{rn}.bundle"
            else: skipped.append(f"repo {rn}: bundle failed: {r.stderr.strip()[:200]}")
        man["repos"][common] = ent
    man["skipped"] = skipped
    json.dump(man, open(os.path.join(tmp, "manifest.json"), "w"), indent=1)
    open(os.path.join(tmp, "skipped.txt"), "w").write("\n".join(skipped) + ("\n" if skipped else ""))
    with open(os.path.join(tmp, "SHA256SUMS"), "w") as f:
        for dp, dn, fn in os.walk(tmp):
            for x in sorted(fn):
                if x in ("SHA256SUMS", "COMPLETE"): continue
                p = os.path.join(dp, x); f.write(f"{sha256(p)}  {os.path.relpath(p, tmp)}\n")
    final = tmp; open(os.path.join(final, "COMPLETE"), "w").write(ts + "\n")
    open(os.path.join(STORE, "LATEST"), "w").write(ts + "\n")
    # rotation + blob GC
    allsn = sorted(x for x in os.listdir(STORE) if x[:8].isdigit() and os.path.isdir(os.path.join(STORE, x)))
    for x in allsn:  # drop incomplete (crashed) snapshots
        if x != ts and not os.path.exists(os.path.join(STORE, x, "COMPLETE")): shutil.rmtree(os.path.join(STORE, x), ignore_errors=True)
    snaps = [x for x in allsn if os.path.exists(os.path.join(STORE, x, "COMPLETE"))]
    for old in snaps[:-KEEP]: shutil.rmtree(os.path.join(STORE, old), ignore_errors=True)
    keep_blobs = set()
    for s in snaps[-KEEP:]:
        try: keep_blobs |= set(json.load(open(os.path.join(STORE, s, "manifest.json")))["data_ro"].values())
        except Exception: pass
    for b in os.listdir(os.path.join(STORE, "blobs")):
        h = b.split(".")[0]
        if h not in keep_blobs: os.remove(os.path.join(STORE, "blobs", b))
    snap_sz, store_sz = du(final), du(STORE)
    nb = sum(1 for r in man["repos"].values() if "bundle" in r)
    line = (f"box_snapshot OK {ts} snap={snap_sz/1e6:.1f}MB store={store_sz/1e6:.1f}MB worktrees={len(man['worktrees'])} "
            f"broken={len(man['broken'])} bundles={nb} skipped={len(skipped)} (see {final}/skipped.txt)")
    if store_sz > STORE_WARN: line += f"  !!! STORE OVER {STORE_WARN/1e9:.0f} GB: lower BOX_SNAPSHOT_KEEP"
    print(line)
    return 2 if man["broken"] else 0

# ---------------------------------------------------------------- check
def loud(msgs):
    bar = "!" * 78
    print(bar); print("!!! RESTORE_CHECK FAIL: box state lost or damaged. Do NOT write new work over it."); 
    for m in msgs: print("!!! " + m)
    print(f"!!! Restore plan: bash tools/restore_from_snapshot.sh   (dry-run; add --apply to act)"); print(bar)

def check(a):
    cpath = os.path.join(STORE, "canary.json")
    canary = json.load(open(cpath)) if os.path.exists(cpath) else None
    probs, notes = [], []
    of = out_files(); dro = data_ro_state()
    wts = find_worktrees()
    cur = {"out_files": of, "data_ro": dro, "worktrees": {}}
    for p, st, info in wts:
        cur["worktrees"][p] = {"status": st, "deleted": len(git_lines(p, "ls-files", "--deleted", "-z", z=True)) if st == "ok" else None}
    if of is None: probs.append(f"{HARNESS}/out/ has VANISHED")
    if dro is None: probs.append(f"{HARNESS}/data_ro/ is MISSING")
    for p, w in cur["worktrees"].items():
        if w["status"] != "ok": probs.append(f"BROKEN worktree {p} (.git points at a missing path)")
    if canary:
        if of is not None and canary.get("out_files"):
            miss = sorted(set(canary["out_files"]) - set(of))
            if miss: probs.append(f"{len(miss)} harness out/ file(s) missing, e.g. {', '.join(miss[:5])}")
        if dro is not None and canary.get("data_ro"):
            for f, h in canary["data_ro"].items():
                if f not in dro: probs.append(f"data_ro/{f} MISSING")
                elif dro[f] != h: probs.append(f"data_ro/{f} CHANGED (sha {dro[f][:12]} != {h[:12]})")
        gone = sorted(set(canary["worktrees"]) - set(cur["worktrees"]))
        if gone: probs.append(f"{len(gone)} worktree(s) VANISHED: {', '.join(gone[:8])}")
        for p, w in cur["worktrees"].items():
            base = (canary["worktrees"].get(p) or {}).get("deleted") or 0
            if w["deleted"] is not None and w["deleted"] > base:
                probs.append(f"{p}: {w['deleted']} tracked file(s) show as DELETED (baseline {base})")
    else:
        for p, w in cur["worktrees"].items():
            if w["deleted"]: notes.append(f"baseline: {p} has {w['deleted']} deleted tracked file(s)")
    latest = open(os.path.join(STORE, "LATEST")).read().strip() if os.path.exists(os.path.join(STORE, "LATEST")) else None
    age_h = None
    if latest:
        age_h = (time.time() - time.mktime(time.strptime(latest, "%Y%m%d_%H%M%S"))) / 3600
    for w in outside_worktrees(wts):
        print(f"restore_check WARN worktree will not survive a box rebuild: {w}")
    if probs and not a.accept:
        loud(probs); return 1
    os.makedirs(STORE, exist_ok=True)
    cur["updated"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    json.dump(cur, open(cpath + ".part", "w"), indent=1); os.replace(cpath + ".part", cpath)
    nd = sum(w["deleted"] or 0 for w in cur["worktrees"].values())
    extra = f" ACCEPTED {len(probs)} problem(s) as new baseline" if probs else ""
    snap = f"last_snapshot={latest} ({age_h:.1f}h)" if latest else "last_snapshot=NONE"
    if age_h is not None and age_h > 24: snap += " !!! older than 24h"
    print(f"restore_check OK out_files={len(of or [])} data_ro={'ok' if dro else 'none'} worktrees={len(wts)} broken=0 "
          f"deleted_tracked={nd} {snap}{' baseline created' if not canary else ''}{extra}")
    return 0

# ---------------------------------------------------------------- restore
def restore(a):
    if a.apply and os.environ.get("CLAUDECODE"):
        print("restore_from_snapshot: --apply refused inside Claude Code; a human or the Grok Bot agent must run it."); return 3
    ts = a.snapshot or (open(os.path.join(STORE, "LATEST")).read().strip() if os.path.exists(os.path.join(STORE, "LATEST")) else None)
    if not ts: print("restore_from_snapshot: no snapshot found in " + STORE); return 1
    sd = os.path.join(STORE, ts)
    if not os.path.exists(os.path.join(sd, "COMPLETE")): print(f"!!! snapshot {ts} is incomplete"); return 1
    man = json.load(open(os.path.join(sd, "manifest.json")))
    bad = [l for l in sh(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=sd).stdout.splitlines() if l.strip()]
    if bad: print("!!! snapshot integrity FAILED:\n" + "\n".join(bad)); return 1
    acts, manual = [], []
    mode = "APPLY" if a.apply else "DRY-RUN"
    def act(msg, fn=None):
        acts.append(msg); print(f"[{mode}] {msg}")
        if a.apply and fn: fn()
    def extract_missing(tgz, base, label):
        with tarfile.open(tgz) as tf:
            mem = [m for m in tf.getmembers() if not os.path.lexists(os.path.join(base, m.name))]
            if mem:
                act(f"{label}: restore {len(mem)} missing file(s) into {base} (e.g. {', '.join(m.name for m in mem[:3])})",
                    lambda: (os.makedirs(base, exist_ok=True), tf.extractall(base, members=mem, filter="data")))
    # harness
    extract_missing(os.path.join(sd, "harness.tgz"), man["harness"], "harness")
    # data_ro
    dd = os.path.join(man["harness"], "data_ro")
    for f, h in man["data_ro"].items():
        p = os.path.join(dd, f)
        cur = sha256(p) if os.path.exists(p) else None
        if cur == h: continue
        if not os.path.exists(os.path.join(STORE, "blobs", h + ".gz.ok")): manual.append(f"data_ro/{f}: blob {h[:12]} missing from store"); continue
        def fix(f=f, h=h, p=p, cur=cur):
            if os.path.isdir(dd): os.chmod(dd, 0o755)
            os.makedirs(dd, exist_ok=True)
            if cur: os.chmod(p, 0o644); os.rename(p, p + f".bak_{ts}")
            with gzip.open(os.path.join(STORE, "blobs", h + ".gz"), "rb") as s, open(p + ".part", "wb") as d: shutil.copyfileobj(s, d, 1 << 20)
            assert sha256(p + ".part") == h; os.replace(p + ".part", p); os.chmod(p, 0o444); os.chmod(dd, 0o555)
        act(f"data_ro/{f}: {'replace changed copy (old kept as .bak)' if cur else 'restore missing'} from blob {h[:12]}", fix)
    # worktrees
    for path, e in sorted(man["worktrees"].items()):
        common = e["common"]
        if not os.path.isdir(common):
            manual.append(f"{path}: repo {common} is gone. Re-clone {man['repos'].get(common, {}).get('origin', '?')}, "
                          f"then fetch {sd}/{man['repos'].get(common, {}).get('bundle', '(no bundle)')} and re-run."); continue
        gf = os.path.join(path, ".git")
        if not os.path.lexists(path):
            ref = e["branch"] if e["branch"] else e["head"]
            def add(path=path, common=common, e=e):
                r = sh(["git", "--git-dir", common, "worktree", "add", path, e["branch"]]) if e["branch"] else None
                if not r or r.returncode: sh(["git", "--git-dir", common, "worktree", "add", "--detach", path, e["head"]], check=True)
            act(f"{path}: worktree missing -> git worktree add {path} {ref}", add)
        elif os.path.isfile(gf) and not os.path.isdir(open(gf).read().split("gitdir:", 1)[-1].strip()):
            manual.append(f"{path}: exists but .git is broken. Copy it aside, then `git --git-dir {common} worktree add {path} {e['branch'] or e['head']}` "
                          f"and copy uncommitted files back (this is how llmgate was fixed on 2026-10-17)."); continue
        if a.apply and not os.path.isdir(path): continue
        if os.path.isdir(path):
            now_del = set(git_lines(path, "ls-files", "--deleted", "-z", z=True)) - set(e["deleted"])
            if now_del:
                act(f"{path}: git checkout -- {len(now_del)} tracked file(s) deleted since snapshot (e.g. {', '.join(sorted(now_del)[:3])})",
                    lambda path=path, d=sorted(now_del): sh(["git", "-C", path, "checkout", "--", *d], check=True))
        for k in ("untracked", "ignored_out"):
            if k in e: extract_missing(os.path.join(sd, e[k]), path, f"{path} {k}")
        if "staged" in e or "unstaged" in e:
            head = (git_lines(path, "rev-parse", "HEAD") or ["?"])[0] if os.path.isdir(path) else e["head"]
            dirty = os.path.isdir(path) and (sh(["git", "-C", path, "diff", "--quiet"]).returncode or sh(["git", "-C", path, "diff", "--cached", "--quiet"]).returncode)
            same = os.path.isdir(path) and head == e["head"] and all(
                subprocess.run(["git", "-C", path, *args], capture_output=True).stdout == (open(os.path.join(sd, e[k]), "rb").read() if k in e else b"")
                for k, args in (("unstaged", ["diff", "--binary"]), ("staged", ["diff", "--cached", "--binary"])))
            if same: pass  # uncommitted changes still present, unchanged
            elif head != e["head"] or dirty:
                manual.append(f"{path}: snapshot has uncommitted changes but the worktree now has its own changes or a different HEAD; "
                              f"inspect and apply by hand: {', '.join(os.path.join(sd, e[k]) for k in ('staged', 'unstaged') if k in e)}")
            else:
                def ap(path=path, e=e):
                    if "staged" in e: sh(["git", "-C", path, "apply", "--index", "--binary", os.path.join(sd, e["staged"])], check=True)
                    if "unstaged" in e: sh(["git", "-C", path, "apply", "--binary", os.path.join(sd, e["unstaged"])], check=True)
                act(f"{path}: re-apply uncommitted changes ({', '.join(k for k in ('staged', 'unstaged') if k in e)} patch)", ap)
    # repos: fetch bundles into a side namespace, never touching branches
    for common, r in sorted(man["repos"].items()):
        if "bundle" not in r or not os.path.isdir(common): continue
        b = os.path.join(sd, r["bundle"])
        heads = [l.split()[0] for l in sh(["git", "bundle", "list-heads", b]).stdout.splitlines() if l.strip()]
        missing = [h for h in heads if sh(["git", "--git-dir", common, "cat-file", "-e", h + "^{commit}"]).returncode]
        if missing:
            act(f"{common}: fetch {len(missing)} lost commit tip(s) from bundle into refs/boxsafe/{ts}/*",
                lambda common=common, b=b: sh(["git", "--git-dir", common, "fetch", b, f"refs/*:refs/boxsafe/{ts}/*"], check=True))
    for m in manual: print(f"[MANUAL] {m}")
    print(f"restore_from_snapshot {mode} {ts}: {len(acts)} action(s){' applied' if a.apply else ' would be taken'}, {len(manual)} manual item(s)"
          + ("" if a.apply or not acts else "; re-run with --apply to act"))
    return 0

# ---------------------------------------------------------------- live out + rehydrate (2026-10-18)
def _copy_file_raw(src, dst):
    """Copy bytes only (no utime/chmod). FUSE store rejects utime and large renames."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as a, open(dst, "wb") as b:
        shutil.copyfileobj(a, b, 1 << 20)

def sync_tree_to_live(src_out, dst_out, skipped):
    """Copy files from src_out into dst_out. Skip >LIVE_FILE_CAP. Never overwrite a newer destination."""
    if not os.path.isdir(src_out): return 0, 0
    os.makedirs(dst_out, exist_ok=True)
    copied = same = 0
    for dp, dn, fn in os.walk(src_out):
        rel = os.path.relpath(dp, src_out)
        target = dst_out if rel == "." else os.path.join(dst_out, rel)
        os.makedirs(target, exist_ok=True)
        for f in fn:
            sp = os.path.join(dp, f); tp = os.path.join(target, f)
            try: st = os.lstat(sp)
            except OSError: continue
            if st.st_size > LIVE_FILE_CAP:
                skipped.append(f"live: {os.path.join(rel, f)} ({st.st_size/1e6:.0f} MB > 40 MB cap)"); continue
            if os.path.exists(tp):
                try: dt = os.lstat(tp)
                except OSError: dt = None
                if dt and dt.st_size == st.st_size and dt.st_mtime >= st.st_mtime - 1:
                    same += 1; continue
                if dt and dt.st_mtime > st.st_mtime + 1:
                    continue  # destination newer — keep it
            try: _copy_file_raw(sp, tp); copied += 1
            except OSError as e: skipped.append(f"live: {os.path.join(rel, f)} ({e})")
    return copied, same

def out_is_live_symlink():
    p = os.path.join(HARNESS, "out")
    if not os.path.islink(p): return False
    try: return os.path.realpath(p) == os.path.realpath(LIVE_OUT)
    except OSError: return False

def ensure_live(a):
    """Make harness out/ a symlink to LIVE/out on the persistent store. Seeds LIVE from local out if needed."""
    skipped = []
    local = os.path.join(HARNESS, "out")
    os.makedirs(LIVE_OUT, exist_ok=True)
    # If out is already the right symlink, just sync any stragglers (no-op when identical)
    if out_is_live_symlink():
        # follow symlink: sync would copy live->live; skip
        n = sum(1 for dp, dn, fn in os.walk(LIVE_OUT) for _ in fn)
        print(f"ensure_live OK already_linked live_files={n} path={LIVE_OUT}")
        return 0
    # Seed live from a real local directory (not through an existing wrong symlink)
    if os.path.isdir(local) and not os.path.islink(local):
        copied, same = sync_tree_to_live(local, LIVE_OUT, skipped)
    else:
        copied = same = 0
        if os.path.islink(local):
            # wrong/broken symlink: remove it so we can replace
            try: os.unlink(local)
            except OSError as e: print(f"ensure_live FAIL cannot unlink bad out symlink: {e}"); return 1
        elif os.path.exists(local) and not os.path.isdir(local):
            print(f"ensure_live FAIL {local} exists and is not a directory"); return 1
    # Replace local out with symlink. Keep a one-shot backup aside if it was a real dir.
    if os.path.isdir(local) and not os.path.islink(local):
        bak = local + f".pre_live_{time.strftime('%Y%m%d_%H%M%S')}"
        os.rename(local, bak)
        os.symlink(LIVE_OUT, local)
        # After link works, drop the local backup only if live has at least as many files
        live_n = sum(1 for dp, dn, fn in os.walk(LIVE_OUT) for _ in fn)
        bak_n = sum(1 for dp, dn, fn in os.walk(bak) for _ in fn)
        if live_n >= bak_n:
            shutil.rmtree(bak, ignore_errors=True)
            bak_note = "local_backup_removed"
        else:
            bak_note = f"local_backup_kept={bak} (live {live_n} < bak {bak_n})"
    else:
        os.makedirs(HARNESS, exist_ok=True)
        if os.path.lexists(local): os.unlink(local)
        os.symlink(LIVE_OUT, local)
        bak_note = "symlink_created"
        live_n = sum(1 for dp, dn, fn in os.walk(LIVE_OUT) for _ in fn)
    open(os.path.join(LIVE, "OUT_IS_SOURCE_OF_TRUTH"), "w").write(
        f"harness out/ -> {LIVE_OUT}\ncreated {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
    print(f"ensure_live OK live_files={live_n} copied={copied} same={same} {bak_note} skipped={len(skipped)} live={LIVE_OUT}")
    if skipped: open(os.path.join(LIVE, "skipped.txt"), "w").write("\n".join(skipped) + "\n")
    return 0

def sync_live(a):
    """Push local out/ into LIVE/out. Safe if out is already the live symlink (no-op walk of same tree)."""
    skipped = []
    local = os.path.join(HARNESS, "out")
    if out_is_live_symlink():
        n = sum(1 for dp, dn, fn in os.walk(LIVE_OUT) for _ in fn)
        print(f"sync_live OK already_linked live_files={n} (writes go straight to store)")
        return 0
    if not os.path.isdir(local):
        print("sync_live FAIL no local out/"); return 1
    os.makedirs(LIVE_OUT, exist_ok=True)
    copied, same = sync_tree_to_live(local, LIVE_OUT, skipped)
    print(f"sync_live OK copied={copied} same={same} skipped={len(skipped)} live={LIVE_OUT}")
    return 0

def _restore_data_ro_from_blobs():
    """Materialise data_ro/ from content-addressed blobs. data_ro is too big for LIVE (Errno 22)."""
    dd = os.path.join(HARNESS, "data_ro")
    acts = []
    # Prefer latest COMPLETE snapshot's manifest
    latest = open(os.path.join(STORE, "LATEST")).read().strip() if os.path.exists(os.path.join(STORE, "LATEST")) else None
    man_path = os.path.join(STORE, latest, "manifest.json") if latest else None
    if not (man_path and os.path.exists(man_path)):
        return acts
    man = json.load(open(man_path))
    for f, h in (man.get("data_ro") or {}).items():
        p = os.path.join(dd, f)
        if os.path.exists(p) and sha256(p) == h: continue
        blob = os.path.join(STORE, "blobs", h + ".gz")
        if not os.path.exists(blob + ".ok"):
            acts.append(f"data_ro/{f}: blob missing"); continue
        os.makedirs(dd, exist_ok=True)
        if os.path.exists(p):
            # never overwrite a different newer file blindly — only replace if missing or hash mismatch and blob ok
            pass
        with gzip.open(blob, "rb") as s, open(p + ".part", "wb") as d:
            shutil.copyfileobj(s, d, 1 << 20)
        if sha256(p + ".part") != h:
            os.remove(p + ".part"); acts.append(f"data_ro/{f}: blob hash mismatch"); continue
        os.replace(p + ".part", p)
        try: os.chmod(p, 0o444)
        except OSError: pass
        acts.append(f"data_ro/{f}: restored from blob")
    try: os.chmod(dd, 0o555)
    except OSError: pass
    return acts

def _checkout_deleted_out_files():
    """git checkout -- for tracked files under a path component named out (reset wipes those dirs)."""
    fixed = []
    for path, status, info in find_worktrees():
        if status != "ok": continue
        deleted = git_lines(path, "ls-files", "--deleted", "-z", z=True)
        outs = [d for d in deleted if is_out_path(d)]
        if not outs: continue
        r = sh(["git", "-C", path, "checkout", "--", *outs])
        if r.returncode == 0: fixed.append(f"{path}: {len(outs)} out file(s)")
        else: fixed.append(f"{path}: checkout failed ({r.stderr.strip()[:120]})")
    return fixed

def rehydrate(a):
    """Boot / SessionStart recovery after a box reset that skipped out/ and data_ro/."""
    notes = []
    # 1. out/ symlink to LIVE
    local = os.path.join(HARNESS, "out")
    os.makedirs(LIVE_OUT, exist_ok=True)
    if out_is_live_symlink():
        notes.append("out_symlink=ok")
    elif os.path.islink(local) or not os.path.exists(local):
        if os.path.lexists(local):
            try: os.unlink(local)
            except OSError as e: print(f"rehydrate FAIL unlink out: {e}"); return 1
        os.symlink(LIVE_OUT, local)
        notes.append("out_symlink=recreated")
    elif os.path.isdir(local):
        # Real directory appeared (e.g. something wrote out/ before rehydrate). Merge into LIVE, then replace.
        skipped = []
        sync_tree_to_live(local, LIVE_OUT, skipped)
        bak = local + f".merged_{time.strftime('%Y%m%d_%H%M%S')}"
        os.rename(local, bak)
        os.symlink(LIVE_OUT, local)
        # Keep bak only if it had files live lacks — otherwise remove
        shutil.rmtree(bak, ignore_errors=True)
        notes.append("out_symlink=merged_local_dir")
        if skipped: notes.append(f"sync_skipped={len(skipped)}")
    else:
        print(f"rehydrate FAIL unexpected out path type at {local}"); return 1
    live_n = sum(1 for dp, dn, fn in os.walk(LIVE_OUT) for _ in fn)
    notes.append(f"live_files={live_n}")
    # 2. data_ro from blobs
    dro = os.path.join(HARNESS, "data_ro")
    if not os.path.isdir(dro) or not os.listdir(dro):
        acts = _restore_data_ro_from_blobs()
        notes.append(f"data_ro={len(acts)} action(s)" if acts else "data_ro=no_blobs")
    else:
        notes.append("data_ro=present")
    # 3. Omegaold (and other) worktrees: restore tracked files the reset deleted under */out/*
    fixed = _checkout_deleted_out_files()
    notes.append(f"worktree_out_restored={len(fixed)}")
    print("rehydrate OK " + " ".join(notes))
    return 0

def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("snapshot")
    c = sp.add_parser("check"); c.add_argument("--accept", action="store_true", help="re-baseline the canary even with problems (after a legit deletion)")
    r = sp.add_parser("restore"); r.add_argument("--snapshot"); r.add_argument("--apply", action="store_true")
    sp.add_parser("ensure-live")
    sp.add_parser("sync-live")
    sp.add_parser("rehydrate")
    a = ap.parse_args()
    sys.exit({"snapshot": snapshot, "check": check, "restore": restore,
              "ensure-live": ensure_live, "sync-live": sync_live, "rehydrate": rehydrate}[a.cmd](a))
if __name__ == "__main__": main()

```

### tools/boot_check.py

```python
#!/usr/bin/env python3
"""Fast box-guard check, meant to run every 15 min.

Detects a platform box rebuild (a new boot whose files were re-hydrated from the
platform store, which drops out/, build/, coverage/ dirs and /tmp) and
cheap damage signs. It never restores or deletes anything; it only reports.

  python3 tools/boot_check.py            # check, one JSON line on stdout
  python3 tools/boot_check.py --record   # check; if no DAMAGE, save this boot as the marker

Exit codes: 0 OK, 10 NEW_BOOT (no damage seen), 20 DAMAGE (may also be a new boot,
see "new_boot" in the JSON), 2 usage/internal error.

Boot identity = /proc/sys/kernel/random/boot_id + mtime_ns/size of
/tmp/sand-copy-in.log (rewritten by every box boot's store copy-in).
PID 1 start ticks and btime are reported but NOT compared: PID 1 starts at
~the same tick every boot, and btime drifts when the VM is paused.

Damage = harness out/ symlink missing or its target unreadable, data_ro/ missing,
a worktree from the latest complete snapshot gone, or tracked files deleted
beyond that snapshot's per-worktree baseline.
"""
import os, sys, json, time, argparse, subprocess, threading
from concurrent.futures import ThreadPoolExecutor

STORE   = os.environ.get("BOXSAFE_STORE", "/cursor/stores/store-805fd633-ada0-483b-9914-93d4a439f09c/box_snapshots")
HARNESS = os.environ.get("BOXSAFE_HARNESS", "/workspace/omega_harness")
MARKER  = os.environ.get("BOOTCHECK_MARKER",
                         os.path.join(os.path.dirname(STORE.rstrip("/")), "box_guard", "boot_marker.json"))
BOOT_ID = os.environ.get("BOOTCHECK_BOOT_ID", "/proc/sys/kernel/random/boot_id")
COPYIN  = os.environ.get("BOOTCHECK_COPYIN_LOG", "/tmp/sand-copy-in.log")
OUT_TIMEOUT = float(os.environ.get("BOOTCHECK_OUT_TIMEOUT", "5"))
GIT_TIMEOUT = 20


def _read(p):
    try:
        with open(p) as f: return f.read().strip()
    except OSError: return None


def boot_identity():
    ident = {"boot_id": _read(BOOT_ID), "copyin_mtime_ns": None, "copyin_size": None}
    try:
        st = os.stat(COPYIN); ident["copyin_mtime_ns"] = st.st_mtime_ns; ident["copyin_size"] = st.st_size
    except OSError: pass
    return ident


def boot_info():
    """Informational only (not compared)."""
    info = {}
    s = _read("/proc/1/stat")
    if s:
        try: info["pid1_start_ticks"] = int(s.rsplit(")", 1)[1].split()[19])
        except Exception: pass
    log = _read(COPYIN)
    if log:
        res = [l for l in log.splitlines() if "result outcome=" in l]
        if res: info["copyin_result"] = res[-1][:300]
    return info


def same_boot(a, b):
    keys = ("boot_id", "copyin_mtime_ns", "copyin_size")
    return all(a.get(k) == b.get(k) for k in keys)


def latest_manifest():
    ts = _read(os.path.join(STORE, "LATEST"))
    if not ts: return None, None
    p = os.path.join(STORE, ts, "manifest.json")
    if not os.path.exists(os.path.join(STORE, ts, "COMPLETE")): return ts, None
    try:
        with open(p) as f: return ts, json.load(f)
    except Exception: return ts, None


def check_out():
    """out/ must be a symlink whose target lists within OUT_TIMEOUT (FUSE may hang)."""
    o = os.path.join(HARNESS, "out")
    if not os.path.islink(o):
        return "out/ is not a symlink" if os.path.exists(o) else "out/ symlink MISSING"
    res = {}
    def ls():
        try: res["n"] = len(os.listdir(o))
        except OSError as e: res["err"] = str(e)
    t = threading.Thread(target=ls, daemon=True); t.start(); t.join(OUT_TIMEOUT)
    if t.is_alive(): return f"out/ target {os.readlink(o)} did not answer in {OUT_TIMEOUT:.0f}s"
    if "err" in res: return f"out/ target unreadable: {res['err'][:200]}"
    return None


def deleted_in(path):
    try:
        r = subprocess.run(["git", "-C", path, "ls-files", "--deleted", "-z"],
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "git ls-files timed out"
    if r.returncode: return None, (r.stderr.strip() or "git failed")[:200]
    return sorted(x for x in r.stdout.split("\0") if x), None


def scan_worktrees(man):
    problems, checked = [], 0
    wts = man.get("worktrees", {}) if man else {}
    todo = []
    for p, e in sorted(wts.items()):
        if not os.path.isdir(p): problems.append(f"worktree VANISHED: {p}"); continue
        if not os.path.exists(os.path.join(p, ".git")): problems.append(f"worktree lost .git: {p}"); continue
        todo.append((p, set(e.get("deleted") or [])))
    with ThreadPoolExecutor(max_workers=16) as ex:
        for (p, base), (dl, err) in zip(todo, ex.map(lambda t: deleted_in(t[0]), todo)):
            checked += 1
            if err: problems.append(f"{p}: {err}"); continue
            new = [x for x in dl if x not in base]
            if new:
                problems.append(f"{p}: {len(new)} tracked file(s) DELETED, e.g. {', '.join(new[:3])}")
    return problems, checked


def run(record=False, now=None):
    t0 = time.time()
    ident = boot_identity()
    marker = None
    if os.path.exists(MARKER):
        try:
            with open(MARKER) as f: marker = json.load(f)
        except Exception: marker = None
    new_boot = marker is None or not same_boot(ident, marker.get("identity", {}))
    damage = []
    if not os.path.isdir(os.path.join(HARNESS, "data_ro")): damage.append("data_ro/ MISSING")
    e = check_out()
    if e: damage.append(e)
    snap, man = latest_manifest()
    if man is None: damage.append(f"no readable complete snapshot manifest (LATEST={snap})")
    wd, checked = scan_worktrees(man)
    damage += wd
    status = "DAMAGE" if damage else ("NEW_BOOT" if new_boot else "OK")
    out = {"status": status, "new_boot": new_boot, "damage": damage, "snapshot": snap,
           "worktrees_checked": checked, "identity": ident, "info": boot_info(),
           "marker_boot": (marker or {}).get("recorded"),
           "time": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
    if marker is None: out["note"] = f"no boot marker at {MARKER}"
    if record:
        if damage:
            out["recorded"] = False; out["note"] = "marker NOT updated: damage present"
        else:
            os.makedirs(os.path.dirname(MARKER), exist_ok=True)
            m = {"identity": ident, "info": out["info"], "recorded": out["time"], "snapshot": snap}
            tmp = MARKER + ".part"
            with open(tmp, "w") as f: json.dump(m, f, indent=1)
            os.replace(tmp, MARKER)
            out["recorded"] = True; out["status"] = "OK"
    out["elapsed_s"] = round(time.time() - t0, 3)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--record", action="store_true", help="after a check with no DAMAGE, save this boot as the marker")
    a = ap.parse_args(argv)
    try:
        out = run(record=a.record)
    except Exception as ex:
        print(json.dumps({"status": "ERROR", "error": str(ex)[:300]})); return 2
    print(json.dumps(out, sort_keys=False))
    return {"OK": 0, "NEW_BOOT": 10, "DAMAGE": 20}[out["status"]]


if __name__ == "__main__":
    sys.exit(main())

```
