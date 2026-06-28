# Öffentliches Web-Frontend

Isoliertes Next.js-Frontend der Energie-Wissensplattform. Das bestehende
FastAPI-Backend und das Streamlit-Frontend werden in diesem Arbeitspaket nicht
eingebunden oder verändert.

## Lokal starten

Voraussetzungen: Node.js 20.9 oder neuer und pnpm.

```bash
pnpm install
pnpm dev
```

Anschließend ist das Frontend unter `http://localhost:3000` erreichbar.

## Prüfen und bauen

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm start
```

Für korrekte absolute URLs in `sitemap.xml` und `robots.txt` wird beim späteren
Deployment `NEXT_PUBLIC_SITE_URL` auf die öffentliche HTTPS-Adresse gesetzt.
Lokal fällt die Anwendung auf `http://localhost:3000` zurück.
