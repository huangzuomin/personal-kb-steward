"""Retired one-vault migration script. It must never rewrite another user's vault."""


def main() -> int:
    print("This one-off migration has been retired. Use healthcheck for a read-only report; "
          "inspect affected links and prepare reviewed updates instead. No files changed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
