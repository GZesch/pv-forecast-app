# ExergyPulse

Die öffentliche Hauptseite läuft mit Next.js. Der bestehende kurzfristige
PV-Forecast bleibt als getrennte Streamlit-Anwendung erhalten. FastAPI ist nur
im Compose-Netz unter `backend:8000` erreichbar; Caddy ist der einzige Dienst
mit öffentlichen Host-Ports.

## Lokale Zielarchitektur

- Next.js-Hauptseite: <http://exergypulse.localhost>
- Streamlit-Forecast: <http://forecast.localhost>
- Forecast-API-Dokumentation: <http://forecast.localhost/api/docs>
- Forecast-Health: <http://forecast.localhost/api/health>

Der Browser sendet PV-Wirtschaftlichkeitsanfragen ausschließlich an den
Same-Origin-Handler `/api/pv-economics/calculate`. Der Next.js-Server erreicht
FastAPI intern über `BACKEND_API_BASE_URL=http://backend:8000`; es gibt keine
öffentliche Backend-URL in einer `NEXT_PUBLIC_`-Variable.

## Vorbereitung vor dem Containerstart

1. Offizielle H25-XLSX lokal und außerhalb des Repositories beschaffen.
2. Deterministische CSV erzeugen:
   `uv run python scripts/convert_bdew_h25.py INPUT.xlsx runtime-data/bdew_h25.csv`
3. Netzwerkfreien Preflight ausführen:
   `uv run python scripts/verify_bdew_h25.py runtime-data/bdew_h25.csv`
4. `.env.example` nach `.env` kopieren und Hostverzeichnis/Adressen prüfen.
5. Compose-Konfiguration prüfen:
   `docker compose --env-file .env.example config --quiet`.
6. Erst danach und mit gesonderter Betriebsfreigabe Container starten.

Die H25-Datei wird weder von Git verwaltet noch in das Docker-Image kopiert.
Das vorhandene Hostverzeichnis `./runtime-data` wird read-only nach
`/app/runtime-data` eingebunden; die Anwendung liest dort `bdew_h25.csv`. Fehlt
die Datei oder ist sie ungültig, kann das Backend trotzdem starten, der
One-shot-Preflight endet jedoch mit einem Fehler und `web` startet nicht. Caddy
wartet nicht auf `web`: Der Next.js-Haupt-Host bleibt bis zur erfolgreichen
Bereitstellung kontrolliert nicht verfügbar, während Backend und der
bestehende Streamlit-Forecast startbar und über den Forecast-Host erreichbar
bleiben.

Die DuckDB-Datei liegt weiterhin unter `./database/pv_forecast.duckdb`. Dieses
Verzeichnis nicht löschen. Insbesondere ist `docker compose down -v` keine
pauschale Betriebsanweisung und ersetzt keine DuckDB-Sicherung.

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
mkdir -p runtime-data
# H25 extern beschaffen, konvertieren und prüfen (siehe Vorbereitung oben)
docker compose --env-file .env.example config --quiet
```

Erst nach erfolgreicher Daten- und Konfigurationsprüfung werden die Container in
einem gesondert freigegebenen Betriebsschritt gestartet. Für zwei Domains stehen
in `.env` beispielsweise:

```dotenv
SITE_ADDRESS=exergypulse.example.de
FORECAST_SITE_ADDRESS=forecast.example.de
BDEW_H25_DATA_HOST_DIR=./runtime-data
```

FastAPI, Next.js und Streamlit veröffentlichen selbst keine Host-Ports. Caddy
leitet die Hauptdomain an Next.js und die Forecast-Domain an Streamlit weiter.
Caddy hängt nicht von `web` ab: Bei fehlender oder ungültiger H25-Datei bleibt
die Hauptdomain bis zum erfolgreichen Preflight kontrolliert nicht verfügbar,
der bestehende Forecast-Pfad bleibt jedoch startbar und erreichbar.

Das Streamlit-Python-Backend ruft FastAPI serverseitig über
`API_BASE_URL=http://backend:8000` auf. Der Browser benötigt die API deshalb
nicht direkt. Ausschließlich die Forecast-Domain stellt für den bestehenden
Forecast `/api/*` bereit und entfernt das Präfix vor der Weiterleitung:

```bash
curl https://forecast.example.de/api/health
curl "https://forecast.example.de/api/debug/open-meteo?lat=59.32512&lon=18.07109"
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

Für beide Domains DNS-A-Records auf die Server-IPv4 setzen. Danach in `.env`
die Adressen ohne Protokoll eintragen:

```dotenv
SITE_ADDRESS=exergypulse.example.de
FORECAST_SITE_ADDRESS=forecast.example.de
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
