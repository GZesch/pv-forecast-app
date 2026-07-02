import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

type NominatimAddress = Record<string, string | undefined>;
type NominatimResult = { place_id?: number; display_name?: string; lat?: string; lon?: string; address?: NominatimAddress };
type GeocodingResult = { id: string; label: string; latitude: number; longitude: number; countryCode: string; federalState: string | null };

const cache = new Map<string, { expires: number; results: GeocodingResult[] }>();
let nextRequestAt = 0;
let requestQueue = Promise.resolve();

const stateNames: Record<string, string> = {
  "baden-württemberg":"BW", bayern:"BY", berlin:"BE", brandenburg:"BB", bremen:"HB", hamburg:"HH",
  hessen:"HE", "mecklenburg-vorpommern":"MV", niedersachsen:"NI", "nordrhein-westfalen":"NW",
  "rheinland-pfalz":"RP", saarland:"SL", sachsen:"SN", "sachsen-anhalt":"ST", "schleswig-holstein":"SH", thüringen:"TH",
};

function federalState(address: NominatimAddress | undefined) {
  const iso = address?.["ISO3166-2-lvl4"];
  if (iso?.startsWith("DE-") && iso.length === 5) return iso.slice(3);
  return address?.state ? stateNames[address.state.toLocaleLowerCase("de-DE")] ?? null : null;
}

function waitForRateLimit() {
  const task = requestQueue.then(async () => {
    const wait = Math.max(0, nextRequestAt - Date.now());
    if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
    nextRequestAt = Date.now() + 1_050;
  });
  requestQueue = task.catch(() => undefined);
  return task;
}

export async function POST(request: NextRequest) {
  const input: unknown = await request.json().catch(() => null);
  const query = input && typeof input === "object" && "query" in input && typeof input.query === "string" ? input.query.trim() : "";
  if (query.length < 2 || query.length > 120) return NextResponse.json({ detail: "Bitte gib mindestens zwei und höchstens 120 Zeichen ein." }, { status: 400 });
  const key = query.toLocaleLowerCase("de-DE");
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return NextResponse.json({ results: cached.results, attribution: "© OpenStreetMap-Mitwirkende" });

  await waitForRateLimit();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  try {
    const baseUrl = (process.env.NOMINATIM_BASE_URL || "https://nominatim.openstreetmap.org").replace(/\/$/, "");
    const params = new URLSearchParams({ q: query, format: "jsonv2", addressdetails: "1", limit: "5", "accept-language": "de" });
    const response = await fetch(`${baseUrl}/search?${params}`, {
      headers: { accept: "application/json", "user-agent": process.env.NOMINATIM_USER_AGENT || "ExergyPulse/1.0 (https://exergypulse.de)" },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Nominatim returned ${response.status}`);
    const body = await response.json() as NominatimResult[];
    const results = body.flatMap((item): GeocodingResult[] => {
      const latitude = Number(item.lat), longitude = Number(item.lon);
      if (!item.display_name || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return [];
      return [{ id: String(item.place_id ?? `${latitude}-${longitude}`), label: item.display_name, latitude, longitude, countryCode: item.address?.country_code?.toLowerCase() ?? "", federalState: federalState(item.address) }];
    });
    if (cache.size >= 500) cache.delete(cache.keys().next().value as string);
    cache.set(key, { expires: Date.now() + 24 * 60 * 60 * 1_000, results });
    return NextResponse.json({ results, attribution: "© OpenStreetMap-Mitwirkende" });
  } catch {
    return NextResponse.json({ detail: "Die Standortsuche ist momentan nicht erreichbar. Bitte versuche es später erneut." }, { status: 503 });
  } finally { clearTimeout(timeout); }
}
