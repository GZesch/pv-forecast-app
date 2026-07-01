import type { Metadata } from "next";
import { PageHero } from "@/components/page-hero";
import styles from "./methodik.module.css";

export const metadata: Metadata = {
  title: "Methodik und Transparenz",
  description: "Datenquellen, Rechenweg, Annahmen und Grenzen des PV- und Speicher-Angebotschecks.",
  alternates: { canonical: "/methodik" },
};

const sections = [
  ["zweck","Zweck und Geltungsbereich"],["rechenweg","Rechenweg im Überblick"],
  ["wetter","Wetter und PV-Erzeugung"],["last","Haushaltslast"],
  ["verschattung","Verschattung"],["speicher","Speicher"],
  ["wirtschaftlichkeit","Wirtschaftlichkeit"],["degradation","Degradation"],
  ["eeg","EEG und Einspeisebegrenzung"],["sensitivitaet","Wettersensitivität"],
  ["annahmen","Standardannahmen"],["quellen","Quellen und Datenstand"],
  ["grenzen","Grenzen"],["datenschutz","Datenschutz"],
];

const modelAssumptions = [
  ["Betrachtungszeitraum","20 Jahre"],["Strompreissteigerung","2 % p. a."],
  ["Betriebskostensteigerung","2 % p. a."],["Nominaler Diskontsatz","3 % p. a."],
  ["PV-Betriebskosten","1 % der aufgelösten PV-Investition pro Jahr"],
  ["Speicherbetriebskosten","0 € pro Jahr"],["PV-Degradation","0,5 % p. a., geometrisch"],
  ["Speicherdegradation","2 % p. a., geometrisch"],["Speicherwirkungsgrad","90 % Round-Trip"],
  ["Lade- und Entladeleistung","je 0,5 C"],["Albedo","0,2"],
  ["Ersatzinvestitionen","keine automatischen Ersatzinvestitionen"],
  ["Finanzierung","keine Finanzierung; Barkauf-/Projektperspektive"],
];

export default function Page() {
  return <main>
    <PageHero eyebrow="Methodik & Transparenz" title="Keine Blackbox.">
      <p>Du kannst nachvollziehen, wie Ergebnisse entstehen: von Wetter- und Lastdaten über die stündliche Energiebilanz bis zu Zahlungsreihen, Kennzahlen und historischen Wetterbandbreiten.</p>
    </PageHero>
    <div className={`shell ${styles.layout}`}>
      <nav className={styles.toc} aria-label="Inhaltsverzeichnis"><strong>Auf dieser Seite</strong><ul>{sections.map(([id,label])=><li key={id}><a href={`#${id}`}>{label}</a></li>)}</ul></nav>
      <div className={styles.content}>
        <MethodSection id="zweck" title="Zweck und Geltungsbereich">
          <p>Der Rechner ist ein Angebotscheck für eine <strong>neue private PV-Anlage in Deutschland</strong>, optional mit Heimspeicher. Er richtet sich an selbst genutzte Ein- und Zweifamilienhäuser und betrachtet Barkauf beziehungsweise Projektwirtschaftlichkeit.</p>
          <p>Verglichen werden <strong>ohne PV</strong>, <strong>nur PV</strong> und – falls gewählt – <strong>PV mit Speicher</strong>. Der Speicher wird immer als zusätzlicher Beitrag gegenüber derselben PV-Anlage ohne Speicher bewertet.</p>
          <h3>Nicht Bestandteil des MVP</h3><ul className={styles.columns}><li>Gewerbe und Mieterstrom</li><li>Volleinspeisung und Direktvermarktung</li><li>bestehende Anlagen und reine Speichernachrüstung</li><li>Finanzierung, Steuern und Förderberatung</li><li>dynamische Stromtarife</li><li>Wärmepumpe und Elektroauto als getrennte Verbraucher</li><li>Anbieter-, Produkt- oder Tarifempfehlungen</li></ul>
        </MethodSection>

        <MethodSection id="rechenweg" title="Rechenweg im Überblick">
          <ol className={styles.flow}><li><strong>Eingaben</strong><span>Standort, Verbrauch, Anlage, Speicher, Preise</span></li><li><strong>Stundenreihen</strong><span>Wetter und Haushaltslast</span></li><li><strong>Energiebilanz</strong><span>8.760 Stunden eines vollständigen Referenzjahres</span></li><li><strong>Projektion</strong><span>jährliche Neusimulation mit Degradation</span></li><li><strong>Zahlungsreihen</strong><span>Eigenverbrauch, Einspeisung, Kosten</span></li><li><strong>Ergebnisse</strong><span>Kennzahlen und optionale Sensitivität</span></li></ol>
          <p>Für jedes Projektjahr werden PV-Erzeugung und verfügbare Speicherkapazität angepasst und der stündliche Dispatch neu simuliert. Der Rechner extrapoliert nicht den kurzfristigen Streamlit-Forecast. Eingaben und Ergebnisse werden nicht als Projekt gespeichert.</p>
        </MethodSection>

        <MethodSection id="wetter" title="Wetter und PV-Erzeugung">
          <p>Das Basismodell ruft über den offiziellen JRC-Endpunkt ein typisches meteorologisches Jahr aus <strong>PVGIS 5.3</strong> mit der Strahlungsdatenbank <strong>PVGIS-SARAH3</strong> ab. Ein TMY bildet typische Monatsbedingungen ab; es ist keine Wetterprognose und kein einzelnes historisches Kalenderjahr.</p>
          <p>Verarbeitet werden Globalstrahlung auf die Horizontale (GHI), direkte Normalstrahlung (DNI), diffuse Horizontalstrahlung (DHI), Außentemperatur und Windgeschwindigkeit. Für jede Teilfläche berechnet das Modell:</p>
          <ol><li>Perez-Transposition auf Neigung und Ausrichtung,</li><li>SAPM-Zelltemperatur aus Einstrahlung, Temperatur und Wind,</li><li>PVWatts-Gleichstromleistung,</li><li>Wechselrichterwirkungsgrad und Systemverluste,</li><li>optionale Begrenzung der AC-Leistung.</li></ol>
          <p>Mehrere Teilflächen werden mit eigener Leistung, Ausrichtung und Neigung berechnet und stündlich addiert. Die Bodenreflexion verwendet standardmäßig eine Albedo von 0,2.</p>
          <aside className={styles.callout}><h3>Irradianz-Zeitversatz</h3><p>PVGIS liefert den Wert unter <code>inputs.location.irradiance_time_offset</code> in Stunden. Er verschiebt die Zeit für die Sonnenstandsberechnung. Die Schattenmatrix bleibt dagegen an der unverschobenen lokalen deutschen Monats- und Stundenposition.</p></aside>
          <Links items={[["PVGIS-Portal des JRC","https://re.jrc.ec.europa.eu/pvg_tools/en/"],["PVGIS-5.3-TMY-Endpunkt","https://re.jrc.ec.europa.eu/api/v5_3/tmy"],["PVGIS-5.3-seriescalc-Endpunkt","https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"]]}/>
        </MethodSection>

        <MethodSection id="last" title="Haushaltslast">
          <p>Standard ist das BDEW-Profil H25. Seine Viertelstundenwerte, Tagesarten und Dynamisierung werden auf ein vollständiges Referenzjahr gerollt, zu UTC-Stunden zusammengefasst und anschließend <strong>exakt auf den eingegebenen Jahresverbrauch normiert</strong>.</p>
          <p>Wochentage, Wochenenden und gesetzliche Feiertage werden anhand des Bundeslandcodes berücksichtigt. Kommunal abhängige Feiertage lassen sich allein aus dem Bundesland nicht vollständig bestimmen.</p>
          <p>Die ExergyPulse-Profile „Tagesprofil“, „Abendprofil“ und „gleichmäßiger“ verschieben beziehungsweise glätten 15 % des H25-Verlaufs. Sie sind synthetische Szenarien, keine Messdaten. Wärmepumpe und Elektroauto können nur im Gesamtjahresverbrauch enthalten sein.</p>
          <h3>H25-Provenienz</h3><dl className={styles.provenance}><div><dt>Offizielles BDEW-XLSX</dt><dd className={styles.hash}>SHA-256 1803D4C612693563A784EB61001E7C58FFD6BD18A6BCA3780F774F3C3459B845</dd></div><div><dt>Deterministisch erzeugte CSV</dt><dd className={styles.hash}>SHA-256 83A7F47E3A6BDEC28EF49FC56351542B3CBC13493BD988908B15579D7A6D66B8</dd></div></dl>
          <p>Die Quelldatei wird wegen ungeklärter ausdrücklicher Weiterverteilungserlaubnis nicht im Repository ausgeliefert. Fehlt die extern bereitgestellte, per Prüfsumme validierte CSV, bricht der Rechner geschlossen ab.</p>
          <Links items={[["Offizielle BDEW-H25-Quelldatei","https://www.bdew.de/media/documents/Kopie_von_Repr%C3%A4sentative_Profile_BDEW_H25_G25_L25_P25_S25_Ver%C3%B6ffentlichung.xlsx"]]}/>
        </MethodSection>

        <MethodSection id="verschattung" title="Verschattung">
          <p>Je PV-Teilfläche kann ein pauschaler Schattenfaktor oder eine Matrix aus zwölf Monaten und 24 lokalen deutschen Stunden verwendet werden. Der Wert beschreibt den blockierten Anteil der direkten Einstrahlung auf die Modulebene.</p>
          <div className={styles.formula} aria-label="POA nach Schatten ist eins minus Schattenfaktor, multipliziert mit direkter POA, plus diffuse POA, plus Bodenreflexion"><span>POA nach Schatten =</span><span>(1 − Schattenfaktor) × POA direkt</span><span>+ POA diffus + POA Boden</span></div>
          <p>In Worten: Nur der direkte Anteil wird vermindert. Diffuse Einstrahlung und Bodenreflexion bleiben unverändert. Module, Strings, Bypassdioden, MPP-Tracker und Optimierer werden nicht abgebildet; eine elektrische Teilverschattungsanalyse findet nicht statt.</p>
        </MethodSection>

        <MethodSection id="speicher" title="Speicher">
          <p>Der Speicher lädt ausschließlich aus PV-Überschuss und entlädt ausschließlich zur Deckung der Haushaltslast. Netzladen und Preis-Arbitrage sind ausgeschlossen.</p>
          <ul><li>nutzbare Kapazität statt Bruttokapazität</li><li>Round-Trip-Wirkungsgrad mit symmetrisch verteilter Lade-/Entladeeffizienz</li><li>begrenzte Lade- und Entladeleistung, standardmäßig jeweils 0,5 C</li><li>sichtbare Speicherverluste</li><li>äquivalente Vollzyklen (EFC) aus intern entnommener Speicherenergie</li></ul>
          <p>Der wirtschaftliche Speicherwert ist stets die Differenz gegenüber „nur PV“. Daraus folgt keine allgemeingültige Empfehlung für eine optimale Speichergröße.</p>
        </MethodSection>

        <MethodSection id="wirtschaftlichkeit" title="Wirtschaftlichkeit">
          <p>Die Zahlungsrechnung ist nominal: Strompreis- und Betriebskostensteigerung werden ausdrücklich angesetzt, ebenso ein nominaler Diskontsatz und die nominale Einspeisevergütung. Für jedes Betriebsjahr entsteht eine Zahlungsreihe.</p>
          <h3>Ausgegebene Kennzahlen</h3><ul><li>nominales Ergebnis über den Betrachtungszeitraum</li><li>Kapitalwert der diskontierten Zahlungsreihe</li><li>Amortisationszeit anhand des kumulierten nominalen Zahlungsstroms</li></ul>
          <p>LCOE und interne Rendite sind keine Leitkennzahlen dieses Rechners. Getrennt bewertet werden PV gegenüber ohne PV, das Gesamtpaket gegenüber ohne PV sowie der Speicher zusätzlich gegenüber nur PV.</p>
          <p>Der zusätzliche Speicherwert umfasst vermiedenen Netzbezug, veränderte Einspeiseerlöse, Speicherverluste, Speicherbetriebskosten und Speichermehrpreis.</p>
          <div className={styles.formula}><span>Paketpreis = PV-Preis + Speichermehrpreis</span></div>
          <p>Aus zwei bekannten Werten wird der dritte exakt abgeleitet; widersprüchliche Angaben werden abgelehnt. Bei ausschließlich bekanntem Paketpreis wird keine Kostenaufteilung erfunden. Dann können einzelne PV- und Speicherkennzahlen nicht verfügbar sein. Finanzierung wird nicht modelliert.</p>
        </MethodSection>

        <MethodSection id="degradation" title="Degradation">
          <h3>PV</h3><p>Standard sind 0,5 % pro Jahr, überschreibbar und geometrisch angewendet. Im ersten Betriebsjahr beträgt der Degradationsfaktor 1; die Minderung beginnt ab Jahr 2.</p>
          <h3>Speicher-Standardmodell</h3><p>Die nutzbare Kapazität sinkt geometrisch um standardmäßig 2 % pro Jahr. Wirkungsgrad sowie Lade- und Entladeleistung bleiben konstant. Ein automatischer Ersatz ist nicht enthalten.</p>
          <h3>Garantiemodell</h3><p>Alternativ kombiniert das Modell Garantiezeit, garantierte Restkapazität und genau eine Nutzungsgrenze aus Durchsatz oder EFC. Verwendet wird das Minimum aus linearer Kalendergrenze und linearer Durchsatzgrenze; für die Nutzung zählen nur abgeschlossene Vorjahre.</p>
          <p className={styles.emphasis}>Garantiegrenzen sind keine erwartete Alterungsprognose.</p><p>Nicht separat modelliert werden Zellchemie, Temperaturalterung, Ladezustand, Entladetiefe, C-Rate-Alterung sowie Leistungs- und Wirkungsgraddegradation.</p>
        </MethodSection>

        <MethodSection id="eeg" title="EEG und Einspeisebegrenzung">
          <p>Hinterlegt ist die Überschusseinspeisung für Gebäude und Lärmschutzwände bei Inbetriebnahme vom <strong>1. Februar bis 31. Juli 2026</strong>:</p>
          <div className={styles.tableWrap}><table><caption>Im Modell hinterlegte EEG-Vergütung</caption><thead><tr><th scope="col">Leistungsanteil</th><th scope="col">Vergütung</th></tr></thead><tbody><tr><th scope="row">bis 10 kW</th><td>7,78 ct/kWh</td></tr><tr><th scope="row">über 10 bis 40 kW</th><td>6,73 ct/kWh</td></tr><tr><th scope="row">über 40 bis 100 kW</th><td>5,50 ct/kWh</td></tr></tbody></table></div>
          <p>Die Berechnung erfolgt leistungsanteilig. Datenversion: <strong>BNetzA-2026-02-01</strong>. Außerhalb des unterstützten Inbetriebnahmezeitraums wird kein Tarif still angenommen; eine manuelle Eingabe ist erforderlich.</p>
          <p>Das Vergütungsende nach § 25 EEG kann unterjährig liegen. Im jährlichen Modell wird dieser Anteil nach Kalendertagen vereinfacht gewichtet.</p>
          <p>Ohne Expertenvorgabe ist das Basisergebnis nicht einspeisebegrenzt. Zusätzlich wird das erste Jahr mit einer 60-%-Grenze verglichen. Im Expertenmodus kann eine Grenze in kW oder Prozent sowie die Zahl betroffener Jahre gesetzt werden; Abregelung bleibt sichtbar.</p>
          <p className={styles.emphasis}>Tarifdaten müssen vor Veröffentlichung beziehungsweise für neue Inbetriebnahmezeiträume aktualisiert werden.</p>
          <Links items={[["Bundesnetzagentur: EEG-Förderung","https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/ErneuerbareEnergien/EEG_Foerderung/start.html"],["§ 25 EEG auf gesetze-im-internet.de","https://www.gesetze-im-internet.de/eeg_2014/__25.html"]]}/>
        </MethodSection>

        <MethodSection id="sensitivitaet" title="Historische Wettersensitivität">
          <p>Optional ruft der Rechner für jede Teilfläche vollständige reale PVGIS-SARAH3-Jahre von 2005 bis 2023 über <code>seriescalc</code> ab. Die gelieferten direkten, diffusen und bodenreflektierten Werte liegen bereits in der jeweiligen Modulebene vor und werden nicht erneut transponiert.</p>
          <p>Schaltjahre müssen zunächst 8.784 Stunden enthalten; anschließend wird ausschließlich der vollständige 29. Februar entfernt. Mindestens zehn vollständige, für alle Teilflächen gemeinsame Jahre sind erforderlich.</p>
          <p>Die Jahre werden nach der jährlichen AC-Erzeugung der Gesamtanlage sortiert, bei Gleichstand nach Kalenderjahr. Ausgewählt werden tatsächlich vorhandene Jahre nach Nearest Rank <code>ceil(p × n)</code>:</p>
          <ul><li>10 %: ertragsschwach</li><li>50 %: mittel</li><li>90 %: ertragreich</li></ul>
          <p>Für jedes ausgewählte Jahr werden Energiebilanz, Speicherdispatch, Projektion und Wirtschaftlichkeit mit unveränderten sonstigen Annahmen neu berechnet. Es entstehen keine interpolierten Kunstjahre.</p>
          <p className={styles.emphasis}>Die Darstellung ist eine historische Wetterbandbreite, keine Zukunftsprognose. Sie wird nicht mit PV-Degradation, Verschmutzung oder zusätzlicher Verschattung vermischt. „Ertragsschwach“ ist kein wirtschaftliches Gesamturteil.</p>
        </MethodSection>

        <MethodSection id="annahmen" title="Standardannahmen">
          <p>Diese Werte sind in der Oberfläche überschreibbar oder als sichtbare Modellstandards dokumentiert. Sie sind keine allgemeingültigen Empfehlungen.</p>
          <div className={styles.tableWrap}><table><caption>ExergyPulse-Modellannahmen, Modellversion pv-economics-1.0</caption><thead><tr><th scope="col">Annahme</th><th scope="col">Standard</th><th scope="col">Einordnung</th></tr></thead><tbody>{modelAssumptions.map(([name,value])=><tr key={name}><th scope="row">{name}</th><td>{value}</td><td>ExergyPulse-Modellannahme</td></tr>)}</tbody></table></div>
        </MethodSection>

        <MethodSection id="quellen" title="Quellen und Datenstand">
          <div className={styles.tableWrap}><table><caption>Primärquellen und interne Modellstände</caption><thead><tr><th scope="col">Quelle</th><th scope="col">Verwendung</th><th scope="col">Stand</th><th scope="col">Grenze oder Hinweis</th></tr></thead><tbody>
            <SourceRow name="PVGIS / JRC" href="https://re.jrc.ec.europa.eu/pvg_tools/en/" use="TMY und historische Einstrahlungs-/Wetterdaten" version="PVGIS 5.3, SARAH3" note="Externer Dienst; TMY ist keine Prognose."/>
            <SourceRow name="BDEW H25" href="https://www.bdew.de/media/documents/Kopie_von_Repr%C3%A4sentative_Profile_BDEW_H25_G25_L25_P25_S25_Ver%C3%B6ffentlichung.xlsx" use="Haushalts-Standardlastprofil" version="Quelldatei 17.03.2025" note="Keine Einzelmessung; Quelldatei nicht im Repository."/>
            <SourceRow name="Bundesnetzagentur" href="https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/ErneuerbareEnergien/EEG_Foerderung/start.html" use="EEG-Vergütung" version="BNetzA-2026-02-01" note="Nur der dokumentierte Zeitraum; sonst manuelle Eingabe."/>
            <SourceRow name="§ 25 EEG" href="https://www.gesetze-im-internet.de/eeg_2014/__25.html" use="Ende des Vergütungszeitraums" version="Abruf vor Veröffentlichung prüfen" note="Unterjähriges Ende wird im Jahresmodell zeitanteilig vereinfacht."/>
            <SourceRow name="ExergyPulse-Modellannahmen" use="Degradation, Kosten, Diskontierung und technische Standards" version="pv-economics-1.0; Datenstand 01.07.2026" note="Keine verbindliche externe Quelle; vom Nutzer teilweise überschreibbar."/>
          </tbody></table></div>
        </MethodSection>

        <MethodSection id="grenzen" title="Grenzen und Einordnung" className={styles.boundaries}>
          <h3>Orientierung statt Scheingenauigkeit</h3><ul><li>keine Ertragsgarantie und keine technische Anlagenplanung</li><li>keine Finanzierungs-, Steuer-, Förder- oder Rechtsberatung</li><li>keine Anbieter- oder Produktempfehlung</li><li>Ergebnisse hängen unmittelbar von Eingaben und Annahmen ab</li><li>individuelle Verbrauchs- und Erzeugungsverläufe können deutlich abweichen</li></ul><p>Die Oberfläche gibt deshalb kein Ampelurteil und keine Kaufempfehlung aus.</p>
        </MethodSection>

        <MethodSection id="datenschutz" title="Datenschutz im Rechner">
          <p>Der PV-Wirtschaftlichkeitsrechner arbeitet stateless: Für diesen Endpunkt sind kein Account und keine Session-ID erforderlich. Eingaben und Ergebnisse werden weder in DuckDB noch im Browser, in einer URL oder als gespeichertes Projekt abgelegt.</p>
          <p>Request- und Response-Inhalte werden nicht protokolliert. Es gibt keine Anbieterweitergabe und keine Leadvermittlung. Für die Wetterabfrage erhält PVGIS die eingegebenen Koordinaten, aber keine vollständige Adresse.</p>
          <p>Diese Beschreibung bezieht sich auf den technisch implementierten Rechnerpfad und ist keine pauschale rechtliche Datenschutzerklärung.</p>
        </MethodSection>
      </div>
    </div>
  </main>;
}

function MethodSection({id,title,children,className=""}:{id:string;title:string;children:React.ReactNode;className?:string}) { return <section id={id} className={`${styles.section} ${className}`}><h2>{title}</h2>{children}</section> }
function Links({items}:{items:string[][]}) { return <ul className={styles.links}>{items.map(([label,url])=><li key={url}><a href={url} target="_blank" rel="noreferrer">{label} <span aria-hidden="true">↗</span><span className={styles.srOnly}> (externer Link)</span></a></li>)}</ul> }
function SourceRow({name,use,version,note,href}:{name:string;use:string;version:string;note:string;href?:string}) { return <tr><th scope="row">{href?<a href={href} target="_blank" rel="noreferrer">{name} <span aria-hidden="true">↗</span><span className={styles.srOnly}> (externer Link)</span></a>:name}</th><td>{use}</td><td>{version}</td><td>{note}</td></tr> }
