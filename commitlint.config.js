// Conventional commits enforcement. Used by .github/workflows/commitlint.yml.
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "ci",
        "chore",
        "docs",
        "refactor",
        "perf",
        "test",
        "style",
        "build",
        "revert",
      ],
    ],
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],
    "header-max-length": [2, "always", 100],
    "body-max-line-length": [1, "always", 100],
  },
};
