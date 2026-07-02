import styles from "./pv-economics-form.module.css";

type ProfileKind = "h25" | "exergypulse_daytime" | "exergypulse_evening" | "exergypulse_flatter";
type DayExample = { title:string; note:string; values:number[] };

const gaussian = (hour:number, center:number, width:number, height:number) => height*Math.exp(-(((hour-center)/width)**2));
const curve = (base:number, scale:number, peaks:Array<[number,number,number]>) => Array.from({length:24},(_,hour)=>scale*(base+peaks.reduce((sum,[center,width,height])=>sum+gaussian(hour,center,width,height),0)));

const examples:DayExample[] = [
  {title:"Winter · Werktag",note:"Morgen- und ausgeprägte Abendspitze",values:curve(.25,1,[[7.2,2,.42],[12.5,4,.16],[19,2.6,.72]])},
  {title:"Sommer · Samstag",note:"Späterer Start, breitere Tageslast",values:curve(.2,.78,[[9.5,2.8,.34],[14,4,.2],[20,2.8,.48]])},
  {title:"Übergang · Sonn-/Feiertag",note:"Gleichmäßigerer Tag mit Abendspitze",values:curve(.23,.9,[[10,3.2,.28],[15,4.5,.2],[19.5,2.8,.55]])},
];

const information:Record<ProfileKind,{title:string;summary:string;points:string[]}> = {
  h25:{title:"BDEW H25 (Standard)",summary:"Standardisiertes Haushaltsprofil mit saisonalen Verläufen und getrennten Kurven für Werktage, Samstage sowie Sonn- und Feiertage.",points:["Berücksichtigt Bundesland-Feiertage und die jahreszeitliche BDEW-Dynamisierung.","Enthält typische Morgen- und Abendspitzen, aber keine individuellen Gewohnheiten.","Wärmepumpe und Elektroauto sind nur im Jahresverbrauch enthalten, nicht als eigene Lasten."]},
  exergypulse_daytime:{title:"ExergyPulse Tagesprofil",summary:"Synthetisches Szenario für einen Haushalt mit stärkerem Verbrauch während des Tages.",points:["15 % der Last außerhalb von 10:00 bis 17:00 Uhr werden in dieses Zeitfenster verschoben.","Die zeitliche Form innerhalb und außerhalb des Fensters bleibt proportional erhalten.","Der Jahresverbrauch bleibt exakt gleich; das Profil stammt nicht aus deinen Messdaten."]},
  exergypulse_evening:{title:"ExergyPulse Abendprofil",summary:"Synthetisches Szenario für einen Haushalt mit stärkerem Verbrauch am späten Nachmittag und Abend.",points:["15 % der Last außerhalb von 17:00 bis 23:00 Uhr werden in dieses Zeitfenster verschoben.","Die vorhandene Abendstruktur wird proportional verstärkt, nicht durch eine einzelne starre Spitze ersetzt.","Der Jahresverbrauch bleibt exakt gleich; das Profil stammt nicht aus deinen Messdaten."]},
  exergypulse_flatter:{title:"ExergyPulse gleichmäßigeres Profil",summary:"Synthetisches Szenario mit schwächeren Spitzen und einer gleichmäßigeren Last über das Jahr.",points:["Jeder Stundenwert wird zu 15 % mit dem jährlichen mittleren Stundenwert gemischt.","Hohe Lasten sinken, niedrige Lasten steigen; Zeit- und Saisonmuster bleiben zu 85 % erhalten.","Der Jahresverbrauch bleibt exakt gleich; das Profil stammt nicht aus deinen Messdaten."]},
};

function transform(values:number[],kind:ProfileKind) {
  if(kind==="h25") return values;
  if(kind==="exergypulse_flatter") { const mean=values.reduce((sum,value)=>sum+value,0)/values.length; return values.map(value=>.85*value+.15*mean); }
  const [start,end]=kind==="exergypulse_daytime"?[10,16]:[17,22];
  const inside=values.reduce((sum,value,hour)=>sum+(hour>=start&&hour<=end?value:0),0);
  const outside=values.reduce((sum,value,hour)=>sum+(hour<start||hour>end?value:0),0);
  const moved=outside*.15;
  return values.map((value,hour)=>hour>=start&&hour<=end?value+moved*value/inside:value*.85);
}

export function LoadProfilePreview({kind}:{kind:string}) {
  const selected=(kind in information?kind:"h25") as ProfileKind;
  const info=information[selected];
  const transformed=examples.map(example=>({...example,values:transform(example.values,selected)}));
  const maximum=Math.max(...transformed.flatMap(example=>example.values));
  return <section className={styles.profilePreview} aria-labelledby="profile-preview-title">
    <div className={styles.profileIntro}><div><p className={styles.profileKicker}>Gewähltes Lastprofil</p><h3 id="profile-preview-title">{info.title}</h3><p>{info.summary}</p></div><ul>{info.points.map(point=><li key={point}>{point}</li>)}</ul></div>
    <div className={styles.profilePlots}>{transformed.map(example=><ProfilePlot key={example.title} example={example} maximum={maximum}/>)}</div>
    <p className={styles.profileCaption}>Schematische, auf eine gemeinsame Skala normierte Tagesverläufe. Sie zeigen Charakter und Veränderungsrichtung, nicht die BDEW-Originalwertetabelle oder deinen absoluten Verbrauch.</p>
  </section>;
}

function ProfilePlot({example,maximum}:{example:DayExample;maximum:number}) {
  const x=(hour:number)=>18+hour/23*264, y=(value:number)=>92-value/maximum*72;
  const points=example.values.map((value,hour)=>`${x(hour)},${y(value)}`).join(" ");
  return <figure className={styles.profilePlot}><figcaption><strong>{example.title}</strong><span>{example.note}</span></figcaption><svg viewBox="0 0 300 118" role="img" aria-label={`Schematischer Lastverlauf: ${example.title}. ${example.note}.`}>
    <g aria-hidden="true"><line x1="18" x2="282" y1="92" y2="92" className={styles.profileAxis}/>{[0,6,12,18,23].map(hour=><g key={hour}><line x1={x(hour)} x2={x(hour)} y1="92" y2="96" className={styles.profileAxis}/><text x={x(hour)} y="109" textAnchor="middle">{hour}</text></g>)}<polyline points={points} className={styles.profileLine}/><path d={`${points.split(" ").map((point,index)=>`${index?"L":"M"}${point}`).join(" ")} L282,92 L18,92 Z`} className={styles.profileArea}/></g>
  </svg></figure>;
}
