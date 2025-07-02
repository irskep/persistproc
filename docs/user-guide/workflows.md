# Workflows & Examples

This guide demonstrates common workflows and real-world scenarios where PersistProc shines in multi-agent development environments.

## Workflow 1: Full-Stack Development Setup

**Scenario**: You're building a modern web application with separate frontend and backend services.

### Traditional Approach (Problems)

```bash
# Terminal 1: Frontend
cd frontend
npm run dev

# Terminal 2: Backend  
cd backend
npm run dev

# Terminal 3: Database
docker-compose up postgres

# Problems:
# - 3 separate terminals to manage
# - If you close a terminal, you lose that service
# - AI agents can't see or manage these processes
# - Port conflicts when agents try to start services
```

### PersistProc Approach (Solution)

```bash
# Start PersistProc server (once, in dedicated terminal)
persistproc --serve

# Start all services (from anywhere, or via AI agents)
persistproc --start --working-dir frontend npm run dev
persistproc --start --working-dir backend npm run dev  
persistproc --start docker-compose up postgres

# Now any AI agent can manage these processes!
```

**Benefits**:
- ✅ Services persist across terminal sessions
- ✅ AI agents can start, stop, restart any service
- ✅ Centralized logging and monitoring
- ✅ No port conflicts

## Workflow 2: Multi-Agent Collaboration

**Scenario**: You switch between different AI tools while working on the same project.

### Example Session

#### 1. Start Development (Terminal)

```bash
# You start the basic environment
persistproc npm run dev:frontend
persistproc npm run dev:backend

# Check everything is running
persistproc --list
```

#### 2. Frontend Work (Cursor)

**You ask Cursor**: *"The React dev server is running slowly. Can you restart it and check for any webpack issues?"*

**Cursor's Response**:
1. Uses `list_processes()` to find the frontend server
2. Uses `restart_process(pid)` to restart it
3. Uses `get_process_output()` to check startup logs
4. Reports any webpack configuration issues found

#### 3. Backend Debugging (Claude Code)

**You ask Claude**: *"Check if the API server is responding and show me any recent errors"*

**Claude's Actions**:
1. Uses `list_processes()` to find the API server
2. Uses `get_process_output(pid, "stderr")` to check error logs
3. May suggest starting additional debugging processes
4. Provides analysis of any issues found

#### 4. Database Work (Terminal)

```bash
# Meanwhile, you handle database migrations manually
persistproc --start npm run db:migrate

# Check migration logs
persistproc --logs <migration-pid>
```

**Result**: Seamless collaboration where each tool/agent can see and control the entire development environment.

## Workflow 3: Environment Switching

**Scenario**: You need to switch between development, staging, and production-like environments.

### Smart Environment Management

```bash
# Stop all current processes
for pid in $(persistproc --list --format json | jq -r '.processes[].pid'); do
  persistproc --stop $pid
done

# Start staging environment
ENV=staging persistproc npm run start:staging
ENV=staging persistproc npm run api:staging
ENV=staging persistproc docker-compose -f docker-compose.staging.yml up

# Or ask an AI agent to do this:
# "Switch to staging environment - stop all dev processes and start staging ones"
```

### Environment-Specific Configs

```json
// package.json
{
  "scripts": {
    "dev:all": "concurrently \"npm run dev:frontend\" \"npm run dev:backend\"",
    "staging:all": "concurrently \"npm run start:frontend\" \"npm run start:backend\"",
    "prod:all": "concurrently \"npm run build:frontend\" \"npm run start:prod\""
  }
}
```

**Agent Usage**:
```bash
# AI agent can intelligently switch environments
# "Start the staging environment"
# -> agent stops dev processes and starts staging ones
```

## Workflow 4: Testing Integration

**Scenario**: Run tests against live development servers without disrupting the development flow.

### Parallel Testing

```bash
# Keep dev servers running
persistproc npm run dev:frontend  # Running on port 3000
persistproc npm run dev:backend   # Running on port 3001

# Start test runners that connect to live servers
persistproc npm run test:integration  # Tests against :3000/:3001
persistproc npm run test:e2e         # Cypress/Playwright tests

# All processes run independently
persistproc --list
# Shows: frontend, backend, integration tests, e2e tests all running
```

### Test-Driven Development Flow

**AI Agent Workflow**:

1. **You**: *"Run the unit tests and keep them watching for changes"*
   - Agent: `start_process("npm run test:watch")`

2. **You**: *"The API tests are failing. Restart the backend and run them again"*
   - Agent: `restart_process(backend_pid)` then `start_process("npm run test:api")`

3. **You**: *"Run the E2E tests against the current dev setup"*
   - Agent: `start_process("npm run test:e2e")` and monitors output

## Workflow 5: Debugging and Log Analysis

**Scenario**: Investigate issues across multiple services with AI assistance.

### Intelligent Log Analysis

**You ask an AI agent**: *"Something is wrong with user authentication. Check all related services for errors."*

**Agent's Response**:
```python
# Pseudo-code for what the agent does:
processes = list_processes()

for process in processes:
    if 'auth' in process.command or 'user' in process.command:
        logs = get_process_output(process.pid, 'stderr', lines=100)
        if 'error' in logs.lower() or 'fail' in logs.lower():
            report_issues(process, logs)
```

### Log Correlation

```bash
# Get logs from all services for the same time period
persistproc --logs frontend-pid --since "2024-01-15T10:30:00"
persistproc --logs backend-pid --since "2024-01-15T10:30:00"  
persistproc --logs auth-service-pid --since "2024-01-15T10:30:00"

# AI agent can correlate timestamps and find related errors
```

## Workflow 6: Branch Switching & Dependency Management

**Scenario**: Switch git branches that require different dependencies or configurations.

### Automated Branch Workflow

**You ask an AI agent**: *"I'm switching to the feature/new-api branch. Update the environment accordingly."*

**Agent's Workflow**:
1. Stop all current processes
2. You switch branches: `git checkout feature/new-api`
3. Agent detects changes and runs: `npm install`
4. Agent starts processes with new configuration
5. Agent monitors for startup errors and reports status

```bash
# Manual equivalent:
persistproc --stop --all
git checkout feature/new-api
npm install
persistproc npm run dev:all
```

## Workflow 7: Performance Monitoring

**Scenario**: Monitor application performance during development.

### Continuous Monitoring

```bash
# Start main services
persistproc npm run dev

# Start monitoring services
persistproc npm run monitor:performance
persistproc npm run monitor:memory
persistproc npm run monitor:logs

# AI agent can periodically check these and alert you
```

**Smart Monitoring Agent**:
```python
def monitor_health():
    processes = list_processes()
    
    issues = []
    for proc in processes:
        status = get_process_status(proc.pid)
        
        if status.cpu_percent > 80:
            issues.append(f"High CPU: {proc.command}")
        
        if status.memory_mb > 1024:
            issues.append(f"High Memory: {proc.command}")
    
    if issues:
        suggest_optimizations(issues)
```

## Workflow 8: Deployment Pipeline

**Scenario**: Run build and deployment processes while keeping development servers running.

### Parallel Build Pipeline

```bash
# Keep development running
persistproc npm run dev:watch

# Start build processes
persistproc npm run build:frontend
persistproc npm run build:backend
persistproc npm run test:full

# Deploy when ready
persistproc npm run deploy:staging
```

**AI-Managed Pipeline**:

**You**: *"Build and deploy to staging, but keep the dev servers running"*

**Agent Actions**:
1. Starts build processes without stopping dev servers
2. Monitors build progress and reports status
3. Runs tests against built artifacts
4. Deploys to staging if tests pass
5. Provides deployment status and URLs

## Workflow 9: Microservices Development

**Scenario**: Develop multiple microservices simultaneously.

### Service Orchestration

```bash
# Start all microservices
persistproc --start --name user-service npm run dev:users
persistproc --start --name order-service npm run dev:orders  
persistproc --start --name payment-service npm run dev:payments
persistproc --start --name notification-service npm run dev:notifications

# Start API gateway
persistproc --start --name gateway npm run dev:gateway

# Start shared services
persistproc --start --name redis redis-server
persistproc --start --name postgres docker-compose up postgres
```

**Service Management**:
```bash
# Restart specific service
persistproc --restart --name user-service

# Check service health
persistproc --status --name order-service

# View service logs
persistproc --logs --name payment-service
```

## Workflow 10: Documentation Development

**Scenario**: Develop documentation alongside code with live preview.

### Documentation Pipeline

```bash
# Start main application
persistproc npm run dev

# Start documentation server
persistproc mkdocs serve

# Start API documentation
persistproc npm run docs:api

# All update automatically as you code
```

**Content Creation Flow**:

**You**: *"Update the API documentation based on the latest code changes"*

**Agent Actions**:
1. Analyzes current API endpoints from running dev server
2. Updates documentation files
3. Restarts docs server to reflect changes
4. Provides links to updated documentation

## Best Practices for Workflows

### 1. Naming Conventions

Use consistent naming for easier management:

```bash
# Good naming patterns
persistproc --start --name "frontend-dev" npm run dev
persistproc --start --name "backend-dev" npm run dev:api
persistproc --start --name "db-dev" docker-compose up postgres

# Easy to filter and manage
persistproc --list --name "*-dev"
```

### 2. Environment Variables

Set up environment-specific configurations:

```bash
# Development
export NODE_ENV=development
export API_URL=http://localhost:3001
persistproc npm run dev

# Staging  
export NODE_ENV=staging
export API_URL=https://staging-api.example.com
persistproc npm run start
```

### 3. Health Checks

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

### 4. Process Dependencies

Start processes in the right order:

```bash
# Start dependencies first
persistproc --start --name db docker-compose up postgres
sleep 5  # Wait for DB to be ready

# Then start services that depend on them
persistproc --start --name backend npm run dev:api
persistproc --start --name frontend npm run dev
```

### 5. Resource Management

Monitor and limit resource usage:

```bash
# Set resource limits
export PERSISTPROC_MAX_PROCESSES=10
export PERSISTPROC_MEMORY_LIMIT=2048

# Monitor usage
persistproc --list --format json | jq '.processes[] | {name: .command, cpu: .cpu_percent, memory: .memory_mb}'
```

---

These workflows demonstrate how PersistProc transforms development from manual process juggling to intelligent, agent-assisted environment management. The key is leveraging the shared process state that all your tools and agents can see and control.

**Next**: Check out specific [examples](../examples/web-development.md) for detailed implementation guidance.