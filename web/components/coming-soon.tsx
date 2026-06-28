import Link from "next/link";
import { Icon } from "@/components/icon";
import type { IconName } from "@/lib/site";

type ComingSoonProps = {
  title: string;
  description: string;
  icon: IconName;
  points: string[];
  externalCalculatorUrl?: string;
};

export function ComingSoon({ title, description, icon, points, externalCalculatorUrl }: ComingSoonProps) {
  return (
    <main>
      <section className="coming-hero">
        <div className="shell narrow">
          <p className="eyebrow">Rechner · Technische Beta</p>
          <div className="large-icon"><Icon name={icon} /></div>
          <h1>{title}</h1>
          <p className="lead">{description}</p>
          <div className="notice" role="status">
            {externalCalculatorUrl ? (
              <>
                <strong>Der Rechner ist bereits im bisherigen Bereich verfügbar.</strong>
                <p>Der PV-Forecast öffnet sich in der bestehenden Streamlit-Anwendung. Die neue gemeinsame Rechneroberfläche folgt später.</p>
                <div className="button-row">
                  <a className="button button-primary" href={externalCalculatorUrl} target="_blank" rel="noopener noreferrer">PV-Forecast öffnen</a>
                </div>
              </>
            ) : (
              <>
                <strong>Dieser Rechner ist in Vorbereitung.</strong>
                <p>Aktuell können hier noch keine Berechnungen durchgeführt werden. Es werden keine Ergebnisse simuliert oder Eingaben gespeichert.</p>
              </>
            )}
          </div>
        </div>
      </section>
      <section className="section section-soft">
        <div className="shell narrow">
          <p className="eyebrow">Geplanter Umfang</p>
          <h2>Was der Rechner leisten soll</h2>
          <ul className="check-list">{points.map((point) => <li key={point}>{point}</li>)}</ul>
          <div className="button-row"><Link className="button button-primary" href="/rechner">Zur Rechnerübersicht</Link><Link className="button button-quiet" href="/methodik">Zur Methodik</Link></div>
        </div>
      </section>
    </main>
  );
}
