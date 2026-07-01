import { cashflowSeries, formatEuro, ScenarioEconomics } from "@/lib/pv-economics-response";
import styles from "./pv-economics-results.module.css";

type Line = { label:string; economics:ScenarioEconomics; className:string; dash?:string };

export function CashflowChart({lines}:{lines:Line[]}) {
  const series=lines.map(line=>({...line,points:cashflowSeries(line.economics)})).filter(x=>x.points.length);
  if(!series.length)return <p>Ein Zahlungsstromdiagramm ist wegen fehlender Investitionsangaben nicht verfügbar.</p>;
  const values=series.flatMap(x=>x.points.map(p=>p.value)); const years=Math.max(...series.flatMap(x=>x.points.map(p=>p.year)),1);
  const min=Math.min(0,...values),max=Math.max(0,...values); const span=Math.max(max-min,1); const x=(year:number)=>70+year/years*650; const y=(value:number)=>20+(max-value)/span*230;
  const ticks=Array.from({length:5},(_,i)=>min+span*i/4).filter(value=>Math.abs(value)>span*1e-9);
  return <div className={styles.chartBlock}>
    <svg className={styles.chart} viewBox="0 0 760 300" role="img" aria-labelledby="cashflow-title cashflow-desc">
      <title id="cashflow-title">Kumulierter nominaler Zahlungsstrom</title><desc id="cashflow-desc">Entwicklung von der Anfangsinvestition in Jahr null bis zum Ende des Betrachtungszeitraums. Die Werte stehen zusätzlich in der Datentabelle.</desc>
      <g aria-hidden="true"><line x1="70" x2="720" y1={y(0)} y2={y(0)} className={styles.zero}/><text x="62" y={y(0)+4} textAnchor="end">0 €</text>{ticks.map(t=><g key={t}><line x1="70" x2="720" y1={y(t)} y2={y(t)} className={styles.gridLine}/><text x="62" y={y(t)+4} textAnchor="end">{new Intl.NumberFormat("de-DE",{notation:"compact",maximumFractionDigits:1}).format(t)} €</text></g>)}
        {[0,Math.ceil(years/2),years].map(t=><text key={t} x={x(t)} y="280" textAnchor="middle">Jahr {t}</text>)}
        {series.map(line=><polyline key={line.label} points={line.points.map(p=>`${x(p.year)},${y(p.value)}`).join(" ")} className={line.className} strokeDasharray={line.dash}/>)}</g>
    </svg>
    <ul className={styles.legend}>{series.map(x=><li key={x.label}><span className={x.className} aria-hidden="true"/> {x.label}</li>)}</ul>
    <div className={styles.tableWrap}><table><caption>Kumulierter nominaler Zahlungsstrom in Euro</caption><thead><tr><th scope="col">Jahr</th>{series.map(x=><th scope="col" key={x.label}>{x.label}</th>)}</tr></thead><tbody>{Array.from({length:years+1},(_,year)=><tr key={year}><th scope="row">{year}</th>{series.map(x=><td key={x.label}>{formatEuro(x.points.find(p=>p.year===year)?.value??null)}</td>)}</tr>)}</tbody></table></div>
  </div>;
}
