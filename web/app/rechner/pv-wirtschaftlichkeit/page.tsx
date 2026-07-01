import type { Metadata } from "next";
import { PVEconomicsForm } from "./pv-economics-form";

export const metadata: Metadata = {
  title: "PV-Wirtschaftlichkeit",
  description: "Transparenter Angebotscheck für private PV-Anlagen und Heimspeicher.",
  alternates: { canonical: "/rechner/pv-wirtschaftlichkeit" },
};

export default function Page() {
  return <main><section className="page-hero"><div className="shell narrow"><p className="eyebrow">Angebotscheck</p><h1>PV-Wirtschaftlichkeit</h1><p className="page-intro">Vergleiche eine konkrete PV-Konfiguration mit und ohne Heimspeicher. Keine Blackbox. Du kannst nachvollziehen, wie Ergebnisse entstehen.</p></div></section><PVEconomicsForm /></main>;
}
