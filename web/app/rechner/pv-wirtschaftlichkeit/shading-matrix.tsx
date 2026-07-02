"use client";

import { useMemo, useState } from "react";
import { FieldErrors, SurfaceForm } from "@/lib/pv-economics";
import styles from "./pv-economics-form.module.css";

const months=["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];
const hours=Array.from({length:24},(_,hour)=>hour);
const berlinParts=new Intl.DateTimeFormat("de-DE",{timeZone:"Europe/Berlin",month:"numeric",hour:"numeric",hourCycle:"h23"});

function solarElevation(date:Date,latitude:number,longitude:number){
  const radians=Math.PI/180,days=date.getTime()/86_400_000+2_440_587.5-2_451_545;
  const meanLongitude=(280.46+.9856474*days)%360,anomaly=(357.528+.9856003*days)*radians;
  const ecliptic=(meanLongitude+1.915*Math.sin(anomaly)+.02*Math.sin(2*anomaly))*radians;
  const obliquity=(23.439-.0000004*days)*radians;
  const rightAscension=Math.atan2(Math.cos(obliquity)*Math.sin(ecliptic),Math.cos(ecliptic))/radians;
  const declination=Math.asin(Math.sin(obliquity)*Math.sin(ecliptic));
  const sidereal=(280.46061837+360.98564736629*days+longitude)%360;
  let hourAngle=(sidereal-rightAscension)%360;if(hourAngle>180)hourAngle-=360;if(hourAngle< -180)hourAngle+=360;
  const lat=latitude*radians;
  return Math.asin(Math.sin(lat)*Math.sin(declination)+Math.cos(lat)*Math.cos(declination)*Math.cos(hourAngle*radians))/radians;
}

function daylightMatrix(latitude:number,longitude:number){
  const result=Array.from({length:12},()=>Array(24).fill(false));
  for(let time=Date.UTC(2026,0,1);time<Date.UTC(2027,0,1);time+=15*60_000){
    const date=new Date(time);if(solarElevation(date,latitude,longitude)>0){const parts=berlinParts.formatToParts(date),month=Number(parts.find(part=>part.type==="month")?.value)-1,hour=Number(parts.find(part=>part.type==="hour")?.value);result[month][hour]=true;}
  }
  return result;
}

export function ShadingMatrix({surface,index,update,errors,latitude,longitude}:{surface:SurfaceForm;index:number;update:(i:number,p:Partial<SurfaceForm>)=>void;errors:FieldErrors;latitude:string;longitude:string}){
  const [showNight,setShowNight]=useState(false),[selectedMonths,setSelectedMonths]=useState(()=>Array(12).fill(true) as boolean[]);
  const [startHour,setStartHour]=useState(0),[endHour,setEndHour]=useState(12),[bulkValue,setBulkValue]=useState("100"),[shiftSummer,setShiftSummer]=useState(true),[bulkMessage,setBulkMessage]=useState("");
  const lat=Number(latitude),lon=Number(longitude),hasLocation=Number.isFinite(lat)&&Number.isFinite(lon)&&latitude!==""&&longitude!=="";
  const daylight=useMemo(()=>daylightMatrix(hasLocation?lat:51.1657,hasLocation?lon:10.4515),[hasLocation,lat,lon]);
  const visibleHours=hours.filter(hour=>showNight||daylight.some(row=>row[hour]));
  const selectPreset=(indices:number[])=>setSelectedMonths(months.map((_,month)=>indices.includes(month)));
  const applyBulk=(value=bulkValue)=>{
    const numeric=Number(value.replace(",","."));
    if(!selectedMonths.some(Boolean)){setBulkMessage("Bitte wähle mindestens einen Monat aus.");return;}
    if(startHour>=endHour){setBulkMessage("Die Startzeit muss vor der Endzeit liegen.");return;}
    if(!Number.isFinite(numeric)||numeric<0||numeric>100){setBulkMessage("Bitte gib eine Verschattung zwischen 0 und 100 % ein.");return;}
    const next=surface.shadingMatrix.map(row=>[...row]);
    selectedMonths.forEach((selected,month)=>{if(!selected)return;const summerShift=shiftSummer&&month>=3&&month<=8?1:0;for(let hour=Math.min(23,startHour+summerShift);hour<Math.min(24,endHour+summerShift);hour++)next[month][hour]=String(numeric);});
    update(index,{shadingMatrix:next});setBulkMessage(`${value} % auf die gewählten Monate und Zeitfenster angewendet.`);
  };
  return <div className={styles.shadingEditor}>
    <div className={styles.shadingExplanation}><div><h3>Verschattung nach Monat und lokaler Uhrzeit</h3><p>Die Stunden folgen der deutschen Ortszeit: MEZ im Winter, MESZ im Sommer. Ein festes Objekt wirkt auf der Uhr im Sommer typischerweise etwa eine Stunde später; Sonnenstand und Jahreszeit können den tatsächlichen Zeitpunkt zusätzlich verschieben.</p></div><label className={styles.toggle}><input type="checkbox" checked={showNight} onChange={event=>setShowNight(event.target.checked)}/> Astronomische Nachtstunden anzeigen</label></div>
    {!hasLocation&&<p className={styles.warning}>Für die Nachtfilterung wird vorübergehend die geografische Mitte Deutschlands verwendet. Nach der Standortwahl aktualisiert sich die Ansicht automatisch.</p>}
    <section className={styles.bulkEditor} aria-labelledby={`bulk-title-${surface.key}`}><h3 id={`bulk-title-${surface.key}`}>Zeitfenster gemeinsam bearbeiten</h3>
      <div className={styles.monthPresets} aria-label="Monatsauswahl"><button type="button" onClick={()=>selectPreset(Array.from({length:12},(_,month)=>month))}>Alle</button><button type="button" onClick={()=>selectPreset([10,11,0,1])}>Winter</button><button type="button" onClick={()=>selectPreset([3,4,5,6,7,8])}>Sommer</button><button type="button" onClick={()=>selectPreset([2,9])}>Übergang</button><button type="button" onClick={()=>selectPreset([])}>Keine</button></div>
      <div className={styles.monthChecks}>{months.map((month,monthIndex)=><label key={month}><input type="checkbox" checked={selectedMonths[monthIndex]} onChange={event=>setSelectedMonths(current=>current.map((value,index)=>index===monthIndex?event.target.checked:value))}/>{month}{(monthIndex===2||monthIndex===9)&&<small> Übergang</small>}</label>)}</div>
      <div className={styles.bulkFields}><label className={styles.field}><span>Von <small>inklusive</small></span><select value={startHour} onChange={event=>setStartHour(Number(event.target.value))}>{hours.map(hour=><option key={hour} value={hour}>{hour}:00</option>)}</select></label><label className={styles.field}><span>Bis <small>exklusive</small></span><select value={endHour} onChange={event=>setEndHour(Number(event.target.value))}>{Array.from({length:24},(_,index)=>index+1).map(hour=><option key={hour} value={hour}>{hour}:00</option>)}</select></label><label className={styles.field}><span>Verschattung <small>%</small></span><input type="number" min="0" max="100" step="any" value={bulkValue} onChange={event=>setBulkValue(event.target.value)}/></label></div>
      <label className={styles.toggle}><input type="checkbox" checked={shiftSummer} onChange={event=>setShiftSummer(event.target.checked)}/> April bis September automatisch um +1 Stunde verschieben</label><p className={styles.help}>März und Oktober enthalten MEZ und MESZ innerhalb desselben Monats. Die Monatsmatrix kann diesen Wechsel nur näherungsweise abbilden; prüfe beide Übergangsmonate bewusst.</p>
      <div className={styles.bulkActions}><button type="button" className={styles.add} onClick={()=>applyBulk()}>Auf Auswahl anwenden</button><button type="button" className={styles.quiet} onClick={()=>applyBulk("0")}>Auswahl auf 0 % setzen</button></div>{bulkMessage&&<p role="status" className={styles.locationStatus}>{bulkMessage}</p>}
    </section>
    <div className={styles.matrixLegend} aria-hidden="true"><span>0 %</span><span className={styles.legendGradient}/><span>100 %</span><span className={styles.nightKey}/> Nacht</div>
    <div className={styles.matrixWrap}><table><caption>Verschattung in Prozent nach Monat und lokaler Stunde (MEZ/MESZ)</caption><thead><tr><th scope="col">Monat</th>{visibleHours.map(hour=><th scope="col" key={hour}>{hour}:00</th>)}</tr></thead><tbody>{surface.shadingMatrix.map((row,month)=><tr key={month}><th scope="row">{months[month]}</th>{visibleHours.map(hour=>{const cell=row[hour],night=!daylight[month][hour];return <td key={hour} className={night?styles.nightCell:undefined}>{night&&!showNight?<span aria-label={`${months[month]}, ${hour}:00 Uhr: astronomische Nacht`}>–</span>:<input type="number" min="0" max="100" step="any" aria-label={`${months[month]}, ${hour}:00 Uhr`} aria-invalid={!!errors[`surfaces.${index}.matrix.${month}.${hour}`]} value={cell} style={{backgroundColor:`color-mix(in srgb, var(--sun) ${Math.max(0,Math.min(100,Number(cell)||0))}%, white)`}} onChange={event=>{const next=surface.shadingMatrix.map(matrixRow=>[...matrixRow]);next[month][hour]=event.target.value;update(index,{shadingMatrix:next});}}/>}</td>;})}</tr>)}</tbody></table></div>
  </div>;
}
