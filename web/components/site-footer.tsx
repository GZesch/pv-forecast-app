import Link from "next/link";
import { siteConfig } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <Link className="brand brand-footer" href="/">
            <span>{siteConfig.name}</span>
          </Link>
          <p className="footer-mission">{siteConfig.claim}</p>
        </div>
        <div>
          <h2>Orientierung</h2>
          <ul>
            <li><Link href="/#themen">Wissen</Link></li>
            <li><Link href="/rechner">Rechner</Link></li>
            <li><Link href="/methodik">Methodik</Link></li>
          </ul>
        </div>
        <div>
          <h2>Projekt</h2>
          <ul>
            <li><Link href="/ueber">Über ExergyPulse</Link></li>
            <li><span>Deutschland · Technische Beta</span></li>
          </ul>
        </div>
      </div>
      <div className="shell footer-bottom">
        <p>© {new Date().getFullYear()} {siteConfig.name}</p>
        <p>Unabhängig · sachlich · transparent</p>
      </div>
    </footer>
  );
}
