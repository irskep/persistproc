# Refactoring Proposal for `persistproc`

This document outlines a refactoring plan to improve the code quality of the `persistproc` codebase. The main goals are:

1.  **Reduce complexity**: Break down large, deeply-nested functions into smaller, more semantic functions.
2.  **Improve testability**: Replace the use of global variables with dependency injection.
3.  **Increase encapsulation**: Ensure that modules hide their internal complexity and expose clear APIs.

---

## 1. Eliminate Global State in `server.py`

**Problem**: The `server.py` module uses a global `process_manager` variable. This makes the application state harder to reason about and complicates testing, as the module's behavior depends on a global variable that can be modified from multiple places.

**Proposal**: We will remove the global variable and use dependency injection. The `ProcessManager` instance will be created in `run_server` and explicitly passed to the functions that need it.

### Before (`server.py`)

```python
# ...
process_manager: Optional[ProcessManager] = None

def create_app(pm: Optional[ProcessManager] = None) -> FastMCP:
    global process_manager
    if pm:
        process_manager = pm
    elif process_manager is None:
        # ... creates process_manager
    # ...

def setup_signal_handlers():
    def signal_handler(signum, frame):
        # ... uses global process_manager
        for pid, p_info in process_manager.processes.items():
            # ...

def run_server(host: str = "127.0.0.1", port: int = 8947, verbose: bool = False):
    global process_manager
    # ...
    process_manager = ProcessManager(LOG_DIRECTORY)
    app = create_app()
    setup_signal_handlers()
    # ...
```

### After (`server.py`)

```python
# No more global process_manager

def create_app(process_manager: ProcessManager) -> FastMCP:
    app = FastMCP(...)
    app.process_manager = process_manager # Store it on the app instance
    create_tools(app, process_manager)
    return app

def setup_signal_handlers(process_manager: ProcessManager):
    def signal_handler(signum, frame):
        # ... uses process_manager passed as argument
        for pid, p_info in process_manager.processes.items():
            # ...

def run_server(host: str = "127.0.0.1", port: int = 8947, verbose: bool = False):
    # ...
    LOG_DIRECTORY = ...
    process_manager = ProcessManager(LOG_DIRECTORY)
    app = create_app(process_manager)
    setup_signal_handlers(process_manager)
    # ...
```

---

## 2. Decompose Large Functions in `core.py`

**Problem**: Several methods in `ProcessManager` are long and handle multiple concerns, making them hard to read and maintain.

**Proposal**: We will break down these large methods into smaller, more focused helper methods.

### `start_process`

The `start_process` method currently handles checking for existing processes, creating the subprocess, and logging. We can extract the subprocess creation.

#### Before (`core.py`)
```python
# In ProcessManager.start_process
# ...
try:
    proc = subprocess.Popen(
        shlex.split(command),
        # ... args ...
    )
except FileNotFoundError as e:
    raise ValueError(f"Command not found: {e.filename}") from e
except Exception as e:
    raise RuntimeError(f"Failed to start process: {e}") from e
# ...
```

#### After (`core.py`)

```python
class ProcessManager:
    # ...
    def _create_subprocess(self, command: str, working_directory: Optional[str], environment: Optional[Dict[str, str]]) -> subprocess.Popen:
        try:
            return subprocess.Popen(
                shlex.split(command),
                cwd=working_directory,
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError as e:
            raise ValueError(f"Command not found: {e.filename}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to start process: {e}") from e

    def start_process(self, command: str, ...) -> Dict:
        # ...
        proc = self._create_subprocess(command, working_directory, environment)
        # ...
```

### `stop_process`

The `stop_process` method contains complex logic for gracefully stopping a process with a fallback to a forceful stop. This can be clarified.

#### Proposal
Extract the sequence of sending `SIGTERM`, waiting, and then sending `SIGKILL` into a dedicated helper method. This makes the logic in `stop_process` clearer and focused on state management.

---

## 3. Simplify Client-Side Logic in `cli.py`

**Problem**: The `run_and_tail_async` function in `cli.py` is very large. It handles argument parsing, connecting to the server, starting the process (with restart logic), and then initiating the log tailing.

**Proposal**: Break this function into smaller, more manageable async functions.

1.  `_find_or_start_process`: This function will contain the logic to connect to the server, check if the process is running, handle the `--restart` flag, and return the process info.
2.  `run_and_tail_async`: This will become a much simpler orchestrator function that calls `_find_or_start_process` and then `tail_and_monitor_process_async`.

### After (`cli.py` - conceptual)

```python
async def _find_or_start_process(client: Client, args: argparse.Namespace) -> Optional[dict]:
    # All the logic for starting, checking existing, and restarting a process
    # ...
    return p_info

async def run_and_tail_async(args: argparse.Namespace):
    # ...
    async with Client(mcp_url) as client:
        p_info = await _find_or_start_process(client, args)
        if not p_info:
            sys.exit(1)

        # ... get log paths ...

        await tail_and_monitor_process_async(client, pid, ..., p_info)
    # ...
```

---

## 4. Improve Tool Encapsulation in `tools.py`

**Problem**: The `tools.py` module contains business logic that should reside in `ProcessManager`. For example, the `restart_process` tool orchestrates calls to `stop_process` and `start_process`. Additionally, `get_process_log_paths` accesses internal state of `ProcessManager`.

**Proposal**:

1.  **Move `restart_process` logic**: Create a `ProcessManager.restart_process(pid)` method. The tool will become a simple wrapper around this call.
2.  **Encapsulate log path access**: Create a `ProcessManager.get_log_paths(pid)` method that returns the log paths, hiding the implementation detail of how they are stored or retrieved.

### `restart_process`

#### Before (`tools.py`)
```python
@app.tool()
def restart_process(pid: int) -> str:
    # ...
    try:
        p_info_dict = process_manager.get_process_status(pid)
        # ... get command, wd, env ...
        process_manager.stop_process(pid)
        new_p_info_dict = process_manager.start_process(command, wd, env)
        return json.dumps(new_p_info_dict, indent=2)
    # ...
```

#### After (`core.py` and `tools.py`)

```python
# In core.py
class ProcessManager:
    # ...
    def restart_process(self, pid: int) -> Dict:
        p_info = self.get_process_status(pid)
        command = p_info["command"]
        wd = p_info.get("working_directory")
        env = p_info.get("environment")

        self.stop_process(pid)
        return self.start_process(command, wd, env)

# In tools.py
@app.tool()
def restart_process(pid: int) -> str:
    try:
        result = process_manager.restart_process(pid)
        return json.dumps(result, indent=2)
    except (ValueError, RuntimeError) as e:
        # ... error handling ...
``` 