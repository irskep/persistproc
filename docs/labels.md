# Process identity and labels

## Process identity

When you run a command with persistproc, you're giving it 3 pieces of information: the command, the working directory, and the environment variables.

Command: `npm run dev`  
Working directory: `/Users/<you>/dev/<project>`  
Environment: `PATH=/Users/<you>/dev/</project> SHELL=/bin/zsh GITHUB_TOKEN=xxx ...`  

persistproc uses the command string _and_ the working directory to uniquely identify a process. Once starting, a process has a pid for that instance, but if the process is restarted, that pid will change.

So if you say `persistproc start 'npm run dev'` from within two different directories, then persistproc will treat them as distinct. When the LLM calls persistproc via MCP, it will be able to distinguish between the two copies, and if it makes an ambiguous request, persistproc will return an error that helps it try again.

## Custom labels

Internally, persistproc uses _labels_ to distinguish between processes, and the default label is `"<command> in <working directory>"`.

These default labels can be quite long if you're running a long command. The command itself can also not be very descriptive.

In cases like this, you can provide a `--label` argument to `persistproc start` or `persistproc run`. Example:

```bash
> persistproc start --label "api-server" 'python -m uvicorn myapp.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug --workers 4'
Started process with PID: 12345
Label: api-server
...

> persistproc start --label "worker-pool" 'celery -A myapp worker --loglevel=info --concurrency=8 --queues=high_priority,low_priority --pool=prefork'
Started process with PID: 67890
Label: worker-pool
...

> persistproc list
PID 12345: api-server (running)
Command: python -m uvicorn myapp.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug --workers 4
Working directory: /Users/user/myproject

PID 67890: worker-pool (running)
Command: celery -A myapp worker --loglevel=info --concurrency=8 --queues=high_priority,low_priority --pool=prefork
Working directory: /Users/user/myproject
```

Custom labels like this can make it even easier for agents to decide which process to inspect or restart.