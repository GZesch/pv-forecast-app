import type { Metadata } from "next";
import { CalculatorCard } from "@/components/cards";
import { PageHero } from "@/components/page-hero";
import { calculators } from "@/lib/site";

export const metadata: Metadata = { title: "Rechner", description: "Transparente Energierechner für PV, Wirtschaftlichkeit und Stromtarife.", alternates: { canonical: "/rechner" } };

export default function CalculatorsPage() {
  return <main><PageHero eyebrow="Rechner" title="Zahlen einordnen, statt ihnen blind zu vertrauen."><p>Unsere Rechner machen Annahmen sichtbar und erklären, was Ergebnisse leisten können – und was nicht. Alle Rechner sollen ohne Account vollständig nutzbar sein.</p></PageHero><section className="section section-soft"><div className="shell"><div className="calculator-grid">{calculators.map((calculator) => <CalculatorCard key={calculator.href} {...calculator} />)}</div><div className="method-callout"><div><span className="status-label">Unser Prinzip</span><h2>Kein Ergebnis ohne Kontext</h2></div><p>Jeder Rechner wird Annahmen, Datenstand und wesentliche Einschränkungen direkt am Ergebnis ausweisen.</p></div></div></section></main>;
}
