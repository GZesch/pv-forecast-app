import type { Metadata } from "next";
import Link from "next/link";
import { TopicCard } from "@/components/cards";
import { topics } from "@/lib/site";

export const metadata: Metadata = { alternates: { canonical: "/" } };

export default function Home() {
  return (
    <main>
      <section className="home-hero">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <p className="eyebrow hero-eyebrow"><span className="eyebrow-dot" /><span>Unabhängige Orientierung <span aria-hidden="true">·</span> Für Deutschland</span></p>
            <h1>Energie verstehen.<br /><span>Selbstbestimmt entscheiden.</span></h1>
            <p className="lead">Verständliches Wissen und transparente Rechner rund um Solarenergie, Speicher und Stromtarife – ohne Verkaufsdruck und ohne versteckte Empfehlungen.</p>
            <div className="button-row">
              <Link className="button button-primary" href="/rechner">Rechner entdecken <span aria-hidden="true">→</span></Link>
              <Link className="button button-secondary" href="#themen">Themen verstehen</Link>
            </div>
            <p className="hero-footnote"><span aria-hidden="true">✓</span> Keine Anbieter-Rankings · keine Leadvermittlung · keine Nutzung deiner Rechnerdaten für Werbung</p>
          </div>
          <aside className="hero-principles" aria-labelledby="hero-principles-title">
            <p className="eyebrow">Keine Blackbox</p>
            <h2 id="hero-principles-title">Du kannst nachvollziehen, wie Ergebnisse entstehen.</h2>
            <ul>
              <li><span aria-hidden="true">✓</span> Annahmen werden offengelegt</li>
              <li><span aria-hidden="true">✓</span> Datenquellen und Datenstand werden genannt</li>
              <li><span aria-hidden="true">✓</span> Grenzen und Unsicherheiten bleiben sichtbar</li>
            </ul>
            <p className="hero-principles-closing">Orientierung statt Scheingenauigkeit</p>
          </aside>
        </div>
      </section>

      <section className="beta-notice-section">
        <div className="shell">
          <div className="beta-notice">
            <span className="beta-notice-icon" aria-hidden="true">β</span>
            <div><strong>Diese Plattform befindet sich in der technischen Beta.</strong><p>Wir bauen Inhalte und Rechner schrittweise auf. Noch nicht verfügbare Funktionen sind klar gekennzeichnet – Ergebnisse werden nicht vorgetäuscht.</p></div>
            <Link href="/ueber">Mehr zum Projekt <span aria-hidden="true">→</span></Link>
          </div>
        </div>
      </section>

      <section className="section" id="themen">
        <div className="shell">
          <div className="section-heading">
            <div><p className="eyebrow">Wissen, das einordnet</p><h2>Energie im Alltag verstehen</h2></div>
            <p>Von der eigenen Solaranlage bis zum Strompreis: Wir erklären Zusammenhänge klar und nennen Grenzen offen.</p>
          </div>
          <div className="topic-grid">{topics.map((topic) => <TopicCard key={topic.title} {...topic} />)}</div>
        </div>
      </section>

      <section className="section section-ink">
        <div className="shell principles-grid">
          <div><p className="eyebrow eyebrow-light">Unser Maßstab</p><h2>Entscheidungshilfe,<br />keine Verkaufsmaschine.</h2></div>
          <div className="principle-list">
            <article><span>01</span><div><h3>Neutral</h3><p>Keine bezahlten Platzierungen und keine versteckten Anbieterinteressen.</p></div></article>
            <article><span>02</span><div><h3>Verständlich</h3><p>Komplexe Zusammenhänge in klarer Sprache, ohne wichtige Details wegzulassen.</p></div></article>
            <article><span>03</span><div><h3>Transparent</h3><p>Annahmen, Datenstand und Grenzen stehen direkt beim Ergebnis.</p></div></article>
          </div>
        </div>
      </section>
    </main>
  );
}
