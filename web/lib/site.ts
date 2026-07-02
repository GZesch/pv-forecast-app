export function normalizePublicUrl(value: string | undefined, fallback: string): string {
  const configuredValue = value?.trim() || fallback;
  const normalizedValue = /^https?:\/\//i.test(configuredValue)
    ? configuredValue
    : `https://${configuredValue}`;

  new URL(normalizedValue);
  return normalizedValue;
}

export const siteConfig = {
  name: "ExergyPulse",
  claim: "Energie verstehen. Selbstbestimmt entscheiden.",
  title: "ExergyPulse – Energie verstehen. Selbstbestimmt entscheiden.",
  description:
    "Neutrales Wissen und transparente Rechner rund um Solarenergie, Speicher und Stromtarife.",
  url: normalizePublicUrl(process.env.NEXT_PUBLIC_SITE_URL, "http://localhost:3000"),
};

export const mainNavigation = [
  { label: "Wissen", href: "/#themen" },
  { label: "Rechner", href: "/rechner" },
  { label: "Strompreise", href: "/stromtarife" },
  { label: "Methodik", href: "/methodik" },
  { label: "Über ExergyPulse", href: "/ueber" },
];

export type IconName =
  | "sun"
  | "battery"
  | "chart"
  | "heat"
  | "balcony"
  | "car"
  | "bolt"
  | "home"
  | "forecast"
  | "calculator";

export const topics: Array<{
  title: string;
  description: string;
  href?: string;
  icon: IconName;
  status?: string;
}> = [
  {
    title: "Solar",
    description: "Ertrag, Auslegung und Betrieb einer Photovoltaikanlage verstehen.",
    href: "/solar",
    icon: "sun",
  },
  {
    title: "Speicher",
    description: "Kapazität, Eigenverbrauch und wirtschaftliche Grenzen einordnen.",
    href: "/speicher",
    icon: "battery",
  },
  {
    title: "Stromtarife",
    description: "Fixpreise und dynamische Modelle sachlich vergleichen.",
    href: "/stromtarife",
    icon: "chart",
  },
  {
    title: "Wärmepumpe",
    description: "Strombedarf, Effizienz und Zusammenspiel mit PV nachvollziehen.",
    icon: "heat",
    status: "Geplant",
  },
  {
    title: "Balkonkraftwerk",
    description: "Kleine PV-Anlagen realistisch bewerten und passend dimensionieren.",
    icon: "balcony",
    status: "Geplant",
  },
  {
    title: "E-Auto laden",
    description: "Ladezeiten, Kosten und den eigenen Solarstrom zusammen denken.",
    icon: "car",
    status: "Geplant",
  },
  {
    title: "Strompreise",
    description: "Preisbestandteile, Börsenpreise und zeitliche Schwankungen verstehen.",
    href: "/stromtarife",
    icon: "bolt",
  },
  {
    title: "Sanierung",
    description: "Energetische Maßnahmen strukturiert einordnen und priorisieren.",
    icon: "home",
    status: "Geplant",
  },
];

export const calculators = [
  {
    title: "PV-Forecast",
    description:
      "Schätze den zu erwartenden PV-Ertrag anhand von Standort, Ausrichtung und Wetterdaten.",
    href: "/rechner/pv-forecast",
    icon: "forecast" as IconName,
    status: "Im bisherigen Bereich",
  },
  {
    title: "PV-Wirtschaftlichkeit",
    description:
      "Ordne Investition, Eigenverbrauch und mögliche Erträge mit transparenten Annahmen ein.",
    href: "/rechner/pv-wirtschaftlichkeit",
    icon: "sun" as IconName,
    status: "In Vorbereitung",
  },
  {
    title: "Stromtarif-Szenarien",
    description:
      "Vergleiche einen Fixpreis mit einem modellierten dynamischen Tarif und flexiblen Lasten.",
    href: "/rechner/stromtarif",
    icon: "calculator" as IconName,
    status: "In Vorbereitung",
  },
];
