import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";
const routes = ["", "/rechner", "/rechner/pv-forecast", "/rechner/pv-wirtschaftlichkeit", "/rechner/stromtarif", "/solar", "/speicher", "/stromtarife", "/methodik", "/ueber"];
export default function sitemap(): MetadataRoute.Sitemap { return routes.map((route) => ({ url: `${siteConfig.url}${route}`, lastModified: new Date(), changeFrequency: route === "" ? "weekly" : "monthly", priority: route === "" ? 1 : 0.7 })); }
