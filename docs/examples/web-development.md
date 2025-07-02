# Web Development with PersistProc

This guide demonstrates how PersistProc transforms web development workflows, particularly for projects involving multiple services and AI agents.

## The Modern Web Dev Challenge

Modern web applications often involve multiple processes:

- **Frontend development server** (React, Vue, Angular)
- **Backend API server** (Node.js, Python, Go)
- **Database** (PostgreSQL, MongoDB, Redis)
- **Build tools** (Webpack, Vite, Parcel)
- **Testing frameworks** (Jest, Cypress, Playwright)

Managing these across different AI agents and terminal sessions is exactly the problem PersistProc solves.

## Complete Example: Full-Stack React + Node.js App

Let's walk through a realistic scenario: You're building a full-stack application with multiple AI agents helping you.

### Project Structure

```
my-app/
├── frontend/          # React app
│   ├── package.json
│   └── src/
├── backend/           # Node.js API
│   ├── package.json
│   └── src/
├── docs/             # Documentation site
└── package.json      # Root package.json
```

### Step 1: Start the PersistProc Server

First, start PersistProc in a dedicated terminal (keep this running):

```bash
cd my-app
persistproc --serve
```

### Step 2: Initial Development Setup

Start your development environment. You can do this from any terminal or ask an AI agent:

#### Via Terminal

```bash
# Start all development services
persistproc --start npm run dev:frontend
persistproc --start npm run dev:backend
persistproc --start npm run dev:db

# Or use a compound command
persistproc npm run dev:all
```

#### Via AI Agent (Cursor)

Ask your Cursor assistant:

> "Start the development environment for this full-stack app"

The agent will:
1. Analyze your `package.json` scripts
2. Use `start_process` to launch each service
3. Report the status of all services

### Step 3: Multi-Agent Development Workflow

Now the real power of PersistProc becomes apparent. Here's how different agents can collaborate:

#### Frontend Work (Cursor)

You're working on React components in Cursor:

**You**: *"The webpack dev server seems slow. Can you restart it with different settings?"*

**Agent Response**: 
1. Uses `list_processes()` to find the frontend server
2. Uses `restart_process(pid)` to restart it
3. Optionally uses `get_process_output()` to check startup logs

```json
{
  "tool": "restart_process",
  "parameters": {
    "pid": 12345
  }
}
```

#### Backend Debugging (Claude Code)

Switch to Claude Code for API work:

**You**: *"Check if the API server is running and show me any recent errors"*

**Agent Actions**:
1. Uses `list_processes()` to find API server
2. Uses `get_process_output(pid, "stderr", lines=50)` to check error logs
3. Analyzes logs for common issues

#### Database Management (Terminal)

Meanwhile, you manually manage the database:

```bash
# Check all running services
persistproc --list

# Restart database if needed
persistproc --restart npm run dev:db

# View database logs
persistproc --logs <db-pid>
```

### Step 4: Real-World Scenarios

#### Scenario 1: Port Conflict Resolution

**Problem**: You try to start a service but get "port already in use" error.

**Solution with PersistProc**:

```bash
# Check what's running
persistproc --list

# Output shows:
# PID 12345: npm run dev:frontend (running) - port 3000
# PID 12346: npm run dev:backend (running) - port 3001

# Stop the conflicting service
persistproc --stop 12345

# Start with different port
PORT=3002 persistproc npm run dev:frontend
```

**Or ask an AI agent**:

> "I'm getting a port conflict. Can you check what's running and fix it?"

#### Scenario 2: Hot Reloading Issues

**Problem**: Frontend hot reloading stops working.

**Solution**:

Ask your agent: *"The frontend hot reload isn't working. Can you restart the dev server and check for errors?"*

Agent response:
1. Restarts the frontend process
2. Monitors startup logs for errors
3. Reports any webpack/Vite configuration issues

#### Scenario 3: API Server Crashes

**Problem**: Backend server crashes during development.

**AI Agent Detection**:
```python
def check_api_health(client):
    processes = client.list_processes()
    
    for proc in processes['processes']:
        if 'api' in proc['command'] and proc['status'] != 'running':
            # Get crash logs
            logs = client.get_process_output(
                proc['pid'], 
                'stderr', 
                lines=20
            )
            return f"API server crashed. Error: {logs['output']}"
    
    return "API server is healthy"
```

#### Scenario 4: Testing Integration

**Scenario**: You want to run tests while keeping servers running.

```bash
# Start test runner in watch mode
persistproc npm run test:watch

# Run E2E tests against running servers
persistproc npm run test:e2e

# All services continue running independently
```

## Advanced Workflows

### Workflow 1: Branch Switching

When switching git branches that require different dependencies:

```bash
# Ask agent: "I'm switching to the feature/new-api branch. 
# Can you restart all services after I switch?"

git checkout feature/new-api
npm install

# Agent automatically:
# 1. Stops all current processes
# 2. Runs npm install
# 3. Restarts all services
# 4. Monitors for startup errors
```

### Workflow 2: Environment Switching

Switching between development and staging:

```bash
# Agent command sequence:
# 1. Stop dev services
# 2. Start staging services with different env vars
# 3. Update database connection
# 4. Verify all services are healthy

ENV=staging persistproc npm run start:all
```

### Workflow 3: Performance Monitoring

Continuous monitoring during development:

```bash
# Start performance monitoring
persistproc npm run monitor

# AI agent periodically checks:
# - Memory usage of all processes
# - Log file sizes
# - Response times
# - Error rates
```

## Integration with Common Tools

### Webpack Dev Server

```json
// package.json
{
  "scripts": {
    "dev": "webpack serve --mode development --port 3000",
    "dev:debug": "webpack serve --mode development --port 3000 --verbose"
  }
}
```

**PersistProc Usage**:
```bash
# Normal start
persistproc npm run dev

# Debug mode
persistproc npm run dev:debug

# Monitor webpack logs
persistproc --logs <webpack-pid>
```

### Vite Development

```json
// package.json
{
  "scripts": {
    "dev": "vite --port 3000",
    "dev:host": "vite --port 3000 --host 0.0.0.0"
  }
}
```

**Agent Interaction**:

> "Start the Vite dev server and make it accessible from other devices"

Agent uses: `start_process("npm run dev:host")`

### Next.js Development

```json
// package.json
{
  "scripts": {
    "dev": "next dev",
    "dev:turbo": "next dev --turbo",
    "build": "next build",
    "start": "next start"
  }
}
```

**Multi-Environment Setup**:
```bash
# Development
persistproc npm run dev

# Production build + start
persistproc npm run build
persistproc npm run start
```

### Express.js API

```json
// package.json
{
  "scripts": {
    "dev": "nodemon src/server.js",
    "start": "node src/server.js",
    "debug": "node --inspect src/server.js"
  }
}
```

**Debugging Workflow**:
```bash
# Start in debug mode
persistproc npm run debug

# Agent can monitor debug output and suggest breakpoints
```

## Best Practices for Web Development

### 1. Service Naming

Use clear, descriptive names for your processes:

```json
{
  "scripts": {
    "dev:frontend": "cd frontend && npm run dev",
    "dev:backend": "cd backend && npm run dev", 
    "dev:db": "docker-compose up postgres",
    "dev:redis": "redis-server",
    "dev:all": "concurrently \"npm run dev:frontend\" \"npm run dev:backend\" \"npm run dev:db\""
  }
}
```

### 2. Environment Management

Use environment-specific startup scripts:

```bash
# Development
ENV=development persistproc npm run dev:all

# Staging
ENV=staging persistproc npm run start:staging

# Production simulation
ENV=production persistproc npm run start:prod
```

### 3. Log Management

Configure proper logging for each service:

```json
{
  "scripts": {
    "dev:frontend": "REACT_APP_LOG_LEVEL=debug npm run dev",
    "dev:backend": "DEBUG=api:* npm run dev"
  }
}
```

### 4. Health Checks

Implement health check scripts:

```json
{
  "scripts": {
    "health:frontend": "curl -f http://localhost:3000/health",
    "health:backend": "curl -f http://localhost:3001/api/health",
    "health:all": "npm run health:frontend && npm run health:backend"
  }
}
```

**Agent can periodically run health checks**:

```python
def monitor_health(client):
    # Check if health check process exists
    result = client.start_process("npm run health:all")
    
    if "error" in result:
        return "❌ Health check failed"
    else:
        return "✅ All services healthy"
```

## Troubleshooting Common Issues

### Issue 1: Process Won't Start

**Symptoms**: Agent reports process start failure

**Debug Steps**:
```bash
# Check the actual error
persistproc --logs <failed-pid>

# Try starting manually
npm run dev

# Check port availability
lsof -i :3000
```

### Issue 2: Logs Not Appearing

**Symptoms**: No output from `get_process_output`

**Solutions**:
1. Check if process is actually running
2. Verify log capture is working
3. Try different output streams (stdout vs stderr)

### Issue 3: Performance Degradation

**Symptoms**: Slow response times, high CPU usage

**AI Agent Diagnosis**:
```python
def diagnose_performance(client):
    processes = client.list_processes()
    
    issues = []
    for proc in processes['processes']:
        if proc['cpu_percent'] > 80:
            issues.append(f"High CPU: {proc['command']} ({proc['cpu_percent']}%)")
        if proc['memory_mb'] > 1024:
            issues.append(f"High Memory: {proc['command']} ({proc['memory_mb']}MB)")
    
    return issues
```

---

**Next**: Explore [Multi-Service Projects](multi-service.md) for more complex deployment scenarios.