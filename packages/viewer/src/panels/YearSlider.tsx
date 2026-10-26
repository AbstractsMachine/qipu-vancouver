import { type CSSProperties, type RefObject, useEffect, useId, useRef, useState } from "react";
import { sliderTicks } from "../eras/timeline";

export interface YearSliderProps {
  readonly first: number;
  readonly present: number;
  readonly value: number;
  /** years the map has a painted key for; they become the tick marks */
  readonly keyYears: readonly number[];
  readonly onChange: (year: number) => void;
  readonly playing?: boolean;
  /** shows the Play button; the parent moves the year while playing */
  readonly onPlayToggle?: () => void;
}

function PlayIcon({ playing }: { readonly playing: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      {playing ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="M4 2.5v11l9-5.5z" />}
    </svg>
  );
}

/** A tick label needs about this many pixels, so narrow sliders show fewer years. */
const LABEL_PX = 46;

function useWidth(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [ref]);
  return width;
}

export function YearSlider({
  first,
  present,
  value,
  keyYears,
  onChange,
  playing = false,
  onPlayToggle,
}: YearSliderProps) {
  const inputId = useId();
  const ticksId = useId();
  const ticksRef = useRef<HTMLDivElement>(null);
  const span = Math.max(1, present - first);
  const width = useWidth(ticksRef, 600);
  const ticks = sliderTicks(keyYears, first, present, Math.max(8, Math.ceil((span * LABEL_PX) / Math.max(width, 1))));
  const isToday = value === present;

  return (
    <div className="qv-slider">
      {onPlayToggle && (
        <button
          type="button"
          className="qv-button qv-slider__play"
          aria-pressed={playing}
          aria-label="Play through the years"
          onClick={onPlayToggle}
        >
          <PlayIcon playing={playing} />
        </button>
      )}
      <div className="qv-slider__body">
        <div className="qv-slider__readout">
          <label className="qv-slider__label" htmlFor={inputId}>
            Year
          </label>
          <output className="qv-slider__year" htmlFor={inputId}>
            {value}
          </output>
          {isToday && <span className="qv-slider__today">Today</span>}
        </div>
        <input
          id={inputId}
          className="qv-slider__input"
          type="range"
          min={first}
          max={present}
          step={1}
          value={value}
          list={ticksId}
          aria-valuetext={isToday ? `${value}, today` : String(value)}
          onChange={(event) => {
            onChange(event.currentTarget.valueAsNumber);
          }}
        />
        <datalist id={ticksId}>
          {ticks.map((year) => (
            <option key={year} value={year} />
          ))}
        </datalist>
        <div ref={ticksRef} className="qv-slider__ticks" aria-hidden="true">
          {ticks.map((year) => (
            <span key={year} className="qv-slider__tick" style={{ "--qv-at": (year - first) / span } as CSSProperties}>
              {year}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
