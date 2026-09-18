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
