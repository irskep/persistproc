# Tools and commands

This page documents all persistproc commands and their usage. Most commands are available both from the command line and as MCP tools for agents, with a few exceptions noted below.

!!! info "What is a tool?"
    persistproc is primarily an MCP server, but all its tools are accessible to you on the command line. This page will discuss each tool in its command line form. The agent has access to the exact same functionality, just through a different mechanism for calling the tools.

## `serve`

!!! note "Command-line only"
    This command is only available from the command line, not as an MCP tool. It doesn't make sense for an agent to start the server.

Starts the server. Necessary for everything else to work. `persistproc` with no subcommands is an alias for `persistproc serve`.

<!-- persistproc serve --help -->
```
usage: persistproc serve [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                         [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
```

**Examples**

Start the server with default settings:

```bash
> persistproc serve
```

Customize the port:

```bash
> persistproc serve --port 9000
```

Enable verbose logging:

```bash
> persistproc serve -v
```

## `run`

!!! note "Command-line only"
    This command is only available from the command line, not as an MCP tool. Agents should use the `start` tool instead.

Ensures a process is running, reproduces its stdout+stderr output on stdout, and lets you kill the process when you Ctrl+C. Most of the time, you can take any command and put `persistproc run` in front of it to magically run it via `persistproc`. (There are some exceptions; see examples below for when you need `--`.)

<!-- persistproc run --help -->
```
usage: persistproc run [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                       [--format {text,json}] [--fresh]
                       [--on-exit {ask,stop,detach}] [--raw] [--label LABEL]
                       program [args ...]

positional arguments:
  program               The program to run (e.g. 'python' or 'ls'). If the
                        string contains spaces, it will be shell-split unless
                        additional arguments are provided separately.
  args                  Arguments to the program

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --fresh               Stop an existing running instance of the same command
                        before starting a new one.
  --on-exit {ask,stop,detach}
                        Behaviour when you press Ctrl+C: ask (default), stop
                        the process, or detach and leave it running.
  --raw                 Show raw timestamped log lines (default strips ISO
                        timestamps).
  --label LABEL         Custom label for the process (default: '<command> in
                        <working_directory>').
```

**Examples**

Most commands work without any special syntax:

```bash
> persistproc run npm run dev
> persistproc run python -m http.server 8080
```

When your command has flags that conflict with persistproc's own flags, use `--` to separate them:

```bash
> persistproc run -- echo -v "verbose output"
> persistproc run -- ls -v
```

You can also pass commands as shell-escaped strings:

```bash
> persistproc run 'echo "Hello World"'
```

Use labels to identify complex processes more easily:

```bash
> persistproc run --label "api-server" 'python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug'
```

The `--fresh` flag stops any existing instance before starting:

```bash
persistproc run --fresh npm run dev
```

Control what happens when you press Ctrl+C (default is to ask):

```bash
# Stop the process when you exit
> persistproc run --on-exit stop npm run dev

# Leave process running when you exit
> persistproc run --on-exit detach npm run dev
```

## `start`

Start a new process.

<!-- persistproc start --help -->
```
usage: persistproc start [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                         [--format {text,json}]
                         [--working-directory WORKING_DIRECTORY]
                         [--label LABEL]
                         COMMAND [args ...]

positional arguments:
  COMMAND               The command to run.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
  --label LABEL         Custom label for the process (default: '<command> in
                        <working_directory>').
```

**Examples**

Basic usage:

```bash
> persistproc start npm run dev
Started process with PID: 12345
Label: npm run dev in /Users/user/myproject
Stdout log: /Users/user/Library/Application Support/persistproc/logs/12345_stdout.log
Stderr log: /Users/user/Library/Application Support/persistproc/logs/12345_stderr.log
Combined log: /Users/user/Library/Application Support/persistproc/logs/12345_combined.log
```

```bash
> persistproc start python -m http.server 8080
```

Unlike `run`, the `start` command doesn't stream output, so you typically don't need `--` for flag conflicts:

```bash
> persistproc start echo -v "verbose output"
```

Specify a working directory:

```bash
> persistproc start --working-directory /path/to/project npm run dev
```

Use shell-escaped strings for complex commands:

```bash
> persistproc start 'echo "Hello World"'
> persistproc start 'bash -c "cd /tmp && python -m http.server 9000"'
```

Add a custom label for complex commands:

```bash
> persistproc start --label "worker-pool" 'celery -A myapp worker --loglevel=info --concurrency=4 --queues=high_priority,low_priority'
```

## `list`

List all managed processes and their status.

<!-- persistproc list --help -->
```
usage: persistproc list [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                        [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
```

**Examples**

```bash
> persistproc list
PID 12345: npm run dev in /Users/user/myproject (running)
Command: npm run dev
Working directory: /Users/user/myproject

PID 67890: python -m http.server 8080 in /Users/user/docs (running)
Command: python -m http.server 8080
Working directory: /Users/user/docs
```

Get more detailed output or different formats:

```bash
> persistproc list -v
> persistproc list --format json
```

## `status`

Get the detailed status of a specific process.

<!-- persistproc status --help -->
```
usage: persistproc status [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                          [--format {text,json}]
                          [--working-directory WORKING_DIRECTORY]
                          TARGET [args ...]

positional arguments:
  TARGET                The PID, label, or command to get status for.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
```

**Examples**

Get status by PID, command, or label:

```bash
> persistproc status 12345
PID: 12345
Command: npm run dev
Working directory: /Users/user/myproject
Status: running
Label: npm run dev in /Users/user/myproject

> persistproc status npm run dev
> persistproc status "my-dev-server"
```

Add working directory context when matching by command:

```bash
> persistproc status --working-directory /path/to/project npm run dev
```

Get structured output:

```bash
> persistproc status --format json 12345
```

## `stop`

Stop a running process.

<!-- persistproc stop --help -->
```
usage: persistproc stop [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                        [--format {text,json}]
                        [--working-directory WORKING_DIRECTORY] [--force]
                        TARGET [args ...]

positional arguments:
  TARGET                The PID, label, or command to stop.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
  --force               Force stop the process.
```

**Examples**

Stop a process by PID, command, or label:

```bash
> persistproc stop 12345
Process stopped with exit code: 0

> persistproc stop npm run dev
> persistproc stop "my-dev-server"
```

Add working directory context when matching by command:

```bash
> persistproc stop --working-directory /path/to/project npm run dev
```

Force stop if the process doesn't respond to normal termination:

```bash
> persistproc stop --force 12345
```

## `restart`

Stops a process and starts it again with the same arguments and working directory.

First, the process shut down completely. If the process fails to shut down within xxx, returns an error. TODO cross reference with 'stop'

Then, the command, working directory, and environment variables are reused to start a fresh copy of the process.

`output` will only return the logs for the latest copy of the process, not the history of every run.

<!-- persistproc restart --help -->
```
usage: persistproc restart [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                           [--format {text,json}]
                           [--working-directory WORKING_DIRECTORY]
                           TARGET [args ...]

positional arguments:
  TARGET                The PID, label, or command to restart.
  args

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
```

**Examples**

Restart a process by PID, command, or label:

```bash
> persistproc restart 12345
Process restarted with PID: 54321

> persistproc restart npm run dev
> persistproc restart "my-dev-server"
```

Add working directory context when matching by command:

```bash
> persistproc restart --working-directory /path/to/project npm run dev
```

## `output`

Retrieve captured output from a process.

<!-- persistproc output --help -->
```
usage: persistproc output [-h] [--port PORT] [--data-dir DATA_DIR] [-v] [-q]
                          [--format {text,json}]
                          [--stream {stdout,stderr,combined}] [--lines LINES]
                          [--before-time BEFORE_TIME]
                          [--since-time SINCE_TIME]
                          [--working-directory WORKING_DIRECTORY]
                          TARGET [args ...]

positional arguments:
  TARGET                The PID, label, or command to get output for.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --stream {stdout,stderr,combined}
                        The output stream to read.
  --lines LINES         The number of lines to retrieve.
  --before-time BEFORE_TIME
                        Retrieve logs before this timestamp.
  --since-time SINCE_TIME
                        Retrieve logs since this timestamp.
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
```

**Examples**

Get recent output from a process:

```bash
> persistproc output 12345
[2024-07-06 14:30:21] > dev-server@1.0.0 dev
[2024-07-06 14:30:21] > vite
[2024-07-06 14:30:22] 
[2024-07-06 14:30:22]   VITE v4.4.0  ready in 324 ms
[2024-07-06 14:30:22] 
[2024-07-06 14:30:22]   ➜  Local:   http://localhost:5173/
[2024-07-06 14:30:22]   ➜  Network: use --host to expose
[2024-07-06 14:30:22] 
[2024-07-06 14:30:22]   ➜  press h to show help

> persistproc output npm run dev
> persistproc output "my-dev-server"
```

Specify which output stream to read:

```bash
> persistproc output --stream stderr 12345
> persistproc output --stream stdout 12345
> persistproc output --stream combined 12345
```

Limit the number of lines:

```bash
> persistproc output --lines 50 12345
```

Get output from a specific time range:

```bash
> persistproc output --since-time "2024-01-01T10:00:00" 12345
> persistproc output --before-time "2024-01-01T12:00:00" 12345
```

Specify working directory context when matching by command:

```bash
> persistproc output --working-directory /path/to/project npm run dev
```

## `get_log_paths`

Get the paths to the log files for a specific process.

<!-- persistproc get_log_paths --help -->
```
usage: persistproc get_log_paths [-h] [--port PORT] [--data-dir DATA_DIR] [-v]
                                 [-q] [--format {text,json}]
                                 [--working-directory WORKING_DIRECTORY]
                                 TARGET [args ...]

positional arguments:
  TARGET                The PID, label, or command to get log paths for.
  args                  Arguments to the command

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
  --working-directory WORKING_DIRECTORY
                        The working directory for the process.
```

**Examples**

Get log file paths by PID, command, or label:

```bash
> persistproc get_log_paths 12345
Stdout log: /Users/user/Library/Application Support/persistproc/logs/12345_stdout.log
Stderr log: /Users/user/Library/Application Support/persistproc/logs/12345_stderr.log

> persistproc get_log_paths npm run dev
> persistproc get_log_paths "my-dev-server"
```

Add working directory context when matching by command:

```bash
> persistproc get_log_paths --working-directory /path/to/project npm run dev
```

## `kill_persistproc`

Kill all managed processes and get the PID of the persistproc server.

<!-- persistproc kill_persistproc --help -->
```
usage: persistproc kill_persistproc [-h] [--port PORT] [--data-dir DATA_DIR]
                                    [-v] [-q] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --port PORT           Server port (default: 8947; env: $PERSISTPROC_PORT)
  --data-dir DATA_DIR   Data directory (default:
                        ~/Library/Application Support/persistproc;
                        env: $PERSISTPROC_DATA_DIR)
  -v, --verbose         Increase verbosity; you can use -vv for more
  -q, --quiet           Decrease verbosity. Passing -q once will show only
                        warnings and errors.
  --format {text,json}  Output format (default: text; env:
                        $PERSISTPROC_FORMAT)
```

**Examples**

```bash
> persistproc kill_persistproc
Killed persistproc server with PID: 8947
```

Get structured output showing the server PID:

```bash
> persistproc kill_persistproc --format json
```