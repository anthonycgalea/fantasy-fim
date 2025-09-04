import { createRootRoute, Outlet } from "@tanstack/react-router";
import { TanStackRouterDevtools } from "@tanstack/router-devtools";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import Navbar from "@/components/Navbar";

const showDevtools = import.meta.env.DEV;

export const Route = createRootRoute({
  component: () => (
    <>
      <div className="flex flex-col min-h-screen bg-background px-8 mt-4">
        <Navbar />
        <Outlet />
        <footer className="mt-auto border-t py-4 text-center">
          Powered by{' '}
          <a
            href="https://www.thebluealliance.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold hover:underline"
          >
            The Blue Alliance
          </a>
        </footer>
      </div>
      {showDevtools && <TanStackRouterDevtools />}
      {showDevtools && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  ),
});
