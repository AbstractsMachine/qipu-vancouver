import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CityConfig } from "./config";
import { type CityData, loadCityData } from "./data/city";
import { clampYear } from "./eras/timeline";
import type { MapView } from "./map/city-map";
import { RecordPanel, type RecordLoad, YearSlider } from "./panels";
import { useLoad, usePlay, useUrlSync } from "./state/hooks";
import { useCityMap } from "./state/use-city-map";
import { type ViewState, writeViewState } from "./state/url";
import { loadPainting } from "./tiles/load";

export interface ViewerProps {
  readonly city: CityConfig;
  /** where to open: usually `readViewState(location.search)` */
  readonly initial?: ViewState;
  /** keep the address bar in step with the view, so it can be shared */
  readonly syncUrl?: boolean;
  /** "cpu" draws the eras without WebGL */
  readonly compositor?: "auto" | "cpu";
  /** shown above the map, e.g. a note that the records are a sample */
  readonly notice?: string;
}

interface Selection {
  readonly position: number;
  /** move the map to it: true when the selection came from a link, not a click */
  readonly fly: boolean;
}

/**
 * The whole viewer: the painted map, the year slider and the record of the
 * block a reader clicks. Loads in tiers: the painting's index and eras first
 * (the map can draw), then the blocks (clicks work), then one block's record
 * per click.
 */
export function Viewer({ city, initial = {}, syncUrl = false, compositor = "auto", notice }: ViewerProps) {
  const container = useRef<HTMLDivElement>(null);
  const painting = useLoad(city.id, () => loadPainting(city));
  const data = useLoad(city.id, () => loadCityData(city));
  const eras = painting.status === "ready" ? painting.value.eras : null;
  const present = eras?.presentYear ?? new Date().getFullYear();
  const first = eras?.firstYear ?? present;

  const [year, setYear] = useState(initial.year ?? present);
  const [playing, setPlaying] = useState(false);
  const [view, setView] = useState<MapView | undefined>(initial.at);
  /* undefined until the reader picks or closes something: until then a block named in the link is open */
  const [picked, setPicked] = useState<Selection | null | undefined>(undefined);
  const shownYear = clampYear(year, first, present);

  const map = useCityMap({
    container,
    city,
    painting: painting.status === "ready" ? painting.value : null,
    initialYear: shownYear,
    initialView: initial.at,
    compositor,
    onPick: (position) => {
      setPicked(position === null ? null : { position, fly: false });
    },
    onViewChange: setView,
  });

  useEffect(() => map?.setYear(shownYear), [map, shownYear]);

  const cityData = data.status === "ready" ? data.value : null;
  useEffect(() => {
    if (map && cityData) map.setBlocks(cityData.blocks);
  }, [map, cityData]);

  /* a block named in the link opens once the blocks have arrived, and the map flies to it unless the link also sets the view */
  const linked = initial.block && cityData ? cityData.blocks.ids.indexOf(initial.block) : -1;
  const selection: Selection | null =
    picked !== undefined ? picked : linked >= 0 ? { position: linked, fly: !initial.at } : null;

  const selectedPosition = selection?.position ?? null;
  const fly = selection?.fly ?? false;
  useEffect(() => {
    map?.select(selectedPosition, fly);
  }, [map, selectedPosition, fly]);

  const stopPlaying = useCallback(() => {
    setPlaying(false);
  }, []);
  usePlay(playing, shownYear, present, setYear, stopPlaying);

  const blockId = selection && cityData ? (cityData.blocks.ids[selection.position] ?? null) : null;
  const state: ViewState = {
    city: city.id,
    ...(shownYear !== present ? { year: shownYear } : {}),
    ...(view ? { at: view } : {}),
    ...(blockId ? { block: blockId } : {}),
  };
  useUrlSync(state, syncUrl);
  const shareUrl = useShareUrl(state);

  return (
    <div className={selection ? "qv-viewer qv-viewer--panel-open" : "qv-viewer"} data-city={city.id} data-compositor={map?.compositorKind()}>
      <div ref={container} className="qv-map" />
      <div className="qv-messages">
        {notice ? <p className="qv-notice">{notice}</p> : null}
        {painting.status === "error" ? (
          <p className="qv-status" role="alert">
            The map could not load: {painting.message}
          </p>
        ) : null}
        {data.status === "error" ? (
          <p className="qv-status" role="status">
            Block records are unavailable: {data.message}
          </p>
        ) : null}
      </div>
      {eras ? (
        <div className="qv-slider-dock">
          <YearSlider
            first={first}
            present={present}
            value={shownYear}
            keyYears={eras.keyYears}
            onChange={(y) => {
              setPlaying(false);
              setYear(y);
            }}
            playing={playing}
            onPlayToggle={() => {
              if (!playing && shownYear >= present) setYear(first);
              setPlaying(!playing);
            }}
          />
        </div>
      ) : null}
      {selection && cityData && blockId ? (
        <BlockRecordPanel
          key={blockId}
          city={city}
          data={cityData}
          position={selection.position}
          year={shownYear}
          shareUrl={shareUrl}
          onClose={() => {
            setPicked(null);
          }}
        />
      ) : null}
    </div>
  );
}

interface BlockRecordPanelProps {
  readonly city: CityConfig;
  readonly data: CityData;
  readonly position: number;
  readonly year: number;
  readonly shareUrl: string;
  readonly onClose: () => void;
}

function BlockRecordPanel({ city, data, position, year, shareUrl, onClose }: BlockRecordPanelProps) {
  const id = data.blocks.ids[position] ?? "";
  const hood = data.blocks.neighbourhoods[data.blocks.hood[position] ?? -1] ?? null;
  const loaded = useLoad(id, async () => {
    const [record, places, placePath] = await Promise.all([data.record(position), data.places(id), data.placePath()]);
    return { record, places, placePath };
  });

  const load: RecordLoad = useMemo(() => {
    if (loaded.status !== "ready") return loaded;
    const { record, places, placePath } = loaded.value;
    const site = city.site;
    return {
      status: "ready",
      record,
      places,
      placeHref: (slug) => (site && placePath ? `${site.base}${placePath.replace("{slug}", slug)}` : null),
    };
  }, [loaded, city.site]);

  return (
    <RecordPanel
      city={city}
      block={{ id, neighbourhood: hood }}
      load={load}
      year={year}
      shareUrl={shareUrl}
      onClose={onClose}
    />
  );
}

function useShareUrl(state: ViewState): string {
  if (typeof window === "undefined") return writeViewState(state);
  return `${window.location.origin}${window.location.pathname}${writeViewState(state)}`;
}
