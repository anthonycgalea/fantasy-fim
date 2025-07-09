import { createLazyFileRoute } from "@tanstack/react-router";

export const Route = createLazyFileRoute("/")({
  component: Index,
});

function Index() {
  return (
    <div className="p-2 space-y-4">
      <h1 className="text-2xl font-bold">Welcome to Fantasy FiM!</h1>
      <p>
        Fantasy FiM lets you create leagues, draft robotics teams and track
        their progress in FIRST in Michigan competitions.
      </p>
    </div>
  );
}
