import { Home, BarChart, Message, Calendar, Trending, File, Settings, Sun, Logout } from "./icons";

const NAV = [
  { icon: Home, active: true },
  { icon: BarChart },
  { icon: Message },
  { icon: Calendar },
  { icon: Trending },
  { icon: File },
  { icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="fixed right-0 top-9 bottom-0 z-20 flex w-14 flex-col items-center
                      border-l border-border bg-surface/60 py-4 backdrop-blur">
      <nav className="flex flex-1 flex-col items-center gap-1.5">
        {NAV.map(({ icon: Icon, active }, i) => (
          <button
            key={i}
            className={`grid h-10 w-10 place-items-center rounded-xl text-xl transition
                        ${active
                          ? "bg-accent/15 text-accent ring-1 ring-accent/30"
                          : "text-text3 hover:bg-surface2 hover:text-text1"}`}
          >
            <Icon />
          </button>
        ))}
      </nav>
      <div className="flex flex-col items-center gap-1.5">
        <button className="grid h-10 w-10 place-items-center rounded-xl text-xl text-text3 hover:bg-surface2 hover:text-text1">
          <Sun />
        </button>
        <button className="grid h-10 w-10 place-items-center rounded-xl text-xl text-text3 hover:bg-surface2 hover:text-text1">
          <Logout />
        </button>
      </div>
    </aside>
  );
}
