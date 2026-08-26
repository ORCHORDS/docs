# Git automatic comment-character policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Automatic commit-message comment characters can avoid template collisions, but tooling that assumes # may parse cleanup, trailers, or generated messages incorrectly.

## When to use

Use when commit templates legitimately contain lines beginning with the conventional comment character.

## Controls

Pin Git in automation, test hooks and editors, preserve trailer parsing, and avoid interpreting comments as authorization metadata.

## Implementation

Set core.commentChar=auto in scoped config, exercise templates and cleanup modes, inspect the final message, and document the selected character behavior.

## Tests

Test templates containing candidate characters, scissors cleanup, hooks, rebases, merge messages, trailers, and older Git clients.

## Gotchas

The chosen character may vary with template content; third-party tools may still hard-code #.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corecommentChar)
