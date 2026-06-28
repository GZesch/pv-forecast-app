import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";
export const metadata: Metadata = { title: "PV-Wirtschaftlichkeit", description: "Der Rechner für PV-Wirtschaftlichkeit ist in Vorbereitung.", alternates: { canonical: "/rechner/pv-wirtschaftlichkeit" } };
export default function Page() { return <ComingSoon title="PV-Wirtschaftlichkeit" description="Ein transparenter Szenariorechner für Investition, Eigenverbrauch und mögliche Erträge einer PV-Anlage." icon="sun" points={["Investition, Betriebskosten und Finanzierung abbilden", "Eigenverbrauch und Einspeisung als Szenarien vergleichen", "Sensitivitäten statt scheinpräziser Einzelwerte zeigen", "Deutsche Rahmenbedingungen ausdrücklich kennzeichnen"]} />; }
