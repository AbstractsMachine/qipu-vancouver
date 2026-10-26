import type { Ref } from "react";
import type { Decision } from "../data/records";
import { type Currency, formatDate, formatMoney, isoDate, outcomeWord, precisionPhrase, streetLabel } from "./format";
import { SourceLink } from "./SourceLink";

export interface DecisionItemProps {
  readonly decision: Decision;
  /** record series names by row code, from the city config */
  readonly kinds: Readonly<Record<string, string>>;
  readonly currency: Currency;
  readonly ref?: Ref<HTMLLIElement>;
}

export function DecisionItem({ decision, kinds, currency, ref }: DecisionItemProps) {
  const { year, date, kind, outcome, plain, printed, precision, address, amount } = decision;
  const word = outcomeWord(outcome);
  const where = [
    precision === null ? null : precisionPhrase(precision),
    address === null ? null : streetLabel(address),
    amount === null ? null : formatMoney(amount, currency),
  ].filter((part) => part !== null);

  return (
    <li className="qv-decision" ref={ref} tabIndex={-1}>
      <p className="qv-decision__meta">
        <time dateTime={isoDate(year, date)}>{formatDate(year, date)}</time>
        <span className="qv-decision__kind">{kinds[kind] ?? kind}</span>
        {word !== null && <span className={`qv-outcome qv-outcome--${outcome ?? ""}`}>{word}</span>}
      </p>
      <p className="qv-decision__text">{plain ?? printed}</p>
      {plain !== null && (
        <>
          <p className="qv-decision__note">qipu&apos;s summary</p>
          <details className="qv-decision__printed">
            <summary>As printed</summary>
            <blockquote>{printed}</blockquote>
          </details>
        </>
      )}
      {where.length > 0 && <p className="qv-decision__where">{where.join(" · ")}</p>}
      <SourceLink source={decision.source} />
    </li>
  );
}
