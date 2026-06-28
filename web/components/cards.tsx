import Link from "next/link";
import { Icon } from "@/components/icon";
import type { IconName } from "@/lib/site";

type CardProps = {
  title: string;
  description: string;
  icon: IconName;
  href?: string;
  status?: string;
};

export function TopicCard({ title, description, icon, href, status }: CardProps) {
  const content = (
    <>
      <div className="card-icon"><Icon name={icon} /></div>
      <div className="card-heading">
        <h3>{title}</h3>
        {status && <span className="status-label">{status}</span>}
      </div>
      <p>{description}</p>
      {href && <span className="text-link">Thema ansehen <span aria-hidden="true">→</span></span>}
    </>
  );

  return href ? <Link className="topic-card" href={href}>{content}</Link> : <article className="topic-card topic-card-muted">{content}</article>;
}

export function CalculatorCard({ title, description, icon, href, status }: Required<CardProps>) {
  return (
    <article className="calculator-card">
      <div className="calculator-card-top">
        <div className="card-icon"><Icon name={icon} /></div>
        <span className="status-label">{status}</span>
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      <Link className="button button-secondary" href={href}>Details ansehen</Link>
    </article>
  );
}
