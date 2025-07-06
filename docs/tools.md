# Tools and commands

Operations available on the command line but not as MCP tools are marked "(command-line only)". This only applies to things that don't make sense for an agent to do, such as starting the server.

!!! note "What is a tool?"
    persistproc is primarily an MCP server, but all its tools are accessible to you on the command line. This page will discuss each tool in its command line form. The agent has access to the exact same functionality, just through a different mechanism for calling the tools.

## `serve` (command-line only)

Starts the server. Necessary for everything else to work. `persistproc` with no subcommands is an alias for `persistproc serve`.

<!-- persistproc serve --help -->
```
usage: persistproc serve [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default: ~/Library/Application Support/persistproc; env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only warnings and errors.
  --format {text,json}  Output format (default: text; env: $PERSISTPROC_FORMAT)
```

### Examples

TBD

## `run` (command-line only)

Ensures a process is running, reproduces its stdout+stderr output on stdout, and lets you kill the process when you Ctrl+C. Most of the time, you can take any command and put `persistproc run` in front of it to magically run it via `persistproc`. (There are some exceptions; see examples below for when you need `--`.)

<!-- persistproc run --help -->
```
usage: persistproc run [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q] [--format {text,json}] [--fresh] [--on-exit {ask,stop,detach}] [--raw]
                       [--label LABEL]
                       program [args ...]

positional arguments:
  program               The program to run (e.g. 'python' or 'ls'). If the string contains spaces, it will be shell-split unless additional
                        arguments are provided separately.
  args                  Arguments to the program

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default: ~/Library/Application Support/persistproc; env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only warnings and errors.
  --format {text,json}  Output format (default: text; env: $PERSISTPROC_FORMAT)
  --fresh               Stop an existing running instance of the same command before starting a new one.
  --on-exit {ask,stop,detach}
                        Behaviour when you press Ctrl+C: ask (default), stop the process, or detach and leave it running.
  --raw                 Show raw timestamped log lines (default strips ISO timestamps).
  --label LABEL         Custom label for the process (default: '<command> in <working_directory>').
```

### Examples

TBD

## `start`

<!-- persistproc serve --help -->
```
usage: persistproc start [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q] [--format {text,json}] [--working-directory WORKING_DIRECTORY]
                         [--label LABEL]
                         COMMAND [args ...]

positional arguments:
  COMMAND               The command to run.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default: ~/Library/Application Support/persistproc; env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only warnings and errors.
  --format {text,json}  Output format (default: text; env: $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
  --label LABEL         Custom label for the process (default: '<command> in <working_directory>').
```