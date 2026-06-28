import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function NotFound() { return <main className="not-found"><div className="shell narrow"><p className="eyebrow">Fehler 404</p><h1>Diese Seite gibt es nicht.</h1><p className="lead">Vielleicht wurde sie verschoben oder der Link ist nicht vollständig.</p><Link className="button button-primary" href="/">Zur Startseite</Link></div></main>; }
