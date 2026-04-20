# Next 100 Steps (9 Phases) — 2026-04-20

## How To Use

- Complete one phase at a time.
- After each phase, run the listed verification checks before starting the next.
- Mark each step complete only when evidence is captured in `C:\kb-search-api\evidence\nine_phase_2026-04-20\`.

## Phase 1 — Governance And Scope Lock (Steps 1-11)

1. Confirm the four mandatory policy files exist.
2. Record SHA256 for each policy file.
3. Write run scope to a phase manifest.
4. Record local date and timezone in the manifest.
5. Record primary repo and history roots.
6. Define no-fabrication verification rules for the run.
7. Define evidence artifact naming pattern.
8. Save phase manifest under evidence folder.
9. Re-open manifest and validate required keys exist.
10. Verify policy hash block has exactly four `OK` entries.
11. Mark Phase 1 complete only after manifest validation passes.

## Phase 2 — Runtime Baseline Refresh (Steps 12-22)

12. Capture full `docker ps` snapshot to file.
13. Count total running containers.
14. Count statuses containing `healthy`.
15. Count statuses containing `unhealthy`.
16. Run endpoint checks for core observability services.
17. Run endpoint checks for KB and automation services.
18. Save endpoint status table with URL, code, and excerpt.
19. Flag endpoints returning non-200 for follow-up.
20. Verify health table has expected number of targets.
21. Verify docker file line count aligns with running count.
22. Mark Phase 2 complete only after both checks pass.

## Phase 3 — Git And Branch Ground Truth (Steps 23-33)

23. Enumerate target repo paths across C:\ and F:\.
24. For each path, detect git or non-git status.
25. Record current branch for git repos.
26. Record `git status --short --branch` output.
27. Record `git remote -v` output.
28. Record last commit tuple (sha/date/author/subject).
29. Save compact summary TSV.
30. Save detailed per-repo report.
31. Validate row count equals planned repo path count.
32. Validate detailed report has one section per path.
33. Mark Phase 3 complete only after row/section checks pass.

## Phase 4 — One-Week Activity Mapping (Steps 34-44)

34. Scan `C:\Users\ajame\.claude\projects\C--` for files updated in 7 days.
35. Count total updated files.
36. Compute extension frequency table.
37. Export top recent files list with sizes and timestamps.
38. Export extension counts file.
39. Export multi-repo recent commits (7-day window).
40. Save summary with all computed totals.
41. Validate extension count sum equals total files updated.
42. Validate recent files export is non-empty.
43. Validate commit export is non-empty.
44. Mark Phase 4 complete only when all validations pass.

## Phase 5 — Referential Validation (Steps 45-55)

45. Parse markdown links from prior master index.
46. Normalize `C:/` and `F:/` targets to filesystem paths.
47. Check existence for each referenced file.
48. Record size and last-write timestamp for each existing target.
49. Save link validation table.
50. Classify key quantitative claims as verified/stale/unverified.
51. Link each classified claim to its evidence artifact.
52. Count missing links.
53. Count stale claims.
54. Validate claim classification row count meets minimum set.
55. Mark Phase 5 complete only after validation checks pass.

## Phase 6 — Documentation Synthesis (Steps 56-67)

56. Draft verified master index refresh document.
57. Include mandatory policy referentials at top.
58. Add nine-phase execution status table.
59. Add corrected weekly activity metrics.
60. Add current runtime snapshot section.
61. Add current repo snapshot section.
62. Add referential validation outcomes.
63. Add links to all phase evidence artifacts.
64. Draft this 100-step phased plan document.
65. Ensure both docs use absolute file links.
66. Ensure unresolved items are clearly labeled pending.
67. Mark Phase 6 complete only after both docs are saved.

## Phase 7 — Documentation Verification (Steps 68-78)

68. Parse links from the new verified master index.
69. Parse links from the new 100-step plan.
70. Validate all generated links resolve to existing files.
71. Generate hash manifest for all newly written docs.
72. Check for stale numeric claims against current evidence files.
73. Confirm phase status table entries map to real artifacts.
74. Confirm no placeholder text remains.
75. Confirm pending phases are explicitly marked pending.
76. Write doc verification summary artifact.
77. Write doc hash manifest artifact.
78. Mark Phase 7 complete only after link/hash checks pass.

## Phase 8 — Commit, Merge, Push (Steps 79-90)

79. Review `git status --short --branch` in `C:\kb-search-api`.
80. Confirm intended file set before staging.
81. Stage verified docs and new evidence artifacts.
82. Create commit with explicit phase completion message.
83. Capture commit SHA and file list.
84. Verify current branch tracking status.
85. Merge working branch into target branch if required.
86. Resolve merge issues only in scope files.
87. Push branch updates to origin.
88. Push target branch updates to origin.
89. Capture post-push `git status` and `git log -1`.
90. Mark Phase 8 complete only after push commands succeed.

## Phase 9 — Final Run Verification And Handoff (Steps 91-100)

91. Re-run runtime snapshot sanity check (`docker ps` count).
92. Re-run repo summary sanity check for primary repos.
93. Verify latest commit SHA exists on pushed branch.
94. Verify working tree is in expected state after push.
95. Record final artifact index for this run.
96. Record remaining blockers with evidence references.
97. Record explicit unverified items (if any).
98. Write concise handoff summary.
99. Include links to master index, 100-step plan, and evidence folder.
100. Mark run complete only after final verification artifact is written.
