import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { YearSlider } from "./YearSlider";

const keyYears = [1906, 1938, 1959, 1985, 2006, 2026];

describe("YearSlider", () => {
  it("is a labelled range input showing the year", () => {
    render(<YearSlider first={1906} present={2026} value={1938} keyYears={keyYears} onChange={vi.fn()} />);
    const slider = screen.getByRole("slider", { name: "Year" });
    expect(slider).toHaveAttribute("min", "1906");
    expect(slider).toHaveAttribute("max", "2026");
    expect(slider).toHaveAttribute("step", "1");
    expect(slider).toHaveValue("1938");
    expect(slider).toHaveAttribute("aria-valuetext", "1938");
    expect(screen.getByRole("status")).toHaveTextContent("1938");
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });

  it("says Today at the present year", () => {
    render(<YearSlider first={1906} present={2026} value={2026} keyYears={keyYears} onChange={vi.fn()} />);
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Year" })).toHaveAttribute("aria-valuetext", "2026, today");
  });

  it("marks the key years as ticks", () => {
    const { container } = render(
      <YearSlider first={1906} present={2026} value={1938} keyYears={keyYears} onChange={vi.fn()} />,
    );
    const options = Array.from(container.querySelectorAll("datalist option"), (o) => o.getAttribute("value"));
    expect(options).toEqual(["1906", "1938", "1959", "1985", "2006", "2026"]);
    const slider = screen.getByRole("slider", { name: "Year" });
    expect(container.querySelector(`datalist#${CSS.escape(slider.getAttribute("list") ?? "")}`)).not.toBeNull();
  });

  it("reports the year the reader picks", () => {
    const onChange = vi.fn();
    render(<YearSlider first={1906} present={2026} value={1938} keyYears={keyYears} onChange={onChange} />);
    fireEvent.change(screen.getByRole("slider", { name: "Year" }), { target: { value: "1959" } });
    expect(onChange).toHaveBeenCalledWith(1959);
  });

  it("has no Play button unless the parent can play", () => {
    render(<YearSlider first={1906} present={2026} value={1938} keyYears={keyYears} onChange={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("toggles play", async () => {
    const user = userEvent.setup();
    const onPlayToggle = vi.fn();
    const { rerender } = render(
      <YearSlider
        first={1906}
        present={2026}
        value={1938}
        keyYears={keyYears}
        onChange={vi.fn()}
        onPlayToggle={onPlayToggle}
      />,
    );
    const play = screen.getByRole("button", { name: "Play through the years" });
    expect(play).toHaveAttribute("aria-pressed", "false");
    await user.click(play);
    expect(onPlayToggle).toHaveBeenCalledTimes(1);

    rerender(
      <YearSlider
        first={1906}
        present={2026}
        value={1938}
        keyYears={keyYears}
        onChange={vi.fn()}
        playing
        onPlayToggle={onPlayToggle}
      />,
    );
    expect(play).toHaveAttribute("aria-pressed", "true");
  });
});
