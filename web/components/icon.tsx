import type { IconName } from "@/lib/site";

export function Icon({ name }: { name: IconName }) {
  const common = {
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  const paths: Record<IconName, React.ReactNode> = {
    sun: <><circle cx="12" cy="12" r="3.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/></>,
    battery: <><rect x="3" y="6" width="16" height="12" rx="2"/><path d="M21 10v4M7 10v4M11 9v6M15 11v2"/></>,
    chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/><path d="M2 19h20"/></>,
    heat: <><path d="M8 3c-2 3 2 4 0 7s2 4 0 7M14 3c-2 3 2 4 0 7s2 4 0 7M20 3c-2 3 2 4 0 7s2 4 0 7"/></>,
    balcony: <><path d="M4 21V9h16v12M2 9h20M7 9V4h10v5M8 13v8M16 13v8M4 17h16"/></>,
    car: <><path d="M5 17h14l1-5-3-5H7l-3 5 1 5Z"/><path d="M7 17v2M17 17v2M4 12h16M8 14h.01M16 14h.01"/></>,
    bolt: <path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z"/>,
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v11h14V10M9 21v-7h6v7"/></>,
    forecast: <><path d="M3 17l5-5 4 3 7-9"/><path d="M15 6h4v4"/><path d="M3 21h18"/></>,
    calculator: <><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h.01M12 19h4"/></>,
  };

  return <svg {...common}>{paths[name]}</svg>;
}
