# PV Forecast App

Grundgerüst einer Web-Anwendung zur Vorhersage von Photovoltaik-Leistung mit
FastAPI, Streamlit und DuckDB.

## Start mit Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Das Compose-Setup entspricht dem Produktionsaufbau: Caddy ist der einzige
öffentlich erreichbare Dienst. FastAPI und Streamlit sind nur im internen
Docker-Netz erreichbar. Für lokale Entwicklung mit automatischem Reload können
die weiter unten dokumentierten `uv`-Befehle verwendet werden.

Danach sind die Dienste erreichbar:

- App (weiterhin Streamlit): <http://localhost>
- Next.js-Preview: <http://preview.localhost>
- API-Dokumentation über Caddy: <http://localhost/api/docs>
- Health Check über Caddy: <http://localhost/api/health>

Beenden mit:

```bash
docker compose down
```

### Getrennte Next.js-Preview

Caddy bedient zwei voneinander getrennte Adressen: `SITE_ADDRESS` bleibt die
öffentliche Streamlit-Hauptadresse, `PREVIEW_SITE_ADDRESS` leitet ausschließlich
an den internen Next.js-Dienst `web:3000` weiter. Lokal verwendet die Preview
den Standardwert `http://preview.localhost`. Falls das Betriebssystem diesen
reservierten `.localhost`-Namen nicht selbst auflöst, muss in der lokalen
Hosts-Datei `127.0.0.1 preview.localhost` ergänzt werden. Es werden keine
zusätzlichen Host-Ports geöffnet.

Für eine andere Preview-Adresse in `.env` eine vollständige URL setzen:

```dotenv
SITE_ADDRESS=:80
PREVIEW_SITE_ADDRESS=http://preview.localhost
PV_FORECAST_URL=http://localhost
```

Die Preview-Adresse wird beim Build in die statischen Metadaten übernommen.
Nach einer Änderung deshalb `web` neu bauen und Caddy aktualisieren:

```bash
docker compose build web
docker compose up -d web caddy
```

`PV_FORECAST_URL` ist die öffentliche Adresse des bestehenden
Streamlit-Rechners. Next.js verwendet sie ausschließlich für den temporären
PV-Forecast-Link; Änderungen an dieser Adresse erfordern ebenfalls einen Neubau
des `web`-Images.

Manuelle lokale Prüfung:

```bash
curl http://localhost/
curl http://preview.localhost/
curl http://preview.localhost/methodik
curl http://localhost/api/health
```

Die Namensauflösung kann vorab geprüft werden:

```powershell
Resolve-DnsName preview.localhost
```

Für einen einmaligen Test ohne Hosts-Datei kann curl die Auflösung explizit
vorgeben:

```powershell
curl.exe --resolve preview.localhost:80:127.0.0.1 http://preview.localhost/
```

Die Preview lässt sich ohne Auswirkung auf Streamlit mit
`docker compose stop web` deaktivieren; die Preview-Adresse antwortet dann nicht
mehr erfolgreich, Hauptseite und API bleiben verfügbar. Mit
`docker compose up -d web` wird sie wieder aktiviert.

Bei einer späteren, ausdrücklich freigegebenen Umschaltung wird im
`SITE_ADDRESS`-Block des Caddyfiles nur das abschließende Standard-Routing von
`frontend:8501` auf `web:3000` geändert. Die `/api/*`-, Swagger- und
OAuth-Weiterleitungen bleiben dabei bestehen. Dieser Umschaltvorgang ist in der
aktuellen Preview-Konfiguration noch nicht vorgenommen.

Die DuckDB-Datei liegt auf dem Host unter `./database/pv_forecast.duckdb` und
bleibt bei Container-Neubauten sowie `docker compose down` erhalten. Dieses
Verzeichnis darf bei Deployments nicht gelöscht werden. `docker compose down -v`
entfernt nur die Caddy-Volumes, nicht das gebundene Datenbankverzeichnis.

## Anlagen-API

Die folgenden Endpunkte verwalten PV-Anlagen dauerhaft in DuckDB:

- `POST /installations` – neue Anlage anlegen
- `GET /installations` – alle Anlagen auflisten
- `GET /installations/{id}` – eine Anlage anhand ihrer UUID abrufen
- `PUT /installations/{id}` – eine Anlage bearbeiten und bei geändertem Ort neu geocodieren
- `DELETE /installations/{id}` – eine Anlage löschen

Alle Anlagen-Endpunkte erwarten den Header `X-Session-ID` mit einer UUID. Das
Streamlit-Frontend fragt in der Sidebar einen einfachen Projekt-/Nutzercode ab
und leitet daraus deterministisch eine stabile UUID ab. Der Code wird getrimmt,
in Kleinbuchstaben normalisiert und leere Eingaben fallen auf `demo` zurück:
`uuid.uuid5(uuid.NAMESPACE_URL, f"pv-forecast:{code}")`. Mit demselben Code sind
Anlagen nach Browser-Reloads, Docker-Restarts und Server-Restarts wieder
sichtbar. Der Code ist kein Passwort, bietet keine echte Authentifizierung und
ersetzt bewusst kein Login-System.

Im Streamlit-Frontend können Anlagen über ein Formular angelegt werden. Die
Anlagenliste wird direkt nach dem Speichern neu vom Backend geladen. Der als
Freitext eingegebene Standort wird im Backend über Nominatim/OpenStreetMap
geocodiert; gespeichert werden die ermittelten Koordinaten und der unveränderte,
getrimmte Standort-Freitext als nutzerfreundliches `location_label`. So bleibt
beispielsweise die Eingabe `Stockholm` auch in der Anlagenliste `Stockholm`.
Bestehende Datensätze ohne Ortslabel werden bei der Schema-Initialisierung mit
gerundeten Koordinaten nachgetragen; auch das Frontend besitzt denselben
Koordinaten-Fallback.

Für einen öffentlich betriebenen Dienst sollte `NOMINATIM_USER_AGENT` auf eine
eindeutige Anwendungskennung mit Kontaktmöglichkeit gesetzt werden. Die öffentliche
Nominatim-Instanz wird mit maximal einer Anfrage pro Sekunde angesprochen.

### Bestehende flüchtige Sessions einem Projektcode zuordnen

Vor der Einführung des Projektcodes wurden Session-IDs flüchtig im
Streamlit-Prozess erzeugt. Solche Anlagen bleiben in DuckDB erhalten, werden aber
erst wieder angezeigt, wenn ihre alte `session_id` auf die stabile UUID eines
Projektcodes umgestellt wird. Das sollte nur nach einem Backup und bewusst für
eine bekannte alte Session erfolgen.

Stabile UUID für einen Code berechnen:

```bash
docker compose exec backend python -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, 'pv-forecast:demo'))"
```

Beispielhafte Zuordnung einer alten Session auf den Code `demo`:

```bash
docker compose exec backend python -c "import duckdb, uuid; db='/app/database/pv_forecast.duckdb'; old='<alte-session-id>'; new=str(uuid.uuid5(uuid.NAMESPACE_URL, 'pv-forecast:demo')); con=duckdb.connect(db); con.execute('UPDATE installations SET session_id = ? WHERE session_id = ?', [new, old]); con.execute('UPDATE plants SET session_id = ? WHERE session_id = ?', [new, old]); con.close(); print(new)"
```

## Wettervorhersage

`GET /installations/{id}/weather-forecast` lädt stündliche Wetterwerte für die
Koordinaten einer gespeicherten Anlage von Open-Meteo. Über den optionalen
Query-Parameter `forecast_days` kann ein Zeitraum von 1 bis 16 Tagen gewählt
werden; der Standard sind 7 Tage. Die Daten werden nur zurückgegeben und nicht
in DuckDB gespeichert.

## PV-Leistungsprognose

`GET /installations/{id}/pv-forecast` lädt die stündlichen Open-Meteo-Daten und
berechnet daraus mit pvlib eine einfache DC-Leistungsprognose. Das Modell nutzt
Sonnenstand, Einstrahlung auf die geneigte Modulfläche, eine einfache
Zelltemperaturabschätzung und PVWatts. Über `forecast_days` sind 1 bis 16 Tage
möglich. Erfolgreiche Prognosen werden in DuckDB gespeichert.
Zusätzlich enthält die Antwort Tageserträge in kWh, die aus den stündlichen
Leistungswerten aufsummiert werden, sowie Peak-Leistung und Peak-Zeitpunkt.

Das Frontend konvertiert API-Zeitstempel für die Anzeige nach `Europe/Berlin`
und formatiert Datum und Uhrzeit auf Deutsch. Die stündlichen Plot-Daten bleiben
unverändert; die Achse zeigt Uhrzeitmarken im Drei-Stunden-Raster und eine
separate, zentrierte Tagesbeschriftung.

## Forecast-Historie

Jede erfolgreiche PV-Berechnung wird in `forecast_runs` und `forecast_points`
gespeichert. `GET /installations/{id}/forecast-history` liefert standardmäßig
die 20 neuesten Runs mit Zeitraum, Tageserträgen und Peak-Kennzahlen. Die
zugehörigen Historieneinträge werden beim Löschen einer Anlage mit entfernt.
Im öffentlichen Standardmodus ist die Historie ausgeblendet und wird nur bei
aktivem Expertenmodus geladen und angezeigt.

## Kraftwerke

Mehrere sessiongebundene Einzelanlagen können zu einem Kraftwerk gruppiert
werden. Die Tabelle `plants` speichert die Gruppe; `installations.plant_id` ist
optional, sodass bestehende Einzelanlagen unverändert funktionieren. Über
`GET /plants/{id}/pv-forecast` werden die Stundenwerte aller zugeordneten
Anlagen timestampgenau summiert und daraus gemeinsame Tageserträge sowie
Peak-Kennzahlen berechnet. Im Expertenmodus liefert das Frontend zusätzlich die
Einzelkurven der enthaltenen Anlagen.

Open-Meteo-Antworten werden anhand auf vier Dezimalstellen gerundeter
Koordinaten und des Prognosezeitraums sechs Stunden im Arbeitsspeicher gecacht.
Innerhalb einer Kraftwerksprognose wird jeder gerundete Standort höchstens
einmal abgefragt. Eine Drosselung des Wetterdienstes wird ohne automatische
Retry-Schleife als temporäre Auslastung verständlich an das Frontend
weitergegeben; technische HTTP-Details werden nicht angezeigt.

Erfolgreiche Prognosen für Anlagen und Kraftwerke werden mit Zieltyp, Ziel-ID,
Stunden- und Tageswerten sowie der Quelle `fresh` oder `cached` persistiert.
Erreicht Open-Meteo sein Tageslimit, liefert die API die neueste gespeicherte
Prognose mit einem Warnhinweis zurück. Ohne gespeicherten Lauf wird eine
verständliche HTTP-503-Meldung ausgegeben.

Falls ein bereits laufendes Docker-Setup einen generischen 404-Fehler für diesen
Endpunkt liefert, müssen Backend und Frontend mit dem aktuellen Quellstand neu
gebaut werden:

```bash
docker compose up --build
```

## Lokale Entwicklung

Python 3.12 und `uv` werden vorausgesetzt.

```bash
uv sync
uv run uvicorn backend.main:app --reload
uv run streamlit run frontend/app.py
uv run pytest
```

## Deployment auf Hetzner Cloud

### 1. Server anlegen

In der Hetzner Cloud Console einen Cloud Server mit Ubuntu 24.04 erstellen.
IPv4 aktivieren und entweder einen SSH-Key hinterlegen oder ein sicheres
Root-Passwort verwenden. Anschließend mit der angezeigten IPv4-Adresse verbinden:

```bash
ssh root@<SERVER-IP>
```

### 2. Docker und grundlegende Pakete installieren

```bash
apt update
apt upgrade -y
apt install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker run --rm hello-world
docker compose version
```

Vor dem Aktivieren der Firewall immer zuerst SSH erlauben:

```bash
apt install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable
ufw status
```

### 3. Anwendung installieren

```bash
git clone <MEIN_REPO>
cd <MEIN_REPO>
cp .env.example .env
nano .env
mkdir -p database
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Für den ersten Start über die Server-IP bleibt in `.env`:

```dotenv
SITE_ADDRESS=:80
```

Die App ist anschließend unter `http://<SERVER-IP>` erreichbar. FastAPI und
Streamlit veröffentlichen selbst keine Host-Ports. Caddy ist der einzige
öffentliche Dienst und leitet die App an Streamlit weiter.

Das Streamlit-Python-Backend ruft FastAPI serverseitig über
`API_BASE_URL=http://backend:8000` auf. Der Browser benötigt die API deshalb
nicht direkt. Für Diagnose und Dokumentation stellt Caddy trotzdem `/api/*`
bereit und entfernt das Präfix vor der Weiterleitung:

```bash
curl http://<SERVER-IP>/api/health
curl "http://<SERVER-IP>/api/debug/open-meteo?lat=59.32512&lon=18.07109"
```

### 4. DuckDB übernehmen und sichern

Die produktive Datei liegt unter
`./database/pv_forecast.duckdb` auf dem VPS. Eine bestehende Datenbank muss vor
dem ersten Containerstart in dieses Verzeichnis kopiert werden. Der folgende
`scp`-Befehl wird auf dem lokalen Rechner ausgeführt, nicht in der VPS-SSH-Sitzung:

```bash
scp database/pv_forecast.duckdb root@<SERVER-IP>:/opt/pv-forecast/database/
```

Dabei muss `/opt/pv-forecast` durch den tatsächlichen Zielpfad des geklonten
Repositories ersetzt werden. Es darf nur eine Backend-Instanz gleichzeitig auf
DuckDB schreiben. Für eine konsistente manuelle Sicherung das Backend kurz
stoppen:

```bash
docker compose stop backend
cp database/pv_forecast.duckdb "database/pv_forecast-$(date +%F-%H%M).duckdb.bak"
docker compose start backend
```

Persistenztest nach dem Anlegen einer Testanlage:

```bash
ls -lh database/pv_forecast.duckdb
docker compose down
docker compose up -d
ls -lh database/pv_forecast.duckdb
```

### 5. Domain und automatisches HTTPS aktivieren

Für die Domain einen DNS-A-Record auf die Server-IPv4 setzen. Danach in `.env`
die Adresse ohne Protokoll eintragen:

```dotenv
SITE_ADDRESS=forecast.example.de
```

Anschließend Caddy neu laden. Bei korrektem DNS und offenen Ports 80/443
beschafft Caddy automatisch ein TLS-Zertifikat:

```bash
docker compose up -d
docker compose logs -f caddy
```

### 6. Spätere Updates

Das Datenbankverzeichnis wird von Git ignoriert und darf nicht gelöscht werden:

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend frontend caddy
```

### Anfänger-Checkliste

- Hetzner Cloud Server mit Ubuntu 24.04 und IPv4 erstellen.
- SSH-Key oder sicheres Root-Passwort hinterlegen und per SSH verbinden.
- Docker Engine und das Docker-Compose-Plugin installieren.
- Vor `ufw enable` unbedingt `OpenSSH`, Port 80 und Port 443 erlauben.
- Repository klonen und `.env.example` nach `.env` kopieren.
- `NOMINATIM_USER_AGENT` in `.env` mit eigener Kontaktangabe anpassen.
- Vorhandene DuckDB bei Bedarf vor dem ersten Start nach `database/` kopieren.
- Mit `docker compose up -d --build` starten und Logs prüfen.
- App über die IPv4-Adresse öffnen und `/api/health` testen.
- Einen Open-Meteo-Test über `/api/debug/open-meteo` ausführen.
- Testanlage anlegen und einen Container-Neustart als Persistenztest durchführen.
- Später DNS setzen, `SITE_ADDRESS` auf die Domain ändern und HTTPS prüfen.
- Regelmäßige DuckDB-Backups außerhalb des Repository-Verzeichnisses einplanen.

## Deployment auf Render (bestehendes Legacy-Setup)

Backend und Frontend werden als zwei getrennte Render-Webservices betrieben.
Beide Services verwenden dasselbe Repository und `requirements.txt`. Die Datei
`.python-version` legt Python 3.12 fest.

### Backend-Service

In Render einen Python-Webservice mit folgenden Einstellungen anlegen:

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

Environment-Variablen:

- `DATABASE_PATH=/var/data/pv_forecast.duckdb`
- `NOMINATIM_USER_AGENT=pv-forecast-app/1.0 (Kontakt: eigene E-Mail oder URL)`

Damit Anlagen und Forecast-Historie Deployments und Neustarts überleben, muss
am Backend-Service ein Render Persistent Disk mit dem Mount Path `/var/data`
eingebunden werden. Ohne Persistent Disk liegt DuckDB auf dem flüchtigen
Dateisystem der Instanz.

### Frontend-Service

Einen zweiten Python-Webservice mit folgenden Einstellungen anlegen:

- Build Command: `pip install -r requirements.txt`
- Start Command: `streamlit run frontend/app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true`

Environment-Variable:

- `API_BASE_URL=https://<name-des-backend-service>.onrender.com`

Das Frontend liest `API_BASE_URL` beim Start aus der Umgebung. Die URL muss auf
die öffentliche HTTPS-Adresse des Backend-Service zeigen und darf optional mit
einem abschließenden Slash angegeben werden.

### Startbefehle außerhalb von Render

Die gleichen portablen Befehle funktionieren in jeder Shell, die `PORT` setzt:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
streamlit run frontend/app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

Backend und Frontend benötigen jeweils einen eigenen Port und laufen daher in
getrennten Prozessen beziehungsweise Render-Services.
