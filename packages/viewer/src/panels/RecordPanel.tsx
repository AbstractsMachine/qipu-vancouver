import { useEffect, useId, useRef } from "react";
import type { CityConfig } from "../config";
import type { BlockRecord, Place } from "../data/records";
import { DecisionList } from "./DecisionList";
import { recordSummary, streetLabel } from "./format";
import { PlacesList } from "./PlacesList";
import { ShareButton } from "./ShareButton";

export type RecordLoad =
  | { readonly status: "loading" }
  | { readonly status: "error"; readonly message: string }
  | {
      readonly status: "ready";
      readonly record: BlockRecord;
      readonly places: readonly Place[];
      /** a place's page, or null where it has none */
      readonly placeHref: (slug: string) => string | null;
    };

export interface RecordPanelProps {
  readonly city: CityConfig;
  readonly block: { readonly id: string; readonly neighbourhood: string | null };
  readonly load: RecordLoad;
  /** the slider's year */
  readonly year: number;
  readonly shareUrl: string;
  readonly onClose: () => void;
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

/**
 * The record of one block, beside the map. The map stays usable while it is
 * open, so the panel is an aside with no focus trap.
 */
export function RecordPanel({ city, block, load, year, shareUrl, onClose }: RecordPanelProps) {
  const headingId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // On close, focus goes back to whatever opened the panel.
  useEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  useEffect(() => {
    closeRef.current?.focus();
  }, [block.id]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) onClose();
    };
    panel.addEventListener("keydown", onKey);
    return () => {
      panel.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <aside ref={panelRef} className="qv-panel" aria-labelledby={headingId}>
      <header className="qv-panel__header">
        <h2 id={headingId} className="qv-panel__title">
          {block.neighbourhood !== null && (
            <>
              <span className="qv-panel__hood">{block.neighbourhood}</span>{" "}
            </>
          )}
          <span className="qv-panel__block">Block {block.id}</span>
        </h2>
        <button ref={closeRef} type="button" className="qv-button qv-panel__close" aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </button>
        <ShareButton url={shareUrl} />
      </header>
      <div className="qv-panel__body">
        <RecordBody city={city} load={load} year={year} />
      </div>
    </aside>
  );
}

function RecordBody({ city, load, year }: Pick<RecordPanelProps, "city" | "load" | "year">) {
  const { kinds, currency, scope } = city.record;
  if (load.status === "loading") {
    return (
      <p role="status" className="qv-panel__status">
        Loading this block&apos;s record…
      </p>
    );
  }
  if (load.status === "error") {
    return (
      <div role="alert" className="qv-panel__status qv-panel__status--error">
        <p>This block&apos;s record could not be loaded. Try again in a moment.</p>
        <p className="qv-panel__detail">{load.message}</p>
      </div>
    );
  }
  const { record, places, placeHref } = load;
  const summary = recordSummary(record.decisions);
  return (
    <>
      <p className="qv-panel__summary">{summary ?? "No decisions are placed on this block yet."}</p>
      {record.streets.length > 0 && (
        <p className="qv-panel__streets">On {record.streets.map(streetLabel).join(" · ")}</p>
      )}
      <p className="qv-panel__scope">{scope}</p>
      {places.length > 0 && <PlacesList places={places} currency={currency} placeHref={placeHref} />}
      <DecisionList key={record.blockId} decisions={record.decisions} year={year} kinds={kinds} currency={currency} />
    </>
  );
}
