/**
 * Where a decision can be read in the original. The row's citation `u` has
 * the same shape in every record system and only the system code `c` says
 * which one resolves it, so the two are always read together.
 *
 *   (none)  a scanned volume on the Internet Archive: `u` = "<identifier>/<leaf>"
 *   b       a PDF the San Francisco Clerk posted:      `u` = "<stem>/<page>"
 *   l       a Legistar meeting:                        `u` = "<id>~<guid>/<page>"
 *   x       the row carries its own URL in `u`
 */
import { FormatError } from "./validate";

export type SourceSystem = "archive" | "clerk" | "legistar" | "url";

export interface Source {
  readonly system: SourceSystem;
  readonly href: string;
  /** the page, where the citation names one */
  readonly page: number | null;
  /** the document or host, for the link's label */
  readonly document: string;
  /** the page link may be a page or two off */
  readonly approximate: boolean;
}

export function sourceOf(row: { u: string; c: string | undefined; approx: boolean }): Source {
  const { u, c, approx } = row;
  if (c === "x") {
    // The row's own URL becomes a link: only a web page, never javascript:, data: or the like.
    if (!/^https?:\/\//i.test(u)) throw new FormatError("source.u", `an http(s) URL (got "${u.slice(0, 40)}")`);
    return { system: "url", href: u, page: pageInUrl(u), document: hostOf(u), approximate: approx };
  }
  const slash = u.lastIndexOf("/");
  const doc = slash >= 0 ? u.slice(0, slash) : u;
  const pageText = slash >= 0 ? u.slice(slash + 1) : "";
  const page = /^\d+$/.test(pageText) ? Number(pageText) : null;
  const anchor = page === null ? "" : `#page=${page}`;
  if (c === "l") {
    const [id = "", guid = ""] = doc.split("~");
    return {
      system: "legistar",
      href: `https://sfgov.legistar.com/View.ashx?M=M&ID=${encodeURIComponent(id)}&GUID=${encodeURIComponent(guid)}${anchor}`,
      page,
      document: "Legistar minutes",
      approximate: approx,
    };
  }
  if (c === "b") {
    return {
      system: "clerk",
      href: `https://sfbos.org/sites/default/files/${encodeURIComponent(doc)}_minutes.pdf${anchor}`,
      page,
      document: `${doc} minutes`,
      approximate: approx,
    };
  }
  return {
    system: "archive",
    href: `https://archive.org/details/${encodeURIComponent(doc)}${page === null ? "" : `/page/n${page}/mode/1up`}`,
    page,
    document: doc,
    approximate: approx,
  };
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function pageInUrl(url: string): number | null {
  const m = /(?:#page=|\/page\/n)(\d+)/.exec(url);
  return m ? Number(m[1]) : null;
}
