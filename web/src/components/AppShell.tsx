import Sidebar from "./Sidebar";
import { Boost } from "./icons";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative z-10 min-h-screen">
      <Sidebar />
      {/* main content: clear of the right rail (pr-14) */}
      <div className="pr-14">
        {/* brand bar */}
        <div className="flex items-center justify-end gap-2 px-6 py-4">
          <span className="text-lg font-bold tracking-tight text-text1">TRADE BOOST</span>
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent/15 text-accent text-xl ring-1 ring-accent/30">
            <Boost />
          </span>
        </div>
        <main className="mx-auto max-w-[1400px] px-6 pb-16">{children}</main>
      </div>
    </div>
  );
}
