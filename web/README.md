# Öffentliches ExergyPulse-Web-Frontend

Next.js stellt die öffentliche Hauptseite und den PV-/Speicher-
Wirtschaftlichkeitsrechner bereit. Der Browser verwendet für Berechnungen nur
den Same-Origin Route Handler `/api/pv-economics/calculate`. Dieser leitet
serverseitig an `BACKEND_API_BASE_URL` weiter; die Backend-Adresse darf nicht als
`NEXT_PUBLIC_`-Variable veröffentlicht werden.

## Lokale Entwicklung ohne Compose

Voraussetzungen: Node.js 20.9 oder neuer, pnpm und ein lokal erreichbares
FastAPI-Backend.

```text
BACKEND_API_BASE_URL=http://localhost:8000
pnpm install
pnpm dev
```

Das Frontend ist dann unter <http://localhost:3000> erreichbar. Der serverseitige
Default für das Backend lautet `http://localhost:8000`.

## Prüfung

```text
pnpm lint
pnpm typecheck
pnpm build
```

## Compose-Betrieb

Caddy leitet `SITE_ADDRESS` an `web:3000`. Lokal ist das standardmäßig
<http://exergypulse.localhost>. Beim Image-Build werden daraus Canonicals,
Sitemap und robots.txt erzeugt. Der Link zum getrennten Streamlit-Forecast wird
aus `FORECAST_SITE_ADDRESS` als `NEXT_PUBLIC_PV_FORECAST_URL` eingebettet.

Im laufenden Web-Container ist `BACKEND_API_BASE_URL=http://backend:8000`
ausschließlich serverseitig gesetzt. `web` wartet auf ein gesundes Backend und
auf den erfolgreich abgeschlossenen H25-Preflight. Fehlende oder ungültige
H25-Laufzeitdaten blockieren damit den neuen Rechnerpfad. Caddy wartet nicht
auf `web`: Bis zum erfolgreichen Preflight ist der Next.js-Haupt-Host daher
kontrolliert nicht verfügbar, während Backend, Caddy und der bestehende
Streamlit-Forecast startbar und über den Forecast-Host erreichbar bleiben.
