import { type Ref, useEffect, useId, useRef, useState } from "react";
import type { Decision } from "../data/records";
import { type Currency, countOf } from "./format";
import { DecisionItem } from "./DecisionItem";

/** Rows a decade shows before its "Show all" button. */
export const DECADE_PREVIEW = 30;

export interface DecadeSectionProps {
  readonly decade: number;
  readonly decisions: readonly Decision[];
  /** the decade holding the slider's year */
  readonly current: boolean;
  readonly kinds: Readonly<Record<string, string>>;
  readonly currency: Currency;
  readonly ref?: Ref<HTMLElement>;
}

export function DecadeSection({ decade, decisions, current, kinds, currency, ref }: DecadeSectionProps) {
  const headingId = useId();
  const [expanded, setExpanded] = useState(false);
  const firstRevealed = useRef<HTMLLIElement>(null);
  const shown = expanded ? decisions : decisions.slice(0, DECADE_PREVIEW);
  const hidden = decisions.length - shown.length;

  // The button disappears once pressed, so focus moves on to the first row it revealed.
  useEffect(() => {
    if (expanded) firstRevealed.current?.focus();
  }, [expanded]);

  return (
    <section
      ref={ref}
      className={current ? "qv-decade qv-decade--current" : "qv-decade"}
      aria-labelledby={headingId}
      aria-current={current ? "true" : undefined}
    >
      <h3 id={headingId} className="qv-decade__heading">
        {decade}s <span className="qv-decade__count">{countOf(decisions.length, "decision")}</span>
        {current && <span className="qv-decade__mark">map year</span>}
      </h3>
      <ol className="qv-decade__list">
        {shown.map((decision, i) => (
          <DecisionItem
            // Rows carry no id; within one block's decade, order is stable.
            key={i}
            ref={i === DECADE_PREVIEW ? firstRevealed : null}
            decision={decision}
            kinds={kinds}
            currency={currency}
          />
        ))}
      </ol>
      {hidden > 0 && (
        <button
          type="button"
          className="qv-button qv-decade__more"
          onClick={() => {
            setExpanded(true);
          }}
        >
          Show all {countOf(decisions.length, "decision")}
        </button>
      )}
    </section>
  );
}
