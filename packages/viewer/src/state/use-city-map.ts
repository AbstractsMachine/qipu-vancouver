import { type RefObject, useEffect, useEffectEvent, useState } from "react";
import type { CityConfig } from "../config";
import { type CityMap, type MapView, createCityMap } from "../map/city-map";
import type { Painting } from "../tiles/load";

export interface CityMapHookOptions {
  readonly container: RefObject<HTMLDivElement | null>;
  readonly city: CityConfig;
  readonly painting: Painting | null;
  readonly initialYear: number;
  readonly initialView: MapView | undefined;
  readonly compositor: "auto" | "cpu";
  onPick(position: number | null): void;
  onViewChange(view: MapView): void;
}

/**
 * Mount the Leaflet map once the painting's index has arrived, and tear it
 * down when the city changes. Returns the map, or null until it exists.
 */
export function useCityMap(options: CityMapHookOptions): CityMap | null {
  const [map, setMap] = useState<CityMap | null>(null);
  const { container, city, painting, compositor } = options;
  const onPick = useEffectEvent((p: number | null) => {
    options.onPick(p);
  });
  const onViewChange = useEffectEvent((v: MapView) => {
    options.onViewChange(v);
  });
  const initial = useEffectEvent(() => ({ year: options.initialYear, view: options.initialView }));

  useEffect(() => {
    const element = container.current;
    if (!element || !painting) return;
    const { year, view } = initial();
    const m = createCityMap({
      element,
      city,
      index: painting.index,
      eras: painting.eras,
      year,
      view,
      compositor,
      onPick: (p) => {
        onPick(p);
      },
      onViewChange: (v) => {
        onViewChange(v);
      },
    });
    /* the map is an external object made here; holding its handle in state re-renders the tree that drives it */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMap(m);
    return () => {
      m.destroy();
      setMap(null);
    };
  }, [container, city, painting, compositor]);

  return map;
}
