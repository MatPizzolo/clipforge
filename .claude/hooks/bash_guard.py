#!/usr/bin/env python3
"""PreToolUse guard for Bash (card 001, action 9; decision log #130).

Blocks what only the owner runs: git writes (commit, push, merge, tag, rebase, reset --hard,
checkout -- ., clean -f), gh merges and repo/secret/variable changes, Modal deploys, app stops,
secret changes and volume deletes, Vercel production deploys and env changes, scripts/deploy.sh
(except --dry-run), and any command that prints a secrets file (.env, web/.env.local, .neon).
Everything else passes; read-only git, scripts/check.sh and scripts/check_scope.py always do.

A crash or unparseable input never blocks: only an explicit match does.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

OWNER = "Give the owner the exact command to run instead (CLAUDE.md, Sessions)."

# Split compound commands into simple ones: ; && || | & newlines, subshells and substitutions.
_SEPARATORS = re.compile(r"&&|\|\||[;|&\n()`]|\$\(")
# A heredoc with a quoted delimiter (<<'EOF', <<"EOF") is literal text, never run: drop its body.
# Unquoted heredocs can expand $(...) and backticks, so their bodies are still checked.
_QUOTED_HEREDOC = re.compile(r"<<-?\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n")


def _strip_quoted_heredocs(command: str) -> str:
    out, pos = [], 0
    while (match := _QUOTED_HEREDOC.search(command, pos)) is not None:
        out.append(command[pos : match.end()])
        end = re.compile(rf"^[ \t]*{re.escape(match.group(2))}[ \t]*$", re.M)
        close = end.search(command, match.end())
        if close is None:  # unterminated: keep the rest, to be safe
            pos = match.end()
            break
        pos = close.end()
    out.append(command[pos:])
    return "".join(out)


_REDIRECT = re.compile(r"(?<![<>])<\s*([^\s<>|;&()]+)")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"sudo", "command", "env", "time", "nohup", "exec", "xargs", "builtin"}
_SHELLS = {"bash", "sh", "zsh", "dash"}

# Commands that print, page or load a file's contents.
_READERS = {
    "cat", "tac", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "ag", "ack",
    "source", ".", "bat", "batcat", "strings", "xxd", "od", "hexdump", "sed", "awk", "gawk",
    "nl", "cut", "sort", "uniq", "base64", "diff", "cmp", "view", "vi", "vim", "nano", "emacs",
    "jq", "column", "paste", "fold", "wc", "tee", "dd", "iconv", "openssl", "gpg", "sha256sum",
    "md5sum", "curl", "scp", "rsync", "nc",
}  # fmt: skip


def _is_secret_path(word: str) -> bool:
    word = word.strip("'\"")
    if "=" in word and not word.startswith(("/", ".")):
        word = word.split("=", 1)[1]  # --file=.env, if=.env
    name = word.rstrip("/").rsplit("/", 1)[-1]
    return name in (".neon", ".env") or (name.startswith(".env.") and name != ".env.example")


def _unwrap(words: list[str]) -> list[str]:
    """Drop env assignments and wrappers: `FOO=1 sudo uv run modal deploy` → modal deploy."""
    while words:
        head = words[0]
        if _ASSIGNMENT.match(head) or head in _WRAPPERS:
            words = words[1:]
        elif head in ("uv", "uvx", "npx", "pnpm", "bunx", "poetry", "pipx"):
            rest = words[1:]
            if rest[:1] in (["run"], ["exec"]) and head in ("uv", "pnpm", "poetry", "pipx"):
                rest = rest[1:]
            while rest and rest[0].startswith("-"):
                # --with pkg / --from pkg take a value
                takes_value = rest[0] in ("--with", "--from", "--python", "-p", "--package")
                rest = rest[2:] if takes_value else rest[1:]
            words = rest
        elif head in ("python", "python3") and words[1:2] == ["-m"]:
            words = words[2:]
        else:
            break
    return words


def _git_problem(args: list[str]) -> str | None:
    # Skip global options: -C <path>, -c <k=v>, --git-dir=..., --no-pager, ...
    while args and args[0].startswith("-"):
        args = args[2:] if args[0] in ("-C", "-c") else args[1:]
    if not args:
        return None
    sub, rest = args[0], args[1:]
    if sub in ("commit", "push", "merge", "rebase"):
        return f"`git {sub}`"
    if sub == "tag" and not (
        not rest or rest[0] in ("-l", "--list", "-n") or rest[0].startswith("-n")
    ):
        return "`git tag`"
    if sub == "reset" and "--hard" in rest:
        return "`git reset --hard`"
    if sub == "checkout" and "--" in rest and rest[rest.index("--") + 1 :] == ["."]:
        return "`git checkout -- .`"
    if sub == "clean" and any(
        a == "--force" or (a.startswith("-") and not a.startswith("--") and "f" in a) for a in rest
    ):
        return "`git clean -f`"
    return None


def _simple_problem(words: list[str], depth: int) -> str | None:
    words = _unwrap(words)
    if not words:
        return None
    cmd, args = words[0].rsplit("/", 1)[-1], words[1:]
    path = words[0]

    if depth < 3:
        if cmd == "eval":
            return command_problem(" ".join(args), depth + 1)
        if cmd in _SHELLS and "-c" in args[:-1]:
            return command_problem(args[args.index("-c") + 1], depth + 1)
    if cmd == "git":
        return _git_problem(args)
    if cmd == "gh":
        if args[:2] == ["pr", "merge"]:
            return "`gh pr merge`"
        if args[:1] in (["repo"], ["secret"], ["variable"]):
            return f"`gh {args[0]}`"
    if cmd == "modal":
        if args[:1] == ["deploy"]:
            return "`modal deploy` (deploys go through scripts/deploy.sh, run by the owner)"
        if args[:2] == ["app", "stop"]:
            return "`modal app stop`"
        if args[:1] == ["secret"]:
            return "`modal secret`"
        if args[:2] in (["volume", "rm"], ["volume", "delete"]):
            return "`modal volume rm`"
    if cmd == "vercel":
        if args[:1] == ["env"]:
            return "`vercel env`"
        if "--prod" in args and (
            not args or args[0] in ("deploy", "--prod") or args[0].startswith("-")
        ):
            return "`vercel deploy --prod`"
    runs_deploy = path.endswith(("scripts/deploy.sh", "scripts/deploy.py")) or (
        cmd.startswith("python") and any(a.endswith("scripts/deploy.py") for a in args)
    )
    if runs_deploy and "--dry-run" not in args:
        return "`scripts/deploy.sh` (only `--dry-run` is allowed in a session)"
    if cmd in _READERS and any(
        _is_secret_path(a) for a in args if not a.startswith("-") or "=" in a
    ):
        return "printing a secrets file (.env, web/.env.local, .neon)"
    return None


def _segments(command: str) -> list[str]:
    """Split into simple commands at separators outside single quotes. Single-quoted text is
    never run by the shell (a `bash -c '...'` body is checked again by the caller); inside double
    quotes `$(...)` and backticks do run, so those still split."""
    segments, current, i = [], [], 0
    in_single = in_double = False
    while i < len(command):
        char = command[i]
        if in_single:
            in_single = char != "'"
        elif char == "\\" and i + 1 < len(command):
            current.append(command[i : i + 2])
            i += 2
            continue
        elif char == "'" and not in_double:
            in_single = True
        elif char == '"':
            in_double = not in_double
        else:
            match = _SEPARATORS.match(command, i)
            if match:
                segments.append("".join(current))
                current = []
                i = match.end()
                continue
        current.append(char)
        i += 1
    segments.append("".join(current))
    return segments


def command_problem(command: str, depth: int = 0) -> str | None:
    """Why `command` is blocked, or None to let it run."""
    command = _strip_quoted_heredocs(command)
    # `< .env` feeds the file to any command.
    if any(_is_secret_path(target) for target in _REDIRECT.findall(command)):
        return "printing a secrets file (.env, web/.env.local, .neon)"
    for segment in _segments(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            words = segment.split()
        problem = _simple_problem(words, depth)
        if problem:
            return problem
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        command = event.get("tool_input", {}).get("command", "")
        problem = command_problem(command) if isinstance(command, str) else None
    except Exception:  # never block on a bug here
        return 0
    if problem is None:
        return 0
    reason = f"Blocked by .claude/hooks/bash_guard.py: {problem} is the owner's. {OWNER}"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
