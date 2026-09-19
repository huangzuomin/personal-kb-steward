# Pre-merge recovery and configuration review

## PR-01 follow-up

The cleanup CI did not establish recovery safety. A run's `created` array also
contains update operations. Rollback now rejects an entire update-containing run
before any deletion or audit mutation; create-only rollback is unchanged. This
is a safety stop, not an implementation of restoration transactions.

Configuration validation requires exactly the five public entry names. Internal
workflows such as `init_kb` remain declared but are not advertised as user entries.
Runtime paths use resolved path containment, not string-prefix comparisons.

The dry-run CLI tests now create their own temporary source copy, configuration,
and vault. They never use or modify the developer's `config.json`. CI runs the
whole suite before preparing the example configuration, on Ubuntu 3.11/3.12 and
Windows 3.12. Knowledge-page writes preserve the supplied newlines explicitly.

PR changes (including base edits) trigger a fresh workflow. Its checkout step
records and checks the exact merge SHA and both event parent SHAs. Re-running an
old workflow is not validation of a new base. Neither this patch nor CI merges a PR.

Stable object binding and apply-attempt history protection remain in PR-02.

## Committed-diff validation

A bare `git diff --check` inspects uncommitted working-tree changes and is not
proof that an already committed PR is whitespace-clean. CI now fetches full
history and runs `scripts/check_committed_diff.py` with the immutable event SHAs:

- Pull request: check the unique merge-base to the PR head (equivalent to
  `base...head`), then the event base to the actual checked-out merge commit.
  Verify the merge commit's two parents match the event base and head first.
- Push: check the event's complete `before..after` tree difference, not only the
  last commit. For a new ref (`before` is zero), compare the empty tree to `after`.
- Log the checkout, event SHA, parents, merge base and both endpoints of every
  checked range. Git check failures fail the job; valid nonempty changes pass.
- Missing event data, a mismatched checkout, unavailable commits, shallow or
  ambiguous ancestry fail closed. A force push whose old SHA is no longer
  available requires fetching that exact object; there is no HEAD-parent fallback.

This checks the final committed differences, not every intermediate historical
commit or unrelated pre-existing whitespace on the base. Regression tests use
real disposable Git repositories, including committed errors with a clean
working tree, multi-commit pushes, base-only changes and merge-result errors.
