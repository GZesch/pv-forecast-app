# PV Forecast App

Grundgerüst einer Web-Anwendung zur Vorhersage von Photovoltaik-Leistung mit
FastAPI, Streamlit und DuckDB.

## Start mit Docker

```bash
docker compose up --build
```

Das lokale Compose-Setup bindet `backend/` und `frontend/` direkt in die
Container ein. Backend-Änderungen werden von Uvicorn automatisch neu geladen;
damit laufen die Container nicht unbemerkt mit älteren API-Routen weiter.

Danach sind die Dienste erreichbar:

- Streamlit: <http://localhost:8501>
- FastAPI: <http://localhost:8000>
- API-Dokumentation: <http://localhost:8000/docs>
- Health Check: <http://localhost:8000/health>

Beenden mit:

```bash
docker compose down
```

Die DuckDB-Datei liegt in einem Docker-Volume und bleibt nach dem Stoppen der
Container erhalten. Mit `docker compose down -v` wird auch dieses Volume entfernt.

## Anlagen-API

Die folgenden Endpunkte verwalten PV-Anlagen dauerhaft in DuckDB:

- `POST /installations` – neue Anlage anlegen
- `GET /installations` – alle Anlagen auflisten
- `GET /installations/{id}` – eine Anlage anhand ihrer UUID abrufen
- `DELETE /installations/{id}` – eine Anlage löschen

Alle Anlagen-Endpunkte erwarten den Header `X-Session-ID` mit einer UUID. Das
Streamlit-Frontend erzeugt beim ersten Besuch automatisch eine anonyme UUID und
speichert sie in `st.session_state`. Anlagen, Forecasts und Historie sind dadurch
nur innerhalb dieser Besucher-Session sichtbar; es gibt bewusst keine Anmeldung
und kein User-Management.

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
Koordinaten und des Prognosezeitraums 15 Minuten im Arbeitsspeicher gecacht.
Innerhalb einer Kraftwerksprognose wird jeder gerundete Standort höchstens
einmal abgefragt. HTTP 429 wird ohne automatische Retry-Schleife als temporäre
Auslastung verständlich an das Frontend weitergegeben.

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

## Deployment auf Render

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
