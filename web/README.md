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

## Docker-Preview

Im gemeinsamen Compose-Setup läuft dieses Frontend als interner Dienst `web`.
Nur Caddy erreicht Port 3000; ein Host-Port wird nicht veröffentlicht. Die
Vorschau verwendet lokal standardmäßig `http://preview.localhost`, während
`http://localhost` weiterhin das bestehende Streamlit-Frontend zeigt. Falls der
lokale Resolver den reservierten `.localhost`-Namen nicht auflöst, muss
`preview.localhost` in der Hosts-Datei auf `127.0.0.1` gesetzt werden.

`PREVIEW_SITE_ADDRESS` aus der Root-`.env` wird beim Image-Build als
`NEXT_PUBLIC_SITE_URL` gesetzt. Dadurch verwenden Canonicals, `sitemap.xml` und
`robots.txt` die Preview-Adresse. Nach einer Änderung muss das Image neu gebaut
werden:

```bash
docker compose build web
docker compose up -d web caddy
```

Der PV-Forecast verweist während der Übergangszeit auf die bestehende
Streamlit-Anwendung. Das Linkziel wird in der Root-`.env` mit
`PV_FORECAST_URL` konfiguriert und beim Build als
`NEXT_PUBLIC_PV_FORECAST_URL` übernommen. Der Link öffnet sich in einem neuen
Tab; die übrigen Rechner-Platzhalter bleiben unverändert.
