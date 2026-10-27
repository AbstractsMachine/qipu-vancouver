import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Place } from "../data/records";
import { PlacesList } from "./PlacesList";

const library: Place = {
  slug: "mount-pleasant-branch-library",
  name: "Mount Pleasant Branch Library",
  kind: "library",
  agreed: 12_500_000,
  paid: 9_000_000,
  contracts: 4,
};

const park: Place = {
  slug: "jonathan-rogers-park",
  name: "Jonathan Rogers Park",
  kind: null,
  agreed: 300_000,
  paid: null,
  contracts: 1,
};

const plaza: Place = { slug: "plaza", name: "Plaza", kind: "plaza", agreed: null, paid: null, contracts: 0 };

const hrefFor = (slug: string) => (slug === "plaza" ? null : `/places/${slug}`);

describe("PlacesList", () => {
  it("lists each place with its money in the city's currency", () => {
    render(<PlacesList places={[library, park]} currency="CAD" placeHref={hrefFor} />);
    expect(screen.getByRole("heading", { name: "Places on this block" })).toBeInTheDocument();
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(first!).getByText("CA$12,500,000 agreed · CA$9,000,000 paid · 4 contracts")).toBeInTheDocument();
    expect(within(first!).getByText("library")).toBeInTheDocument();
    expect(within(second!).getByText("CA$300,000 agreed · 1 contract")).toBeInTheDocument();
    expect(screen.getByText("Figures cover the whole place, across all its blocks.")).toBeInTheDocument();
  });

  it("links to a place's page where it has one", () => {
    render(<PlacesList places={[library, plaza]} currency="USD" placeHref={hrefFor} />);
    expect(screen.getByRole("link", { name: "Mount Pleasant Branch Library" })).toHaveAttribute(
      "href",
      "/places/mount-pleasant-branch-library",
    );
    expect(screen.queryByRole("link", { name: "Plaza" })).not.toBeInTheDocument();
    expect(screen.getByText("$12,500,000 agreed · $9,000,000 paid · 4 contracts")).toBeInTheDocument();
  });

  it("leaves out the money line for a place with no figures", () => {
    render(<PlacesList places={[plaza]} currency="CAD" placeHref={hrefFor} />);
    const item = screen.getByRole("listitem");
    expect(item.querySelector(".qv-place__money")).toBeNull();
  });
});
