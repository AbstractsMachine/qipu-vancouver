import { useId } from "react";
import type { Place } from "../data/records";
import { type Currency, countOf, formatMoney } from "./format";

export interface PlacesListProps {
  readonly places: readonly Place[];
  readonly currency: Currency;
  /** the place's page, or null where it has none */
  readonly placeHref: (slug: string) => string | null;
}

function moneyLine({ agreed, paid, contracts }: Place, currency: Currency): string {
  return [
    agreed === null ? null : `${formatMoney(agreed, currency)} agreed`,
    paid === null ? null : `${formatMoney(paid, currency)} paid`,
    contracts > 0 ? countOf(contracts, "contract") : null,
  ]
    .filter((part) => part !== null)
    .join(" · ");
}

export function PlacesList({ places, currency, placeHref }: PlacesListProps) {
  const headingId = useId();
  return (
    <section className="qv-places" aria-labelledby={headingId}>
      <h3 id={headingId}>Places on this block</h3>
      <ul className="qv-places__list">
        {places.map((place) => {
          const href = placeHref(place.slug);
          const money = moneyLine(place, currency);
          return (
            <li key={place.slug} className="qv-place">
              <p className="qv-place__name">
                {href === null ? place.name : <a href={href}>{place.name}</a>}
                {place.kind !== null && <span className="qv-place__kind"> {place.kind}</span>}
              </p>
              {money !== "" && <p className="qv-place__money">{money}</p>}
            </li>
          );
        })}
      </ul>
      <p className="qv-places__note">Figures cover the whole place, across all its blocks.</p>
    </section>
  );
}
