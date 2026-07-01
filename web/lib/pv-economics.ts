export type InvestmentInput = { pv: string; battery: string; package: string };

export type SurfaceForm = {
  key: string; identifier: string; peakPower: string; azimuth: string; tilt: string;
  inverterEfficiency: string; systemLoss: string; maxAcPower: string;
  shadingMode: "constant" | "matrix"; constantShading: string; shadingMatrix: string[][];
};

export type FormValues = {
  annualConsumption: string; federalState: string; commissioningDate: string;
  latitude: string; longitude: string; profileKind: string; surfaces: SurfaceForm[];
  batteryEnabled: boolean; batteryCapacity: string; batteryRte: string;
  chargePower: string; dischargePower: string; chargeAutomatic: boolean; dischargeAutomatic: boolean;
  warrantyModel: boolean; warrantyYears: string; residualCapacity: string;
  warrantyLimitKind: "throughput" | "efc"; warrantedThroughput: string; warrantedEfc: string;
  electricityPrice: string; investments: InvestmentInput; manualTariff: string;
  years: string; pvDegradation: string; batteryDegradation: string;
  electricityGrowth: string; operatingCostGrowth: string; discountRate: string;
  pvOperatingCost: string; pvOperatingCostAutomatic: boolean; batteryOperatingCost: string;
  postEegValue: string; feedInLimitKind: "none" | "kw" | "percent";
  feedInLimit: string; feedInLimitYears: string;
};

export type FieldErrors = Record<string, string>;
export type InvestmentResolution = { pv: number | null; battery: number | null; package: number | null; error?: string };

const number = (value: string) => value.trim() === "" ? null : Number(value.replace(",", "."));
export const percentToFraction = (value: string) => { const n = number(value); return n === null ? null : n / 100; };
export const centsToEuros = (value: string) => { const n = number(value); return n === null ? null : n / 100; };
export const halfCPower = (capacity: string) => { const n = number(capacity); return n === null || !Number.isFinite(n) ? "" : String(Math.round(n * 50) / 100); };

export function resolveInvestments(input: InvestmentInput, batteryEnabled: boolean): InvestmentResolution {
  const pv = number(input.pv), battery = batteryEnabled ? number(input.battery) : null, packagePrice = number(input.package);
  const values = [pv, battery, packagePrice].filter((v): v is number => v !== null);
  if (values.some((v) => !Number.isFinite(v) || v < 0)) return { pv, battery, package: packagePrice, error: "Investitionswerte müssen Zahlen ab 0 € sein." };
  if (!batteryEnabled) return { pv: pv ?? packagePrice, battery: null, package: packagePrice ?? pv };
  if (values.length === 3 && Math.abs((pv! + battery!) - packagePrice!) > .01) return { pv, battery, package: packagePrice, error: "Paketpreis muss PV-Preis plus Speichermehrpreis entsprechen." };
  if (values.length === 2) {
    if (pv === null) return packagePrice! < battery! ? { pv, battery, package: packagePrice, error: "Der Paketpreis ist kleiner als der Speichermehrpreis." } : { pv: packagePrice! - battery!, battery, package: packagePrice };
    if (battery === null) return packagePrice! < pv ? { pv, battery, package: packagePrice, error: "Der Paketpreis ist kleiner als der PV-Preis." } : { pv, battery: packagePrice! - pv, package: packagePrice };
    return { pv, battery, package: pv + battery };
  }
  return { pv, battery, package: packagePrice };
}

const inRange = (value: string, min: number, max: number, required = true) => {
  const n = number(value);
  if (n === null) return required ? "Dieses Feld ist erforderlich." : undefined;
  if (!Number.isFinite(n) || n < min || n > max) return `Bitte einen Wert zwischen ${min} und ${max} eingeben.`;
};

export function tariffNeedsManual(date: string) { return !!date && (date < "2026-02-01" || date > "2026-07-31"); }

export function validateForm(v: FormValues): FieldErrors {
  const e: FieldErrors = {};
  const check = (key: string, value: string, min: number, max: number, required = true) => { const message = inRange(value, min, max, required); if (message) e[key] = message; };
  check("annualConsumption", v.annualConsumption, .01, 1e9); check("latitude", v.latitude, -90, 90); check("longitude", v.longitude, -180, 180);
  if (!v.federalState) e.federalState = "Bitte ein Bundesland auswählen.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.commissioningDate) || Number.isNaN(Date.parse(`${v.commissioningDate}T00:00:00Z`))) e.commissioningDate = "Bitte ein gültiges Inbetriebnahmedatum eingeben.";
  if (!v.surfaces.length) e.surfaces = "Mindestens eine PV-Teilfläche ist erforderlich.";
  const ids = new Set<string>();
  v.surfaces.forEach((s, i) => {
    const p = `surfaces.${i}.`;
    if (!s.identifier.trim()) e[p + "identifier"] = "Bitte eine eindeutige Bezeichnung eingeben.";
    else if (ids.has(s.identifier.trim())) e[p + "identifier"] = "Diese Bezeichnung wird bereits verwendet."; else ids.add(s.identifier.trim());
    check(p + "peakPower", s.peakPower, .000001, 100); check(p + "azimuth", s.azimuth, 0, 360); check(p + "tilt", s.tilt, 0, 90);
    check(p + "inverterEfficiency", s.inverterEfficiency, .000001, 100); check(p + "systemLoss", s.systemLoss, 0, 99.999999);
    check(p + "maxAcPower", s.maxAcPower, .000001, 1e9, false); check(p + "constantShading", s.constantShading, 0, 100, s.shadingMode === "constant");
    if (s.shadingMode === "matrix") s.shadingMatrix.forEach((row, month) => row.forEach((cell, hour) => check(`${p}matrix.${month}.${hour}`, cell, 0, 100)));
  });
  if (v.batteryEnabled) {
    check("batteryCapacity", v.batteryCapacity, .000001, 1e9); check("batteryRte", v.batteryRte, .000001, 100);
    check("chargePower", v.chargePower, 0, 1e9); check("dischargePower", v.dischargePower, 0, 1e9);
    if (v.warrantyModel) {
      check("warrantyYears", v.warrantyYears, .000001, 1e9); check("residualCapacity", v.residualCapacity, 0, 100);
      check(v.warrantyLimitKind === "throughput" ? "warrantedThroughput" : "warrantedEfc", v.warrantyLimitKind === "throughput" ? v.warrantedThroughput : v.warrantedEfc, .000001, 1e12);
    }
  }
  check("electricityPrice", v.electricityPrice, .000001, 1e9);
  const investment = resolveInvestments(v.investments, v.batteryEnabled);
  const hasInvestment = [v.investments.pv, v.investments.package, v.batteryEnabled ? v.investments.battery : ""].some((value) => value.trim() !== "");
  if (!hasInvestment) e.investments = "Bitte mindestens einen Investitionswert eingeben.";
  else if (investment.error) e.investments = investment.error;
  const packageOnlyWithBattery = v.batteryEnabled && v.investments.package.trim() !== "" && v.investments.pv.trim() === "" && v.investments.battery.trim() === "";
  if (packageOnlyWithBattery && v.pvOperatingCost.trim() === "") e.pvOperatingCost = "Bei ausschließlich bekanntem Paketpreis müssen die jährlichen PV-Betriebskosten ausdrücklich angegeben werden.";
  if (tariffNeedsManual(v.commissioningDate)) check("manualTariff", v.manualTariff, 0, 1e9); else check("manualTariff", v.manualTariff, 0, 1e9, false);
  check("years", v.years, 1, 40); check("pvDegradation", v.pvDegradation, 0, 99.999999); check("batteryDegradation", v.batteryDegradation, 0, 99.999999);
  check("electricityGrowth", v.electricityGrowth, -99.999999, 1e6); check("operatingCostGrowth", v.operatingCostGrowth, -99.999999, 1e6); check("discountRate", v.discountRate, -99.999999, 1e6);
  check("pvOperatingCost", v.pvOperatingCost, 0, 1e12, false); check("batteryOperatingCost", v.batteryOperatingCost, 0, 1e12); check("postEegValue", v.postEegValue, 0, 1e12);
  if (v.feedInLimitKind !== "none") { check("feedInLimit", v.feedInLimit, 0, v.feedInLimitKind === "percent" ? 100 : 1e9); check("feedInLimitYears", v.feedInLimitYears, 1, Number(v.years) || 40); }
  return e;
}

export function buildRequest(v: FormValues) {
  const investment = resolveInvestments(v.investments, v.batteryEnabled);
  const pvOpex = number(v.pvOperatingCost);
  return {
    latitude: number(v.latitude), longitude: number(v.longitude), federal_state: v.federalState,
    annual_consumption_kwh: number(v.annualConsumption), profile_kind: v.profileKind,
    has_heat_pump: false, has_electric_vehicle: false,
    pv_surfaces: v.surfaces.map((s) => ({
      identifier: s.identifier.trim(), peak_power_kwp: number(s.peakPower), azimuth_deg: number(s.azimuth), tilt_deg: number(s.tilt),
      inverter_efficiency: percentToFraction(s.inverterEfficiency), system_loss_fraction: percentToFraction(s.systemLoss),
      max_ac_power_kw: number(s.maxAcPower), constant_shading_factor: s.shadingMode === "constant" ? percentToFraction(s.constantShading) : null,
      shading_matrix: s.shadingMode === "matrix" ? s.shadingMatrix.map((row) => row.map((x) => percentToFraction(x))) : null,
    })),
    battery: v.batteryEnabled ? {
      usable_capacity_kwh: number(v.batteryCapacity), round_trip_efficiency: percentToFraction(v.batteryRte), max_charge_power_kw: number(v.chargePower), max_discharge_power_kw: number(v.dischargePower),
      degradation_kind: v.warrantyModel ? "warranty" : "standard", residual_capacity_fraction: v.warrantyModel ? percentToFraction(v.residualCapacity) : null,
      warranty_years: v.warrantyModel ? number(v.warrantyYears) : null,
      warranted_throughput_kwh: v.warrantyModel && v.warrantyLimitKind === "throughput" ? number(v.warrantedThroughput) : null,
      warranted_efc: v.warrantyModel && v.warrantyLimitKind === "efc" ? number(v.warrantedEfc) : null,
    } : null,
    electricity_price_eur_per_kwh: centsToEuros(v.electricityPrice), commissioning_date: v.commissioningDate,
    manual_feed_in_tariff_eur_per_kwh: centsToEuros(v.manualTariff), pv_investment_eur: investment.pv,
    battery_incremental_investment_eur: v.batteryEnabled ? investment.battery : null, package_investment_eur: investment.package,
    assumptions: {
      years: number(v.years), pv_degradation_rate: percentToFraction(v.pvDegradation), battery_capacity_loss_rate: percentToFraction(v.batteryDegradation),
      electricity_price_growth_rate: percentToFraction(v.electricityGrowth), operating_cost_growth_rate: percentToFraction(v.operatingCostGrowth), nominal_discount_rate: percentToFraction(v.discountRate),
      pv_operating_cost_year1_eur: pvOpex, battery_operating_cost_year1_eur: number(v.batteryOperatingCost), post_eeg_value_eur_per_kwh: number(v.postEegValue),
      max_feed_in_power_kw: v.feedInLimitKind === "kw" ? number(v.feedInLimit) : null, max_feed_in_percent: v.feedInLimitKind === "percent" ? number(v.feedInLimit) : null,
      feed_in_limit_years: v.feedInLimitKind === "none" ? 0 : number(v.feedInLimitYears),
    }, one_time_costs: [],
  };
}

export function normalizeApiError(status: number, body: unknown): string[] {
  if (status === 422 && body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (Array.isArray(detail)) {
      const labels: Record<string, string> = { pv_surfaces: "PV-Teilflächen", battery: "Speicher", assumptions: "Expertenannahmen", commissioning_date: "Inbetriebnahmedatum", manual_feed_in_tariff_eur_per_kwh: "Einspeisevergütung" };
      return (detail as Array<{loc?: unknown[]; msg?: string}>).map((item) => {
        const path = item.loc?.slice(1).map((part) => labels[String(part)] || String(part)).join(" → ") || "Eingabe";
        const message = item.msg?.replace(/^Value error,\s*/i, "") || "Der Wert ist ungültig.";
        return `${path}: ${message}`;
      });
    }
    if (typeof detail === "string") {
      const lower = detail.toLowerCase();
      if (lower.includes("tariff") || lower.includes("eeg")) return ["Für dieses Inbetriebnahmedatum ist eine manuelle Einspeisevergütung erforderlich."];
      if (lower.includes("operating cost")) return ["Die jährlichen PV-Betriebskosten müssen für diese Investitionsangaben ausdrücklich angegeben werden."];
      return ["Die Eingaben konnten fachlich nicht verarbeitet werden. Bitte prüfe die Angaben und Annahmen."];
    }
  }
  if (status === 503) return ["Die Berechnung ist momentan nicht erreichbar. Bitte versuche es später erneut."];
  if (status === 502) return ["Ein externer Wetterdienst hat keine verwertbare Antwort geliefert. Bitte versuche es später erneut."];
  if (status === 500) return ["Bei der Berechnung ist ein interner Fehler aufgetreten. Es wurden keine Ergebnisse gespeichert."];
  return ["Die Berechnung konnte nicht abgeschlossen werden. Bitte versuche es später erneut."];
}
