import { TasksBoard } from "./_components/tasks-board";

export const dynamic = "force-dynamic";

export default function CrmTasksPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tasks &amp; Calendar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every follow-up, call, and meeting across your pipeline — with recurring
          tasks, automation, and AI suggestions grounded in real CRM data.
        </p>
      </div>
      <TasksBoard />
    </div>
  );
}
