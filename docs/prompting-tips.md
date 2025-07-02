# Prompting Tips for Web Development

This page provides examples of how to effectively use an AI agent with `persistproc` in a realistic web development workflow. The key is to let the agent manage the background processes for you.

## Scenario: Managing a Web Server

Let's assume you have a typical web project (e.g., Next.js, Django, Vite) and you've already started the `persistproc` server.

### Starting Your Dev Server

First, start your development server as a managed process. You only need to do this once from your terminal.

```bash
# In your project directory
persistproc npm run dev
```

The server is now running in the background. You can close the terminal where you ran this command. Now, you can use your AI agent to interact with it.

### Example Prompts

Here are some prompts you could give your agent throughout your development session.

---

**Prompt 1: Checking the Status**

> "Is the dev server running? Show me the running processes."

**Agent Action**: The agent calls `list_processes()` and shows you the output, confirming that `npm run dev` is active.

---

**Prompt 2: Debugging an Error**

You've made some code changes, and now your browser shows an error.

> "I think I just broke the app. Can you check the server logs for any recent errors?"

**Agent Action**: The agent calls `get_process_output(pid=..., stream="stderr", lines=50)`. It can then analyze the errors and suggest a fix.

---

**Prompt 3: Restarting After a Change**

You've just changed a configuration file that requires a manual restart (e.g., `tailwind.config.js`).

> "I just updated the Tailwind config. Please restart the dev server for me."

**Agent Action**: The agent finds the process and calls `restart_process(pid=...)`. It can then monitor the logs with `get_process_output` to confirm it started up correctly.

---

**Prompt 4: Running a Related Task**

You need to run a database migration or a code generator alongside your dev server.

> "Run the database migrations using `npm run db:migrate`."

**Agent Action**: The agent calls `start_process(command="npm run db:migrate")`. This new process now runs alongside your dev server, and the agent can report back when it's finished. This avoids the need to open another terminal tab just for a one-off task. 