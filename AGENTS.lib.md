# Agents

<!-- Note to developers: This file is intended for craft libraries.

     To complete this AGENTS.md file for your library:
     1. Replace instances of "Starbase" and "starbase" with the library name.
     2. Complete the 'TODO' sections.
     3. Rename to AGENTS.md.
     4. Delete AGENTS.app.md.
     5. Delete this comment.

    Some guidelines:
     - Keep it brief. This file will be in the context of every prompt and increases the
       number of reasoning tokens, so it should be as short as possible.
     - Ask the LLM to generate an agents file and ensure your agents file doesn't
       include that information.
         - LLMs (as of 2026) produce agents files that actually hinder performance.
           Instead, an agents file should be instructing things that:
             - couldn't be quickly deduced by a senior developer,
             - are very important, or
             - are often missed by LLMs.
     - Mention specific tooling. For example, mentioning `uv` will dramatically increase
       the odds that the agent will use uv.
    -->

## Overview

`canonical/starbase` is a Python library for (TODO: add an inline explanation of the
library).

## Craft apps and libraries

Starbase is used by craft apps, including but not limited to Charmcraft, Debcraft,
Imagecraft, Rockcraft, and Snapcraft. The source code for these apps is at
https://github.com/canonical/<app-name-in-lowercase>.

Craft apps use starbase in conjunction with the following craft libraries:

| Package             | Role                                                                                          |
| ------------------- | --------------------------------------------------------------------------------------------- |
| `craft-application` | Application framework: CLI lifecycle, configuration, service management, remote build support |
| `craft-archives`    | Repository and package archive management (apt sources, keyrings)                             |
| `craft-cli`         | Terminal output, progress reporting, error formatting                                         |
| `craft-grammar`     | Architecture and platform-conditional YAML in project files                                   |
| `craft-parts`       | Part lifecycle (pull, build, overlay, stage, prime) steps, plugins                            |
| `craft-platforms`   | Platform and architecture abstractions                                                        |
| `craft-providers`   | Build environment manager for LXD and Multipass                                               |
| `craft-store`       | Store API client: upload, release, track management                                           |

The source code for these libraries is at https://github.com/canonical/<library>.

## Development

Starbase uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
make setup          # Install all deps
```

### Running tests

```bash
make test           # Full test suite
make test-fast      # Fast tests only
uv run pytest tests/unit/path/to/test_file.py::test_name  # run a specific test
```

(TODO: delete this section if there are no spread tests)
End-to-end tests (`tests/spread/`) use [spread](https://github.com/canonical/spread/)
and require additional setup to run locally. Spread tests should be run for
comprehensive changes or changes that can't be completely verified with unit and
integration tests. Spread tests are expensive to run, so extend existing tests when
appropriate.

### Formatting and linting

```bash
make format
make lint
```

### Documentation

Documentation uses the [Diátaxis](https://diataxis.fr) framework
and the [Sphinx Stack](https://github.com/canonical/sphinx-stack).
All documentation must follow the [Starcraft style
guide](https://documentation.ubuntu.com/starflow/latest/how-to/starcraft-style-guide/)
and the overall [Canonical style guide](https://documentation.ubuntu.com/style-guide/).

```bash
make setup-docs
make docs
make lint-docs
```

## Practices

- Backward compatibility is a **hard requirement**. Apps using this library must
  continue to build successfully without requiring user modifications. Changes that
  alter behavior, configuration, APIs, defaults, or validation rules must be opt-in.
  When modifying business logic, verify that existing behavior is preserved and explain
  how you verified it.
- Make the smallest safe change necessary to resolve the issue. Avoid unrelated bug
  fixes, opportunistic cleanup, and refactoring unless required. The right amount of
  complexity is the minimum needed for the current task.
- Never speculate about code you haven't inspected.
- Follow the project's existing conventions regarding style, docstrings, logging,
  comments, and testing.
- Comments should explain complex business logic, non-obvious algorithms, regex, and
  other "gotchas". Comments should brief, explain "why" not "how", and be helpful for
  future maintainers.
- Update relevant documentation and release notes to reflect code changes.

## Processes

- If you're contributing to a specific release, target the upstream
  `hotfix/<major.minor>` branch, if it exists. Otherwise, target the `main` branch.
- Commit headers are no more than 80 characters, follow [Conventional
  Commits](https://www.conventionalcommits.org/en/v1.0.0/), and use the following types:
    - ci, build, feat, fix, perf, refactor, style, test, docs, chore
- Always run `make format`, `make lint`, and `make test-fast` before completing your
  work.
