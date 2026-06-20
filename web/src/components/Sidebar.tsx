"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, BarChart, Message, Calendar, Trending, File, Settings, Sun, Moon, Logout } from "./icons";

const NAV = [
  { icon: Home, href: "/" },
  { icon: Trending, href: "/simulator" },
  { icon: BarChart, href: "/demo" },
  { icon: File, href: "/strategies" },
  { icon: Calendar, href: "/calendar" },
  { icon: Message, href: "/alerts" },
  { icon: Settings, href: "/settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [light, setLight] = useState(false);
  useEffect(() => setLight(document.documentElement.classList.contains("light")), []);
  const toggleTheme = () => {
    const next = !light;
    setLight(next);
    document.documentElement.classList.toggle("light", next);
    try { localStorage.setItem("theme", next ? "light" : "dark"); } catch {}
  };
  return (
    <aside className="fixed right-0 top-0 bottom-0 z-20 flex w-14 flex-col items-center
                      border-l border-border bg-surface/60 py-4 backdrop-blur">
      <nav className="flex flex-1 flex-col items-center gap-1.5">
        {NAV.map(({ icon: Icon, href }, i) => {
          const active = href !== "#" && (href === "/" ? pathname === "/" : pathname.startsWith(href));
          return (
            <Link
              key={i}
              href={href}
              className={`grid h-10 w-10 place-items-center rounded-xl text-xl transition
                          ${active
                            ? "bg-accent/15 text-accent ring-1 ring-accent/30"
                            : "text-text3 hover:bg-surface2 hover:text-text1"}`}
            >
              <Icon />
            </Link>
          );
        })}
      </nav>
      <div className="flex flex-col items-center gap-1.5">
        <button onClick={toggleTheme} aria-label="החלף מצב תצוגה"
          className="grid h-10 w-10 place-items-center rounded-xl text-xl text-text3 hover:bg-surface2 hover:text-text1">
          {light ? <Moon /> : <Sun />}
        </button>
        <button className="grid h-10 w-10 place-items-center rounded-xl text-xl text-text3 hover:bg-surface2 hover:text-text1">
          <Logout />
        </button>
      </div>
    </aside>
  );
}
