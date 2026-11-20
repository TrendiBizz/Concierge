# SESSION HANDOFF 2026-11-18za

## Done this thread (verified by tool output)
- Omega box omega-new (host fxut8777965, SHADOW): omega_config.ini nas_noiseband_shadow_enabled=0, backup omega_config.ini.bak-20261118-noiseband, engine restarted via OMEGA.ps1 restart (startup checks passed, f0ac542, service Running).
- Omegaold repo: same change committed ea8a48b on branch config/noiseband-shadow-off-20261118, pushed (no PR, main untouched).
- Box ledger C:\Omega\logs\trades\omega_trade_closes.csv: 130 -> 111 rows, all shadow=1. Removed 3 non-shadow rows + rows of NasNyPullbackAlwaysShadow, NasNyR6AlwaysShadow, NasNySessionShadow, GoldBear, NasNoiseBandShadow (19 total). Archive on box: logs\trades\archive\omega_trade_closes.pre-clean-20261118.csv; Mac copies in scratchpad arch/ and ~/jo-jobs/. Stray empty dir ~/Memory-Omega/archive (delete if unwanted).
- Move-Item failed ("file already exists"); used Copy-Item -Force over file instead. Use tools/omega_ps.sh (hook blocks nested ssh powershell).

## OPEN OPERATOR ASKS (Jo, verbatim)
"now tell me what Hermes is capable doing that ensures it works like i asked, I also have not seen any postings to the fb and ig pages like i asked"
- Not yet answered: need to inspect hermes/README.md, docs/AGENT_WORKING_ORDER.md, hermes job configs/schedules/skills (container hermes-concierge) and report capabilities from evidence (FACT vs INFERENCE).
- FB/IG: no posts seen. Known: FB/IG source missing (handoff 18m); drafts in commit aca98af and brief d04ca4b (Trendi Desk to produce FB/IG from 16 Nov LinkedIn draft). Find whether any posting job/credentials/API exists; likely drafts only, no publisher. Do NOT post externally without Jo's confirmation.

## Other open
- Weekly-engine-health job 5b254a9a0c94 rerun to regenerate report from cleaned ledger (ask Jo). Box also has omega_trade_closes_ALL.csv, _REAL.csv, daily files untouched.
- ~/jo-brain c94fdd5 unpushed (ask Jo). Brain job can't write /opt/data/jo-brain (read-only mount).
- omega-desk MCP removed; restore from ~/.claude/removed-mcp-2026-11-18.json before next trading session.
- Container /opt/data/claude-jobs/repo = fresh clone Omegaold main e43e175; old at repo.stale-4b4117f. ~/Omegaold dirty, don't touch.
- Omega Boss routines port; context trimming (disable claude.ai connectors) not applied.
- concierge-integration main 0128ce5 pushed; untracked SESSION_HANDOFF files only.
