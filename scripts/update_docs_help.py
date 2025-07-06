import re
import subprocess
from pathlib import Path


def get_help_text(command):
    # We need to handle the user's home dir replacement carefully.
    # The path printed by argparse can be different from Path.home().
    # For example, on macOS, it might be /Users/user vs /Users/user.
    # A simple regex is probably better.

    print(f"Fetching help for: {command}")
    print("⏳ Running command...", end="", flush=True)

    cmd_array = ["./pp"] + command.split() + ["--help"]

    result = subprocess.run(
        cmd_array,
        capture_output=True,
        text=True,
        check=True,
    )

    print(" ✅")  # Complete the progress line

    output_lines = result.stdout.splitlines()

    # Filter mise and uv dependency installation output
    dependency_patterns = [
        r"Installing dependencies\.\.\.",
        r"^\[deps:sync\]",
        r"^\s*\+\s+\w+==",  # + package==version
        r"^\s*\$\s+uv\s+sync",  # $ uv sync commands
    ]

    filtered_output_lines = [
        line
        for line in output_lines
        if not any(re.search(pattern, line) for pattern in dependency_patterns)
    ]
    output = "\n".join(filtered_output_lines)

    # Filter out uv installation messages from stderr
    filtered_stderr_lines = [
        line
        for line in result.stderr.splitlines()
        if not any(
            phrase in line
            for phrase in [
                "Installing dependencies...",
                "Audited",
                "Resolved",
                "Building",
                "Built",
                "Prepared",
                "Uninstalled",
                "Installed",
                "packages in",
                "package in",
            ]
        )
    ]
    if filtered_stderr_lines:
        output += "\n" + "\n".join(filtered_stderr_lines)

    # Simple replacement for the known default data directory path
    output = output.replace(
        "/Users/steve/Library/Application Support/persistproc",
        "~/Library/Application Support/persistproc",
    )

    return output


def main():
    docs_file = Path("docs/tools.md")
    lines = docs_file.read_text().splitlines()
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.search(r"<!-- persistproc (.*?) --help -->", line)
        if match:
            command = match.group(1)
            new_lines.append(line)  # Add the comment line
            i += 1  # Move to the next line (should be ```)
            if i < len(lines) and lines[i].strip() == "```":
                new_lines.append(lines[i])  # Add the opening ```
                i += 1  # Move past the opening ```
                try:
                    help_text = get_help_text(command)
                    new_lines.extend(
                        help_text.strip().splitlines()
                    )  # Add the help text
                except subprocess.CalledProcessError as e:
                    print(f" ❌ Error getting help for {command}: {e}")
                    # If error, keep original content or leave empty
                    while i < len(lines) and lines[i].strip() != "```":
                        i += 1  # Skip original content until closing ```

                # Skip existing content until the closing ```
                while i < len(lines) and lines[i].strip() != "```":
                    i += 1

                if i < len(lines) and lines[i].strip() == "```":
                    new_lines.append(lines[i])  # Add the closing ```
                else:
                    # If no closing ``` found, add one to prevent malformed markdown
                    new_lines.append("```")
            else:
                new_lines.append(
                    line
                )  # Add the original line back if format is unexpected
        else:
            new_lines.append(line)
        i += 1

    docs_file.write_text("\n".join(new_lines))


if __name__ == "__main__":
    main()
