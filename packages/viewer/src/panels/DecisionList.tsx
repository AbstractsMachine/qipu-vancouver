import { useEffect, useMemo, useRef } from "react";
import type { Decision } from "../data/records";
import { type Currency, decadeOf, groupByDecade } from "./format";
import { DecadeSection } from "./DecadeSection";

export interface DecisionListProps {
  /** newest first, as the record comes */
  readonly decisions: readonly Decision[];
  /** the slider's year; its decade is marked and kept in view */
  readonly year: number;
  readonly kinds: Readonly<Record<string, string>>;
  readonly currency: Currency;
}

export function DecisionList({ decisions, year, kinds, currency }: DecisionListProps) {
  const groups = useMemo(() => groupByDecade(decisions), [decisions]);
  const currentDecade = decadeOf(year);
  const currentRef = useRef<HTMLElement>(null);
  const openedOn = useRef(currentDecade);

  /* the panel opens on its summary; moving the slider to another decade brings that decade into view */
  useEffect(() => {
    if (currentDecade === openedOn.current) return;
    openedOn.current = Number.NaN;
    const section = currentRef.current;
    // jsdom has no layout and no scrollIntoView.
    if (section && "scrollIntoView" in section) section.scrollIntoView({ block: "nearest" });
  }, [currentDecade]);

  return (
    <div className="qv-decisions">
      {groups.map(({ decade, items }) => (
        <DecadeSection
          key={decade}
          ref={decade === currentDecade ? currentRef : null}
          decade={decade}
          decisions={items}
          current={decade === currentDecade}
          kinds={kinds}
          currency={currency}
        />
      ))}
    </div>
  );
}
