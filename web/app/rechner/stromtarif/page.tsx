import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";
export const metadata: Metadata = { title: "Stromtarif-Szenarien", description: "Der Rechner für Fixpreis- und dynamische Tarifszenarien ist in Vorbereitung.", alternates: { canonical: "/rechner/stromtarif" } };
export default function Page() { return <ComingSoon title="Stromtarif-Szenarien" description="Ein sachlicher Vergleich zwischen einem eingegebenen Fixpreis und einem modellierten dynamischen Tarif – ohne Anbieter-Ranking." icon="calculator" points={["Arbeitspreis und Grundpreis berücksichtigen", "Dynamischen Durchschnittspreis als Annahme modellieren", "Flexible Verbraucher und Lastverschiebung untersuchen", "Preisrisiken und Sensitivitäten sichtbar machen"]} />; }
