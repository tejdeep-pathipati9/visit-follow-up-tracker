# Remaining work

Decisions behind these items are in the [assumptions log](assumptions-log.md).
Last reviewed: 2026-11-01.

## Open questions

| ID | Question | Ask | Owner |
|---|---|---|---|
| O9 | The brief asks 1.1.0 for "one new rule", and its tests for "a follow-up that breaks two rules"; our flags never combine (A1) and 1.1.0 adds passwords (A18). Is that acceptable? | Instructor | Jihyung |
| O10 | Is A10 right: staff change only their own follow-ups, and only managers create, edit, or import? | Team | Jihyung |

## Whole team

- [ ] Client brief in `docs/`: each section names its researcher and lists its sources
- [ ] Task board (Linear or Planner), shared with Adam, PRs linked
- [ ] Rehearse the presentation (`presentation/index.html`) and the [demo plan](demo-plan.md)
- [ ] Re-create local databases and Docker volumes after the latest schema changes

## Sanket: intake, validation, rules

- [ ] Merge the generator (PR #9) before `feature/duedate`, which updates it
- [ ] Research: users and their terms

## Jihyung: storage, report, interface

- [x] Open a PR for `feature/duedate`
- [ ] Research: how follow-ups are tracked today and where it goes wrong
- [ ] Speed up the report and CSV for very large open lists. With 120,000 visits and about
  150,000 open overdue follow-ups (synthetic stress data), lists and counts take about a
  second, but the report and a full CSV page through every row and take minutes. Real
  records have far fewer open follow-ups.

## Tejdeep: Docker, release, CI, README

- [ ] Release 1.0.0: image tag, Git tag, CHANGELOG entry
- [ ] Release 1.1.0: password sign-in (A18), then image tag, Git tag, CHANGELOG entry; 1.0.0 must still read the database
- [ ] Rollback 1.1.0 → 1.0.0 on the same volume, history intact; then add it to the demo plan
- [ ] README with real command output for build, run, release, rollback, backup
- [ ] Combine the client brief and assumptions log; check every source is listed
- [ ] Research: privacy and care rules, record retention
