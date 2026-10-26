import type { Source } from "../data/sources";
import { sourceLabel } from "./format";

export interface SourceLinkProps {
  readonly source: Source;
}

export function SourceLink({ source }: SourceLinkProps) {
  return (
    <a className="qv-source" href={source.href} target="_blank" rel="noopener noreferrer">
      {sourceLabel(source)}
      {source.approximate && source.page !== null && (
        <>
          {" "}
          <span className="qv-source__approx">(page may be off by one or two)</span>
        </>
      )}{" "}
      <span className="qv-visually-hidden">(opens in a new tab)</span>
    </a>
  );
}
