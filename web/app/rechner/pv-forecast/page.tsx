import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";
export const metadata: Metadata = { title: "PV-Forecast", description: "Der neutrale PV-Ertragsforecast ist in Vorbereitung.", alternates: { canonical: "/rechner/pv-forecast" } };
export default function Page() { return <ComingSoon title="PV-Forecast" description="Eine wetterbasierte Prognose für den erwarteten Ertrag deiner Photovoltaikanlage – nachvollziehbar und ohne dauerhafte Speicherung für Gäste." icon="forecast" points={["Standort, Leistung, Ausrichtung und Neigung berücksichtigen", "Stündliche und tägliche Ertragsprognose darstellen", "Wettergrundlage und Berechnungsannahmen offenlegen", "Vollständig ohne Account nutzbar sein"]} />; }
