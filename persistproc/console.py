import os
from rich.console import Console
from rich import print as rich_print, print_json as rich_print_json

# Cross-platform output helpers that use Rich on Unix but plain output on Windows


def print_rule(title: str = "") -> None:
    """Print a horizontal rule with optional title."""
    if os.name == "nt":
        # Windows: Plain text rule
        if title:
            print(f"--- {title} ---")
        else:
            print("-" * 50)
    else:
        # Unix: Rich formatted rule
        console = Console()
        if title:
            console.rule(f"[bold yellow]{title}[/bold yellow]")
        else:
            console.rule()


def print_json(data) -> None:
    """Print JSON data with formatting."""
    if os.name == "nt":
        # Windows: Plain JSON
        import json

        print(json.dumps(data, indent=2))
    else:
        # Unix: Rich formatted JSON
        rich_print_json(data=data)


def print_rich(*args, **kwargs) -> None:
    """Print with Rich formatting on Unix, plain on Windows."""
    if os.name == "nt":
        # Windows: Strip Rich markup and use plain print
        plain_args = []
        for arg in args:
            if isinstance(arg, str):
                # Simple Rich markup removal
                import re

                plain_arg = re.sub(r"\[/?[^\]]*\]", "", str(arg))
                plain_args.append(plain_arg)
            else:
                plain_args.append(arg)
        print(*plain_args)
    else:
        # Unix: Use Rich print
        rich_print(*args, **kwargs)
