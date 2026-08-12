#!/usr/bin/env python3
"""Small, liveness-preserving policy hook for wali-0x3.

The policy protects implementation scope and irreversible effects.  It does
not require project-management metadata to be valid before that metadata can
be repaired, and it never turns a PostToolUse warning into an unrecoverable
state.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from wali_work import (
    GOAL_FILE,
    IMPLEMENTATION_AGENT_TYPES,
    PolicyContext,
    PolicyTask,
    SPEC_FILE,
    STATE_DIR,
    WORK_FILE,
    Goal,
    WorkState,
    WorkStateError,
    checkpoint_reasons,
    claimed_policy_task,
    load_goal,
    load_policy_context,
    load_state,
    validate_state,
)


STATE_FILES = {
    GOAL_FILE.as_posix(),
    SPEC_FILE.as_posix(),
    WORK_FILE.as_posix(),
    (STATE_DIR / "handoff.md").as_posix(),
}
CONTROL_PREFIXES = (".claude/", "claude/", ".svn/")
LOCAL_SVN_MUTATIONS = {
    "add",
    "changelist",
    "checkout",
    "cl",
    "co",
    "copy",
    "cp",
    "delete",
    "del",
    "export",
    "merge",
    "mkdir",
    "move",
    "mv",
    "patch",
    "pd",
    "pe",
    "pdel",
    "pedit",
    "propdel",
    "propedit",
    "propset",
    "ps",
    "pset",
    "remove",
    "relocate",
    "ren",
    "rename",
    "resolve",
    "resolved",
    "rm",
    "switch",
    "sw",
    "update",
    "up",
    "upgrade",
}
REMOTE_SVN_MUTATIONS = {
    "ci",
    "commit",
    "import",
    "lock",
    "unlock",
}
SVN_OPERATION_ALIASES = {
    "ci": "commit",
    "cl": "changelist",
    "co": "checkout",
    "cp": "copy",
    "del": "delete",
    "mv": "move",
    "pd": "propdel",
    "pe": "propedit",
    "pdel": "propdel",
    "pedit": "propedit",
    "ps": "propset",
    "pset": "propset",
    "remove": "delete",
    "ren": "move",
    "rename": "move",
    "resolved": "resolve",
    "rm": "delete",
    "sw": "switch",
    "up": "update",
}
SVN_OPTIONS_WITH_VALUES = {
    "--accept",
    "--change",
    "--cl",
    "--changelist",
    "--depth",
    "--diff-cmd",
    "--encoding",
    "--extensions",
    "--file",
    "--message",
    "--native-eol",
    "--revision",
    "--strip",
    "--targets",
    "--with-revprop",
    "-c",
    "-F",
    "-m",
    "-r",
    "-x",
}
READ_ONLY_SVN_OPERATIONS = {
    "annotate",
    "blame",
    "cat",
    "diff",
    "help",
    "info",
    "list",
    "log",
    "mergeinfo",
    "proplist",
    "propget",
    "status",
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    ask: bool = False


def _relative_path(project_root: Path, raw_path: str) -> str | None:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def _scope_matches(path: str, scope: str) -> bool:
    normalized = scope.replace("\\", "/").strip().strip("`")
    if normalized == path:
        return True
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if not any(token in normalized for token in ("*", "?", "[")):
        return path.startswith(normalized.rstrip("/") + "/")
    return fnmatch.fnmatchcase(path, normalized)


def _state_path(project_root: Path, tool_input: dict[str, object]) -> str | None:
    raw = str(
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    return _relative_path(project_root, raw) if raw else None


def _safe_split(command: str) -> list[str] | None:
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _command_segments(command: str) -> tuple[str, ...]:
    raw_segments: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(command):
        character = command[index]
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\" and quote != "'":
            current.append(character)
            escaped = True
        elif quote:
            current.append(character)
            if character == quote:
                quote = ""
        elif character in {"'", '"'}:
            current.append(character)
            quote = character
        elif character == "|" and current and current[-1] == ">":
            current.append(character)
        elif character in {";", "|", "\n"}:
            raw_segments.append("".join(current))
            current = []
            if character == "|" and index + 1 < len(command) and command[index + 1] == "|":
                index += 1
        elif character == "&" and (
            (index + 1 < len(command) and command[index + 1] == "&")
            or not current
            or current[-1] not in {">", "<"}
        ):
            raw_segments.append("".join(current))
            current = []
            if index + 1 < len(command) and command[index + 1] == "&":
                index += 1
        else:
            current.append(character)
        index += 1
    raw_segments.append("".join(current))

    segments: list[str] = []
    for raw_segment in raw_segments:
        segment = raw_segment.strip()
        while segment.startswith(("(", "{")):
            segment = segment[1:].lstrip()
        while segment.endswith((")", "}")):
            segment = segment[:-1].rstrip()
        if segment:
            segments.append(segment)
    expanded: list[str] = []
    for segment in segments:
        arguments = _safe_split(segment)
        visible = _unwrap_arguments(arguments) if arguments else []
        if visible and Path(visible[0]).name.lower() in {"sh", "bash", "zsh", "dash", "ksh"}:
            command_index = next(
                (
                    index + 1
                    for index, item in enumerate(visible[1:], start=1)
                    if item.startswith("-") and "c" in item[1:]
                ),
                None,
            )
            if command_index is not None and command_index < len(visible):
                expanded.extend(_command_segments(visible[command_index]))
                continue
        expanded.append(segment)
    return tuple(expanded)


def _unwrap_arguments(arguments: list[str]) -> list[str]:
    result = list(arguments)
    while result:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", result[0]):
            result = result[1:]
            continue
        program = Path(result[0]).name.lower()
        if program == "command":
            result = result[1:]
            continue
        if program == "env":
            index = 1
            while index < len(result):
                item = result[index]
                if item in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}:
                    index += 2
                elif item.startswith("-") or "=" in item:
                    index += 1
                else:
                    break
            result = result[index:]
            continue
        if program == "sudo":
            index = 1
            while index < len(result):
                item = result[index]
                if item in {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from"}:
                    index += 2
                elif item.startswith("-"):
                    index += 1
                else:
                    break
            result = result[index:]
            continue
        if program in {"time", "nice"}:
            index = 1
            while index < len(result):
                item = result[index]
                if item in {"-f", "--format", "-o", "--output", "-n", "--adjustment"}:
                    index += 2
                elif item.startswith("-"):
                    index += 1
                else:
                    break
            result = result[index:]
            continue
        if program == "nohup":
            result = result[1:]
            continue
        if program in {"timeout", "gtimeout"}:
            index = 1
            while index < len(result):
                item = result[index]
                if item in {"-k", "--kill-after", "-s", "--signal"}:
                    index += 2
                elif item.startswith("-"):
                    index += 1
                else:
                    index += 1  # duration
                    break
            result = result[index:]
            continue
        break
    return result


def _operation_arguments(
    arguments: list[str],
    *,
    options_with_values: set[str],
) -> tuple[str, list[str]]:
    index = 1
    lowered_options = {item.lower() for item in options_with_values}
    while index < len(arguments):
        item = arguments[index]
        lowered = item.lower()
        if item == "--":
            index += 1
            break
        if lowered in lowered_options:
            index += 2
            continue
        if any(lowered.startswith(option + "=") for option in lowered_options):
            index += 1
            continue
        if item.startswith("-"):
            index += 1
            continue
        return lowered, arguments[index + 1 :]
    if index < len(arguments):
        return arguments[index].lower(), arguments[index + 1 :]
    return "", []


def _git_operation(arguments: list[str]) -> tuple[str, list[str]]:
    return _operation_arguments(
        arguments,
        options_with_values={"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env"},
    )


def _svn_operation(arguments: list[str]) -> tuple[str, list[str]]:
    return _operation_arguments(
        arguments,
        options_with_values={"--username", "--password", "--config-dir", "--config-option"},
    )


def _canonical_svn_operation(operation: str) -> str:
    aliases = {
        "?": "help",
        "ann": "annotate",
        "di": "diff",
        "h": "help",
        "ls": "list",
        "pget": "propget",
        "pg": "propget",
        "plist": "proplist",
        "pl": "proplist",
        "praise": "blame",
        "stat": "status",
        "st": "status",
        **SVN_OPERATION_ALIASES,
    }
    return aliases.get(operation, operation)


def _svn_operands(arguments: list[str]) -> tuple[str, list[str]]:
    operation, remaining = _svn_operation(arguments)
    operands = _positional_arguments(
        remaining,
        options_with_values=SVN_OPTIONS_WITH_VALUES,
    )
    if (
        _canonical_svn_operation(operation) == "propset"
        and _option_value(remaining, {"-F", "--file"}) is not None
        and operands
    ):
        operands.insert(1, "<property-file-value>")
    return operation, operands


def _is_svn_repository_target(value: str) -> bool:
    return value.startswith("^/") or bool(
        re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value)
    )


def _svn_operand_has_peg_revision(value: str) -> bool:
    _path, separator, revision = value.rpartition("@")
    return bool(separator and revision)


def _svn_local_target_operands(
    operation: str,
    operands: list[str],
    arguments: list[str],
) -> list[str]:
    canonical = _canonical_svn_operation(operation)
    if canonical == "patch":
        candidates = operands[1:2] if len(operands) > 1 else ["."]
    elif canonical == "merge":
        has_repository_source = any(
            _is_svn_repository_target(item) for item in operands
        )
        local_operands = [item for item in operands if not _is_svn_repository_target(item)]
        if _svn_has_revision_selector(arguments):
            # Cherry-pick form: SOURCE [TARGET_WCPATH].  With one operand the
            # target is the current working copy, not the source path.
            candidates = operands[-1:] if len(operands) >= 2 else ["."]
        elif len(operands) == 2 and all(
            _svn_operand_has_peg_revision(item) for item in operands
        ):
            # Two explicitly pegged operands select the two-source form, even
            # when one is a repository URL; without TARGET_WCPATH SVN writes
            # to the current working copy.
            candidates = ["."]
        elif has_repository_source:
            candidates = local_operands[-1:] if local_operands else ["."]
        elif len(operands) >= 3:
            candidates = operands[-1:]
        elif len(operands) == 2:
            # Automatic merge form: SOURCE [TARGET_WCPATH].  Local two-source
            # merges require explicit peg revisions, handled by the branch above.
            candidates = operands[-1:]
        else:
            candidates = ["."]
    elif canonical == "switch":
        relocating = (
            len(operands) > 1
            and _is_svn_repository_target(operands[0])
            and _is_svn_repository_target(operands[1])
        )
        if relocating:
            candidates = operands[2:3] or ["."]
        else:
            candidates = operands[1:2] if len(operands) > 1 else ["."]
    elif canonical in {"checkout", "export"}:
        candidates = operands[-1:] if len(operands) > 1 else []
    elif canonical == "changelist":
        candidates = operands[1:]
    elif canonical == "relocate":
        candidates = operands[2:] or ["."]
    elif canonical == "propset":
        candidates = operands[2:]
    elif canonical in {"propdel", "propedit"}:
        candidates = operands[1:]
    elif canonical == "copy":
        candidates = operands[-1:]
    elif canonical == "move":
        candidates = operands
    elif canonical in {"update", "upgrade"}:
        candidates = operands or ["."]
    else:
        candidates = operands
    return [item for item in candidates if not _is_svn_repository_target(item)]


def _svn_has_revision_selector(arguments: list[str]) -> bool:
    return any(
        item in {"-c", "--change", "-r", "--revision"}
        or item.startswith(("--change=", "--revision="))
        or (item.startswith("-c") and len(item) > 2)
        or (item.startswith("-r") and len(item) > 2)
        for item in arguments[1:]
    )


def _implementation_agent_svn_violation(command: str) -> bool:
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        visible = _unwrap_arguments(arguments)
        if not visible or Path(visible[0]).name.lower() != "svn":
            continue
        operation, _remaining = _svn_operation(visible)
        if not operation:
            if any(
                item.lower() in {"--help", "--version", "-h"}
                for item in visible[1:]
            ):
                continue
            return True
        if _canonical_svn_operation(operation) not in READ_ONLY_SVN_OPERATIONS:
            return True
    return False


def _svn_writes_repository(arguments: list[str]) -> bool:
    operation, operands = _svn_operands(arguments)
    canonical = _canonical_svn_operation(operation)
    if operation in REMOTE_SVN_MUTATIONS or canonical in REMOTE_SVN_MUTATIONS:
        return True
    if canonical in {"propset", "propdel", "propedit"} and any(
        item.lower() == "--revprop" for item in arguments
    ):
        return True
    if canonical in {"copy", "move"}:
        return bool(operands and _is_svn_repository_target(operands[-1]))
    if canonical == "propset":
        targets = operands[2:]
    elif canonical in {"propdel", "propedit"}:
        targets = operands[1:]
    elif canonical in {"delete", "mkdir"}:
        targets = operands
    else:
        targets = []
    return any(_is_svn_repository_target(item) for item in targets)


def _dangerous_local_command(command: str) -> bool:
    compact = re.sub(r"\s+", " ", command.strip().lower())
    patterns = (
        r"(?:^|[;&|]\s*)rm\s+[^\n]*(?:-rf|-fr)",
        r"(?:^|[;&|]\s*)git\s+reset\s+--hard(?:\s|$)",
        r"(?:^|[;&|]\s*)git\s+clean\s+[^\n]*-[^\s]*f",
        r"(?:^|[;&|]\s*)svn\s+revert(?:\s|$)",
        r"(?:^|[;&|]\s*)svn\s+cleanup\b[^\n]*(?:--remove-unversioned|--remove-ignored)",
    )
    if any(re.search(pattern, compact) for pattern in patterns):
        return True
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        arguments = _unwrap_arguments(arguments)
        if not arguments:
            continue
        program = Path(arguments[0]).name.lower()
        if program == "rm":
            flags = "".join(
                item[1:]
                for item in arguments[1:]
                if item.startswith("-") and not item.startswith("--")
            ).lower()
            long_flags = {item.lower() for item in arguments[1:] if item.startswith("--")}
            if ("r" in flags or "--recursive" in long_flags) and (
                "f" in flags or "--force" in long_flags
            ):
                return True
        if program == "git":
            operation, remaining = _git_operation(arguments)
            if operation == "reset" and "--hard" in {item.lower() for item in remaining}:
                return True
            if operation == "clean" and any(
                item.startswith("-") and "f" in item.lower() for item in remaining
            ):
                return True
            if operation == "switch" or (operation == "checkout" and "--" not in remaining):
                return True
        if program == "svn":
            operation, remaining = _svn_operation(arguments)
            if operation == "revert":
                return True
            if operation == "cleanup" and any(
                item.lower() in {"--remove-unversioned", "--remove-ignored"}
                for item in remaining
            ):
                return True
    return False


def _external_write(command: str) -> bool:
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        arguments = _unwrap_arguments(arguments)
        if not arguments:
            continue
        program = Path(arguments[0]).name.lower()
        if program in {"ssh", "scp", "sftp", "ftp"}:
            return True
        if program == "git":
            operation, _remaining = _git_operation(arguments)
            if operation in {"push", "send-email"}:
                return True
        if program == "svn":
            if _svn_writes_repository(arguments):
                return True
        lowered = [argument.lower() for argument in arguments[1:]]
        if program in {"npm", "pnpm", "yarn"} and "publish" in lowered:
            return True
        if program == "docker":
            operation, _remaining = _operation_arguments(
                arguments,
                options_with_values={"--context", "--host", "-H", "--config", "--log-level"},
            )
            if operation == "push":
                return True
        if program == "kubectl":
            operation, _remaining = _operation_arguments(
                arguments,
                options_with_values={
                    "--context",
                    "--namespace",
                    "-n",
                    "--kubeconfig",
                    "--cluster",
                    "--user",
                    "--server",
                    "--token",
                    "--request-timeout",
                    "-v",
                    "--v",
                    "--as",
                    "--as-group",
                    "--as-uid",
                },
            )
            if operation in {
                "apply",
                "create",
                "delete",
                "patch",
                "replace",
                "rollout",
                "scale",
                "set",
            }:
                return True
        if program == "curl":
            for original, item in zip(arguments[1:], lowered):
                if (
                    item
                    in {
                        "-d",
                        "--data",
                        "--data-raw",
                        "--data-binary",
                        "--data-urlencode",
                        "--form",
                        "-t",
                        "--upload-file",
                        "--json",
                    }
                    or item.startswith(
                        (
                            "-d",
                            "--data=",
                            "--data-raw=",
                            "--data-binary=",
                            "--data-urlencode=",
                            "--form=",
                            "-t",
                            "--upload-file=",
                            "--json=",
                        )
                    )
                    or original.startswith("-F")
                ):
                    return True
            for index, original in enumerate(arguments[1:]):
                if original in {"-X", "--request"} and index + 1 < len(lowered):
                    return lowered[index + 1] not in {"get", "head", "options"}
                if original.startswith("-X") and len(original) > 2:
                    return original[2:].lower() not in {"get", "head", "options"}
                if original.lower().startswith("--request="):
                    return original.split("=", 1)[1].lower() not in {"get", "head", "options"}
    return False


def _redirection_targets(segment: str) -> tuple[str, ...]:
    try:
        lexer = shlex.shlex(segment, posix=True, punctuation_chars="<>|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return ()
    targets: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        if token.startswith(">") and not token.startswith(">>>"):
            target = tokens[index + 1]
            if not re.fullmatch(r"&(?:\d+|-)", target):
                targets.append(target)
    return tuple(targets)


def _positional_arguments(
    arguments: list[str],
    *,
    options_with_values: set[str] | None = None,
) -> list[str]:
    result: list[str] = []
    value_options = {item.lower() for item in (options_with_values or set())}
    index = 0
    while index < len(arguments):
        item = arguments[index]
        lowered = item.lower()
        if item == "--":
            result.extend(arguments[index + 1 :])
            break
        if lowered in value_options:
            index += 2
            continue
        if any(lowered.startswith(option + "=") for option in value_options):
            index += 1
            continue
        if not item.startswith("-"):
            result.append(item)
        index += 1
    return result


def _option_value(arguments: list[str], options: set[str]) -> str | None:
    for index, item in enumerate(arguments):
        lowered = item.lower()
        for option in options:
            normalized = option.lower()
            if lowered == normalized and index + 1 < len(arguments):
                return arguments[index + 1]
            if lowered.startswith(normalized + "="):
                return item.split("=", 1)[1]
            if len(option) == 2 and lowered.startswith(normalized) and len(item) > 2:
                return item[2:]
    return None


def _in_place_script_targets(program: str, arguments: list[str]) -> tuple[str, ...]:
    in_place = False
    script_from_option = False
    positional: list[str] = []
    index = 0
    script_options = {"-e", "--expression", "-f", "--file"} if program == "sed" else {"-e", "-E"}
    while index < len(arguments):
        item = arguments[index]
        lowered = item.lower()
        if item == "--":
            positional.extend(arguments[index + 1 :])
            break
        if lowered in {option.lower() for option in script_options}:
            script_from_option = True
            index += 2
            continue
        if any(lowered.startswith(option.lower() + "=") for option in script_options):
            script_from_option = True
            index += 1
            continue
        if lowered in {"-i", "--in-place"} or lowered.startswith(("-i", "--in-place=")) or (
            program == "perl" and item.startswith("-") and "i" in item[1:]
        ):
            in_place = True
            if lowered == "-i" and index + 1 < len(arguments) and arguments[index + 1] == "":
                index += 2
                continue
            index += 1
            continue
        if item.startswith("-"):
            index += 1
            continue
        positional.append(item)
        index += 1
    if not in_place:
        return ()
    files = positional if script_from_option else positional[1:]
    return tuple(files)


def _explicit_file_targets(command: str) -> tuple[str, ...]:
    targets: list[str] = []
    for segment in _command_segments(command):
        targets.extend(_redirection_targets(segment))
        arguments = _safe_split(segment)
        if not arguments:
            continue
        arguments = _unwrap_arguments(arguments)
        if not arguments:
            continue
        program = Path(arguments[0]).name.lower()
        option_values = {
            "touch": {"-d", "--date", "-t", "-r", "--reference", "--time"},
            "mkdir": {"-m", "--mode"},
            "truncate": {"-s", "--size", "-r", "--reference", "-o", "--io-blocks"},
            "cp": {"-t", "--target-directory", "-S", "--suffix"},
            "install": {"-m", "--mode", "-o", "--owner", "-g", "--group", "-t", "--target-directory"},
            "ln": {"-t", "--target-directory", "-S", "--suffix"},
            "mv": {"-t", "--target-directory", "-S", "--suffix"},
        }
        positional = _positional_arguments(
            arguments[1:],
            options_with_values=option_values.get(program),
        )
        if program in {"touch", "mkdir", "rmdir", "rm", "unlink", "truncate", "tee"}:
            targets.extend(positional)
        elif program in {"cp", "install", "ln", "mv"}:
            target_directory = _option_value(
                arguments[1:],
                {"-t", "--target-directory"},
            )
            if target_directory:
                destinations = [
                    (Path(target_directory) / Path(source).name).as_posix()
                    for source in positional
                ]
                if program == "mv":
                    targets.extend(positional)
                targets.extend(destinations or [target_directory])
            elif positional:
                if program == "mv":
                    targets.extend(positional)
                else:
                    targets.append(positional[-1])
        elif program in {"sed", "perl"}:
            targets.extend(_in_place_script_targets(program, arguments[1:]))
        elif program == "git":
            operation, remaining = _git_operation(arguments)
            if operation == "restore":
                targets.extend(
                    _positional_arguments(
                        remaining,
                        options_with_values={"--source", "-s"},
                    )
                )
            elif operation == "checkout" and "--" in remaining:
                targets.extend(remaining[remaining.index("--") + 1 :])
    return tuple(dict.fromkeys(targets))


def _svn_local_mutations(
    project_root: Path,
    command: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    mutations: list[tuple[str, tuple[str, ...]]] = []
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        arguments = _unwrap_arguments(arguments)
        if not arguments or Path(arguments[0]).name.lower() != "svn":
            continue
        operation, operands = _svn_operands(arguments)
        if operation not in LOCAL_SVN_MUTATIONS:
            continue
        targets: list[str] = []
        for argument in _svn_local_target_operands(operation, operands, arguments):
            relative = _relative_path(project_root, argument)
            if relative is None:
                targets = []
                break
            targets.append(relative)
        mutations.append((operation, tuple(targets)))
    return tuple(mutations)


def _has_svn_mutation(command: str) -> bool:
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        arguments = _unwrap_arguments(arguments)
        if not arguments or Path(arguments[0]).name.lower() != "svn":
            continue
        operation, _targets = _svn_operation(arguments)
        if operation in LOCAL_SVN_MUTATIONS | REMOTE_SVN_MUTATIONS:
            return True
    return False


def _project_state(project_root: Path) -> tuple[Goal | None, WorkState | None, list[str]]:
    try:
        goal_text = (project_root / GOAL_FILE).read_text(encoding="utf-8")
        goal = load_goal(project_root, text=goal_text)
    except (OSError, WorkStateError) as error:
        return None, None, [str(error)]
    try:
        state = load_state(project_root, goal_text=goal_text)
    except WorkStateError as error:
        return goal, None, [str(error)]
    return goal, state, validate_state(state)


def _catastrophic_local_command(project_root: Path, command: str) -> bool:
    protected = {Path("/").resolve(), Path.home().resolve(), project_root.resolve()}
    protected.update(project_root.resolve().parents)
    for raw_target in _explicit_file_targets(command):
        if raw_target in {"~", "$HOME", "${HOME}"}:
            return True
        try:
            expanded = os.path.expandvars(
                raw_target.replace("${CLAUDE_PROJECT_DIR}", str(project_root)).replace(
                    "$CLAUDE_PROJECT_DIR", str(project_root)
                )
            )
            wildcard_indexes = [
                expanded.index(token)
                for token in ("*", "?", "[")
                if token in expanded
            ]
            if wildcard_indexes:
                prefix = expanded[: min(wildcard_indexes)].rstrip("/") or "."
                wildcard_root = Path(prefix).expanduser()
                if not wildcard_root.is_absolute():
                    wildcard_root = project_root / wildcard_root
                if wildcard_root.resolve() in protected:
                    return True
            target = Path(expanded).expanduser()
            if not target.is_absolute():
                target = project_root / target
            if target.resolve() in protected:
                return True
        except OSError:
            continue
    return False


def _agent_identity(payload: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(payload.get("session_id", "")),
        str(payload.get("agent_id", "")),
        str(payload.get("agent_type", "")),
    )


def _is_restricted_agent(payload: dict[str, object]) -> bool:
    """Return true for child agents and directly launched implementation roles."""

    _session_id, agent_id, agent_type = _agent_identity(payload)
    return bool(agent_id) or agent_type in IMPLEMENTATION_AGENT_TYPES


def _clears_agent_claims(command: str) -> bool:
    if re.search(r"\bclear_agent_claims\b", command):
        return True
    for segment in _command_segments(command):
        arguments = _safe_split(segment)
        if not arguments:
            continue
        visible = _unwrap_arguments(arguments)
        lowered = [item.lower() for item in visible]
        script_indexes = [
            index
            for index, item in enumerate(visible)
            if Path(item).name.lower() == "wali_work.py"
        ]
        module_indexes = [
            index
            for index, item in enumerate(lowered[:-1])
            if item == "-m" and lowered[index + 1] in {"wali_work", "wali_work.py"}
        ]
        start_indexes = script_indexes + module_indexes
        if any("clear-claims" in lowered[index + 1 :] for index in start_indexes):
            return True
    return False


def _task_for_action(
    project_root: Path,
    context: PolicyContext,
    payload: dict[str, object],
) -> PolicyTask | None:
    session_id, agent_id, agent_type = _agent_identity(payload)
    if agent_type in IMPLEMENTATION_AGENT_TYPES and not agent_id:
        return None
    if agent_id:
        return claimed_policy_task(
            project_root,
            context,
            session_id=session_id,
            agent_id=agent_id,
            agent_type=agent_type,
        )
    return context.task


def _decide_bash(
    project_root: Path,
    command: str,
    payload: dict[str, object],
) -> Decision:
    if not command.strip():
        return Decision(False, "Bash 命令不能为空")
    _session_id, agent_id, agent_type = _agent_identity(payload)
    if agent_type in IMPLEMENTATION_AGENT_TYPES and not agent_id:
        return Decision(
            False,
            "直接启动的实现 Agent 没有 Task claim，不能执行 Bash；请由 wali-0x3 分派",
        )
    restricted_agent = _is_restricted_agent(payload)
    if _clears_agent_claims(command) and restricted_agent:
        return Decision(False, "实现 Agent 不能清理 Task claim；请返回 wali-0x3")
    if restricted_agent and _implementation_agent_svn_violation(command):
        return Decision(
            False,
            "实现 Agent 只执行明确只读的 SVN 命令；其他 SVN 调度请返回 Coordinator",
        )
    dangerous_local = _dangerous_local_command(command)
    if dangerous_local:
        if _catastrophic_local_command(project_root, command):
            return Decision(False, "命令可能删除项目根、主目录或系统根，已拒绝")
        if restricted_agent:
            return Decision(False, "Subagent 不执行破坏性工作区操作；请返回 Coordinator")
    external_write = _external_write(command)
    svn_mutations = _svn_local_mutations(project_root, command)
    has_svn_mutation = _has_svn_mutation(command)
    file_targets = _explicit_file_targets(command)
    if (
        not dangerous_local
        and not external_write
        and not has_svn_mutation
        and not file_targets
    ):
        # Common local commands do not depend on project-management state.
        return Decision(True)
    confirmation_reasons: list[str] = []
    if dangerous_local:
        confirmation_reasons.append("命令包含可恢复但高风险的本地操作")
    implementation_targets: list[str] = []
    for raw_target in file_targets:
        if raw_target == "/dev/null":
            continue
        relative = _relative_path(project_root, raw_target)
        if relative is None:
            if restricted_agent:
                return Decision(False, "Subagent 的显式文件写入必须位于已认领 Task Scope；请返回 Coordinator")
            confirmation_reasons.append("显式文件写入目标位于项目外")
            continue
        if relative in STATE_FILES:
            if restricted_agent:
                return Decision(False, "Subagent 不能修改治理文件；请返回 Coordinator")
            continue
        if relative == "CLAUDE.md" or relative.startswith(CONTROL_PREFIXES):
            if restricted_agent:
                return Decision(False, f"Subagent 不能修改控制面 {relative}；请返回 Coordinator")
            confirmation_reasons.append(f"命令会修改 wali-0x3 控制面 {relative}")
            continue
        implementation_targets.append(relative)
    if has_svn_mutation and restricted_agent:
        return Decision(False, "Subagent 不执行 SVN 调度；请返回 Coordinator 串行处理")
    if svn_mutations or implementation_targets:
        try:
            context = load_policy_context(project_root)
        except WorkStateError:
            context = None
        if context is None or context.phase != "work":
            if restricted_agent:
                return Decision(False, "Subagent 只在有效 work phase 写入；请返回 Coordinator 修复状态")
            confirmation_reasons.append("当前不是有效的 work phase")
        else:
            task = _task_for_action(project_root, context, payload)
            if task is None or task.status != "working":
                if restricted_agent:
                    return Decision(False, "Subagent 未认领 working active Task；请返回 Coordinator")
                confirmation_reasons.append("Agent 未认领处于 working 的 active Task")
            else:
                invalid_files = [
                    target
                    for target in implementation_targets
                    if not any(_scope_matches(target, scope) for scope in task.scopes)
                ]
                if invalid_files:
                    if restricted_agent:
                        return Decision(False, f"Subagent 写入超出 {task.id} Scope；请返回 Coordinator")
                    confirmation_reasons.append(
                        f"Bash 文件写入超出 {task.id} Scope"
                    )
                invalid_svn = [
                    targets
                    for _operation, targets in svn_mutations
                    if not targets
                    or any(
                        not any(_scope_matches(target, scope) for scope in task.scopes)
                        for target in targets
                    )
                ]
                if invalid_svn:
                    confirmation_reasons.append(
                        "SVN 目标不在 active_task Scope 内或无法精确识别"
                    )
    if external_write:
        confirmation_reasons.append("命令会写入外部系统")
    if confirmation_reasons:
        return Decision(
            True,
            "；".join(dict.fromkeys(confirmation_reasons)) + "，请确认",
            ask=True,
        )
    return Decision(True)


def decide_tool(project_root: Path, payload: dict[str, object]) -> Decision:
    tool_name = str(payload.get("tool_name", ""))
    raw_input = payload.get("tool_input", {})
    if not isinstance(raw_input, dict):
        return Decision(False, "tool_input 必须是对象")
    tool_input = raw_input
    path = _state_path(project_root, tool_input)
    restricted_agent = _is_restricted_agent(payload)

    # Governance state is always repairable by the Coordinator, even when it
    # is missing or invalid. Subagents return structured results instead.
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and path in STATE_FILES:
        if restricted_agent:
            return Decision(False, "Subagent 不能修改治理文件；请返回 Coordinator")
        return Decision(True)

    if tool_name in {"Read", "Glob", "Grep", "WebFetch", "WebSearch"}:
        if path is not None and _relative_path(project_root, path) is None:
            return Decision(False, "读取路径不在项目内")
        return Decision(True)
    if tool_name == "Bash":
        return _decide_bash(
            project_root,
            str(tool_input.get("command", "")),
            payload,
        )
    if tool_name in {"Skill", "Agent", "AskUserQuestion"}:
        return Decision(True)
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        if path is None:
            if restricted_agent:
                return Decision(False, "Subagent 的写入必须位于已认领 Task Scope；请返回 Coordinator")
            return Decision(True, "写入目标不在项目内，请核对目标后确认", ask=True)
        if path == "CLAUDE.md" or path.startswith(CONTROL_PREFIXES):
            if restricted_agent:
                return Decision(False, f"Subagent 不能修改控制面 {path}；请返回 Coordinator")
            return Decision(True, f"将修改 wali-0x3 控制面：{path}", ask=True)
        try:
            context = load_policy_context(project_root)
        except WorkStateError:
            if restricted_agent:
                return Decision(False, "Subagent 无法读取有效工作状态；请返回 Coordinator 修复")
            return Decision(True, "工作状态不可读；继续写入需要确认", ask=True)
        if context.phase != "work":
            phase = context.phase
            if restricted_agent:
                return Decision(False, f"Subagent 不能在 {phase} phase 修改实现；请返回 Coordinator")
            return Decision(True, f"{phase} phase 的实现写入需要确认：{path}", ask=True)
        task = _task_for_action(project_root, context, payload)
        if task is None or task.status != "working":
            if restricted_agent:
                return Decision(False, "Subagent 未认领 working active Task；请返回 Coordinator")
            return Decision(True, "Agent 未认领处于 working 的 active Task；继续写入需要确认", ask=True)
        if not any(_scope_matches(path, scope) for scope in task.scopes):
            if restricted_agent:
                return Decision(False, f"Subagent 写入超出 {task.id} Scope；请返回 Coordinator")
            return Decision(True, f"写入超出 {task.id} Scope：{path}", ask=True)
        return Decision(True)
    # Tools outside the configured hook matcher remain governed by Claude's own
    # permission system. If invoked here explicitly, do not invent a denial.
    return Decision(True)


def _decision_output(decision: Decision) -> None:
    permission_decision = (
        "ask" if decision.ask else "allow" if decision.allowed else "deny"
    )
    output: dict[str, object] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": permission_decision,
    }
    if decision.reason:
        output["permissionDecisionReason"] = decision.reason
    print(
        json.dumps(
            {
                "hookSpecificOutput": output,
            },
            ensure_ascii=False,
        )
    )


def _run_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是对象")
        decision = decide_tool(project_root, payload)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        decision = Decision(False, f"WALI Hook 输入无效：{error}")
    _decision_output(decision)
    return 0


def _run_post_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是对象")
        tool_name = str(payload.get("tool_name", ""))
        raw_input = payload.get("tool_input", {})
        tool_input = raw_input if isinstance(raw_input, dict) else {}
        path = _state_path(project_root, tool_input)
        if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and path in STATE_FILES:
            _goal, _state, reasons = _project_state(project_root)
            if reasons:
                print(
                    json.dumps(
                        {
                            "systemMessage": "WALI 状态需要修复：\n- " + "\n- ".join(reasons)
                        },
                        ensure_ascii=False,
                    )
                )
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(json.dumps({"systemMessage": f"WALI PostHook 无法检查结果：{error}"}, ensure_ascii=False))
    return 0


def _run_check(project_root: Path, checkpoint: str | None) -> int:
    try:
        state = load_state(project_root)
        reasons = checkpoint_reasons(state, checkpoint) if checkpoint else validate_state(state)
    except WorkStateError as error:
        reasons = [str(error)]
    if reasons:
        print("WALI 状态检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    print("WALI 状态检查通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("hook")
    subparsers.add_parser("post-hook")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--checkpoint", choices=("work", "verify", "done"))
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "hook":
        return _run_hook(project_root)
    if args.command == "post-hook":
        return _run_post_hook(project_root)
    return _run_check(project_root, args.checkpoint)


if __name__ == "__main__":
    sys.exit(main())
