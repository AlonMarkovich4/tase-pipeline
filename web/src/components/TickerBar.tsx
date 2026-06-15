import { TICKER, type Quote } from "@/lib/data";

function Chip({ q }: { q: Quote }) {
  const up = q.pct >= 0;
  return (
    <span className="flex items-center gap-2 whitespace-nowrap px-4 text-xs">
      <span className="font-semibold text-text1">{q.sym}</span>
      <span className="text-text2">{q.price}</span>
      <span className={up ? "text-pos" : "text-neg"}>
        {up ? "▲" : "▼"} {Math.abs(q.pct).toFixed(2)}%
      </span>
    </span>
  );
}

export default function TickerBar() {
  const row = [...TICKER, ...TICKER]; // duplicate for seamless loop
  return (
    <div className="fixed inset-x-0 top-0 z-30 h-9 overflow-hidden border-b border-border bg-surface/80 backdrop-blur">
      <div className="animate-ticker flex h-9 w-max items-center">
        {row.map((q, i) => (
          <span key={i} className="flex items-center">
            <Chip q={q} />
            <span className="text-text3">·</span>
          </span>
        ))}
      </div>
    </div>
  );
}
