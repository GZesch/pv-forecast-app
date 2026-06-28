import Link from "next/link";
import { mainNavigation, siteConfig } from "@/lib/site";

function Brand() {
  return (
    <Link className="brand" href="/" aria-label={`${siteConfig.name} – Startseite`}>
      <span className="brand-mark" aria-hidden="true"><span /></span>
      <span>{siteConfig.name}</span>
    </Link>
  );
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  return (
    <nav aria-label={mobile ? "Mobile Hauptnavigation" : "Hauptnavigation"}>
      <ul className={mobile ? "mobile-nav-list" : "nav-list"}>
        {mainNavigation.map((item) => (
          <li key={item.href}>
            <Link href={item.href}>{item.label}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="beta-bar">
        <div className="shell beta-bar-inner">
          <span className="beta-pill">Technische Beta</span>
          <span>Die Plattform wird schrittweise aufgebaut. Inhalte und Rechner werden transparent ergänzt.</span>
        </div>
      </div>
      <div className="shell header-inner">
        <Brand />
        <div className="desktop-nav"><Navigation /></div>
        <details className="mobile-menu">
          <summary aria-label="Navigation öffnen"><span /><span /><span /></summary>
          <div className="mobile-menu-panel"><Navigation mobile /></div>
        </details>
      </div>
    </header>
  );
}
