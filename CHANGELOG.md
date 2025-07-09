# Changelog

<!-- loosely based on https://keepachangelog.com/en/1.0.0/ -->

## Unreleased

## 0.2.1 - 2025-01-09

### Changed

- Patch release to sync PyPI version with git tag (no code changes)

## 0.2.0 - 2025-01-08

### Added

- New unified `ctrl` tool that consolidates start, stop, and restart operations into a single MCP tool
    - `persistproc start`, `persistproc stop`, and `persistproc restart` commands continue to work as aliases
- Support for `--environment` flag in start operations for setting environment variables via JSON

### Changed

- Replace `kill-persistproc` with `shutdown` and demote it from MCP tool to command line command

## 0.1.0 - 2025-07-06

- Initial release of persistproc