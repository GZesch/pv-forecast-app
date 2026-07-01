export type ScenarioResult = {
  household_consumption_kwh: number; pv_generation_kwh: number;
  direct_pv_consumption_kwh: number; battery_delivery_to_load_kwh: number;
  battery_losses_kwh: number; feed_in_kwh: number; curtailed_pv_kwh: number;
  curtailment_ratio: number | null; grid_import_kwh: number;
  self_consumption_ratio: number | null; autonomy_ratio: number | null;
  equivalent_full_cycles: number | null;
};

export type FirstYear = { without_pv: ScenarioResult; pv_only: ScenarioResult; pv_with_battery: ScenarioResult | null };
export type AnnualEconomics = {
  operating_year: number; electricity_price_eur_per_kwh: number;
  feed_in_tariff_eur_per_kwh: number; reference_electricity_cost_eur: number;
  avoided_grid_cost_eur: number; feed_in_revenue_eur: number;
  operating_cost_eur: number; one_time_cost_eur: number; cashflow_eur: number;
  cumulative_cashflow_eur: number; discounted_cashflow_eur: number;
};
export type FinancialMetrics = { available: boolean; unavailable_reason: string | null; nominal_total_eur: number | null; net_present_value_eur: number | null; payback_years: number | null };
export type ScenarioEconomics = { year_zero_cashflow_eur: number | null; annual: AnnualEconomics[]; metrics: FinancialMetrics };
export type Economics = { pv: ScenarioEconomics; package: ScenarioEconomics; incremental_battery: ScenarioEconomics };
export type FeedInLimitComparison = { limit_kw: number; base_pv_curtailed_kwh: number; limited_pv_curtailed_kwh: number; limited_battery_curtailed_kwh: number | null };
export type CalculationWarning = { code: string; severity: "info" | "warning" | string; text?: string };

export type ResponseMetadata = {
  model_version?: string; calculated_at?: string; market?: string; defaults_data_date?: string;
  assumptions?: Array<{ key?: string; value?: unknown; unit?: string; source?: string; note?: string }>;
  used_assumptions?: { years?: number; resolved_pv_operating_cost_year1_eur?: number; resolved_battery?: { usable_capacity_kwh?: number; max_charge_power_kw?: number; max_discharge_power_kw?: number; round_trip_efficiency?: number } | null; [key: string]: unknown };
  profile_source?: string; profile?: { type?: string; id?: string; source?: string; version?: string; source_url?: string | null; source_xlsx_sha256?: string | null; source_csv_sha256?: string | null };
  weather_source?: string; weather?: { radiation_database?: string | null; source_period?: string | null; api_endpoint?: string; selected_tmy_months?: Array<[number, number]>; irradiance_time_offset_hours?: number | null; retrieved_at?: string };
  eeg?: { rate_eur_per_kwh?: number; manual_override?: boolean; valid_from?: string | null; valid_to?: string | null; data_version?: string; source_url?: string };
  [key: string]: unknown;
};

export type WeatherMetrics = Omit<FinancialMetrics, "unavailable_reason">;
export type WeatherSensitivityScenario = { label: "low" | "median" | "high"; display_label: string; source_year: number; quantile: number; nearest_rank: number; annual_pv_generation_kwh: number; deviation_from_tmy_percent: number | null; first_year: FirstYear; economics: { pv: WeatherMetrics; package: WeatherMetrics; incremental_battery: WeatherMetrics } };
export type WeatherSensitivity = { scenarios: WeatherSensitivityScenario[]; distribution: { complete_year_count: number; minimum_kwh: number; median_kwh: number; maximum_kwh: number }; source_period: string; radiation_database: string; api_endpoint: string; retrieved_at: string; quantile_method: string; leap_day_normalization: string; notice: string };
export type PVEconomicsResponse = { metadata: ResponseMetadata; first_year: FirstYear; economics: Economics; feed_in_limit_comparison: FeedInLimitComparison; warnings: CalculationWarning[]; disclaimers: string[]; weather_sensitivity: WeatherSensitivity | null };

const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nullableFinite = (v: unknown) => v === null || finite(v);
const keys = ["household_consumption_kwh","pv_generation_kwh","direct_pv_consumption_kwh","battery_delivery_to_load_kwh","battery_losses_kwh","feed_in_kwh","curtailed_pv_kwh","grid_import_kwh"];
const ratioKeys = ["curtailment_ratio","self_consumption_ratio","autonomy_ratio","equivalent_full_cycles"];
const scenario = (v: unknown): v is ScenarioResult => object(v) && keys.every(k=>finite(v[k])) && ratioKeys.every(k=>nullableFinite(v[k]));
const metrics = (v: unknown, reason=true) => object(v) && typeof v.available === "boolean" && nullableFinite(v.nominal_total_eur) && nullableFinite(v.net_present_value_eur) && nullableFinite(v.payback_years) && (!v.available || (finite(v.nominal_total_eur) && finite(v.net_present_value_eur))) && (!reason || v.unavailable_reason === null || typeof v.unavailable_reason === "string");
const annual = (v: unknown) => object(v) && ["operating_year","electricity_price_eur_per_kwh","feed_in_tariff_eur_per_kwh","reference_electricity_cost_eur","avoided_grid_cost_eur","feed_in_revenue_eur","operating_cost_eur","one_time_cost_eur","cashflow_eur","cumulative_cashflow_eur","discounted_cashflow_eur"].every(k=>finite(v[k]));
const economic = (v: unknown) => object(v) && nullableFinite(v.year_zero_cashflow_eur) && Array.isArray(v.annual) && v.annual.length>0 && v.annual.every(annual) && metrics(v.metrics);
const firstYear = (v: unknown): v is FirstYear => object(v) && scenario(v.without_pv) && scenario(v.pv_only) && (v.pv_with_battery === null || scenario(v.pv_with_battery));
const weather = (v: unknown): v is WeatherSensitivity => {
  if (!object(v) || !Array.isArray(v.scenarios) || !object(v.distribution)) return false;
  if (![v.distribution.complete_year_count,v.distribution.minimum_kwh,v.distribution.median_kwh,v.distribution.maximum_kwh].every(finite)) return false;
  if (!["source_period","radiation_database","api_endpoint","retrieved_at","quantile_method","leap_day_normalization","notice"].every(k=>typeof v[k] === "string")) return false;
  return v.scenarios.length === 3 && v.scenarios.map(s=>object(s)?s.label:null).join(",") === "low,median,high" && v.scenarios.every(s=>object(s) && typeof s.display_label === "string" && [s.source_year,s.quantile,s.nearest_rank,s.annual_pv_generation_kwh].every(finite) && nullableFinite(s.deviation_from_tmy_percent) && firstYear(s.first_year) && object(s.economics) && metrics(s.economics.pv,false) && metrics(s.economics.package,false) && metrics(s.economics.incremental_battery,false));
};

export function isPVEconomicsResponse(v: unknown): v is PVEconomicsResponse {
  if (!object(v) || !object(v.metadata) || !firstYear(v.first_year) || !object(v.economics) || !object(v.feed_in_limit_comparison)) return false;
  if (!economic(v.economics.pv) || !economic(v.economics.package) || !economic(v.economics.incremental_battery)) return false;
  const comparison=v.feed_in_limit_comparison;
  if (!["limit_kw","base_pv_curtailed_kwh","limited_pv_curtailed_kwh"].every(k=>finite(comparison[k])) || !nullableFinite(comparison.limited_battery_curtailed_kwh)) return false;
  if (!Array.isArray(v.warnings) || !v.warnings.every(w=>object(w) && typeof w.code === "string" && typeof w.severity === "string") || !Array.isArray(v.disclaimers) || !v.disclaimers.every(x=>typeof x === "string")) return false;
  return v.weather_sensitivity === null || weather(v.weather_sensitivity);
}

const nf = (options: Intl.NumberFormatOptions) => new Intl.NumberFormat("de-DE", options);
export const formatEuro = (v: number | null) => finite(v) ? nf({style:"currency",currency:"EUR",maximumFractionDigits:0}).format(v) : "Nicht verfügbar";
export const formatKwh = (v: number | null) => finite(v) ? `${nf({maximumFractionDigits:0}).format(v)} kWh` : "–";
export const formatKw = (v: number | null) => finite(v) ? `${nf({maximumFractionDigits:1}).format(v)} kW` : "–";
export const formatPercent = (v: number | null, fraction=true) => finite(v) ? nf({style:"percent",maximumFractionDigits:1}).format(fraction?v:v/100) : "–";
export const formatYears = (v: number | null, horizon?: number) => !finite(v) ? (horizon ? "Nicht innerhalb des Betrachtungszeitraums" : "Nicht verfügbar") : `${nf({maximumFractionDigits:1}).format(v)} Jahre`;
export const formatDateTime = (v?: string) => { if(!v)return "–"; const d=new Date(v); return Number.isNaN(d.valueOf())?"–":new Intl.DateTimeFormat("de-DE",{dateStyle:"medium",timeStyle:"short"}).format(d); };
export const formatDate = (v?: string | null) => { if(!v)return "–"; const parts=/^(\d{4})-(\d{2})-(\d{2})$/.exec(v); return parts?`${parts[3]}.${parts[2]}.${parts[1]}`:"–"; };

const warningTexts: Record<string,string> = {
  STANDARD_LOAD_PROFILE:"Das BDEW-H25-Standardlastprofil ist keine individuelle Verbrauchsmessung.", SYNTHETIC_LOAD_PROFILE:"Das gewählte ExergyPulse-Lastprofil ist ein synthetisches Modellprofil.", PACKAGE_PRICE_NOT_SPLIT:"Der Paketpreis konnte nicht auf PV und Speicher aufgeteilt werden; einzelne Investitionskennzahlen sind daher eingeschränkt.", BATTERY_NEGATIVE_NPV:"Der zusätzliche Kapitalwert des Speichers ist unter den eingegebenen Annahmen negativ.", BATTERY_NO_PAYBACK:"Der Speicher amortisiert sich zusätzlich zur PV nicht innerhalb des Betrachtungszeitraums.", PV_NO_PAYBACK:"Die PV-Anlage amortisiert sich im Modell nicht innerhalb des Betrachtungszeitraums.", REPLACEMENT_COSTS_NOT_INCLUDED:"Automatische Ersatzinvestitionen für Speicher oder Wechselrichter sind nicht berücksichtigt.", FEED_IN_LIMIT_NOT_IN_BASE_CASE:"Die zusätzliche 60-%-Betrachtung ist ein Erstjahresvergleich und nicht Teil des Basisszenarios.", FEED_IN_TARIFF_MANUAL_OVERRIDE:"Die Einspeisevergütung wurde manuell vorgegeben.", TMY_NOT_FORECAST:"Das typische meteorologische Jahr von PVGIS ist keine Wetterprognose.", SHADING_SIMPLIFIED:"Verschattung vermindert nur den direkten Einstrahlungsanteil.", ELECTRICAL_PARTIAL_SHADING_NOT_MODELLED:"Module, Strings und Bypassdioden werden bei Teilverschattung nicht elektrisch modelliert.", BATTERY_WARRANTY_IS_BOUNDARY:"Garantieangaben sind Modellgrenzen und keine erwartete Alterungsprognose.", CALCULATION_ORIENTATION_ONLY:"Die Berechnung dient der Orientierung und ist kein Angebotsurteil."
};
export const warningText = (code:string) => warningTexts[code] || "Allgemeiner Modellhinweis; Details sind in dieser Oberfläche noch nicht weiter klassifiziert.";
export const isEconomicWarning = (code:string) => ["PACKAGE_PRICE_NOT_SPLIT","BATTERY_NEGATIVE_NPV","BATTERY_NO_PAYBACK","PV_NO_PAYBACK"].includes(code);
export const unavailableReason = (reason:string|null) => reason?.includes("PV investment") ? "PV-Investitionskosten sind nicht getrennt verfügbar." : reason?.includes("package") || reason?.includes("Total package") ? "Der Gesamtpreis ist nicht verfügbar." : reason?.includes("Battery") ? "Der Speichermehrpreis ist nicht getrennt verfügbar." : "Die Kennzahl ist für diese Eingaben nicht verfügbar.";
export const cashflowSeries = (value:ScenarioEconomics) => value.year_zero_cashflow_eur === null ? [] : [{year:0,value:value.year_zero_cashflow_eur},...value.annual.map(x=>({year:x.operating_year,value:x.cumulative_cashflow_eur}))];
export const batteryComparison = (first:FirstYear) => first.pv_with_battery ? { avoidedGridKwh:first.pv_only.grid_import_kwh-first.pv_with_battery.grid_import_kwh, feedInChangeKwh:first.pv_with_battery.feed_in_kwh-first.pv_only.feed_in_kwh, autonomyChange:first.pv_with_battery.autonomy_ratio===null||first.pv_only.autonomy_ratio===null?null:first.pv_with_battery.autonomy_ratio-first.pv_only.autonomy_ratio } : null;
export const pvStatement = (m:FinancialMetrics) => !m.available ? "Die PV-Wirtschaftlichkeit kann wegen fehlender Investitionsangaben nicht vollständig bewertet werden." : m.payback_years===null ? "Die PV amortisiert sich im Modell nicht innerhalb des Betrachtungszeitraums." : "Die PV amortisiert sich im Modell innerhalb des Betrachtungszeitraums.";
export const batteryStatement = (m:FinancialMetrics, first:FirstYear) => { const c=batteryComparison(first); if(!c)return ""; if(!m.available)return "Der Speicherbeitrag ist energetisch sichtbar; seine zusätzliche Wirtschaftlichkeit ist wegen fehlender Preisaufteilung nicht vollständig verfügbar."; return `Der Speicher verändert den Autarkiegrad um ${formatPercent(c.autonomyChange)} und ${m.net_present_value_eur!==null&&m.net_present_value_eur>=0?"erreicht":"erreicht nicht"} einen positiven zusätzlichen Kapitalwert.`; };
