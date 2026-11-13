import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HealthDot, ResultBadge, SourceBadge } from "@/components/ui/Badges";
import { Markdown } from "@/components/ui/Markdown";
import { fmtDuration } from "@/lib/format";

describe("status is never color-only", () => {
  it("source badges carry text labels", () => {
    render(<><SourceBadge source="SIMULATED" /><SourceBadge source="LOCAL_LAB" /><SourceBadge source="IMPORTED_SAMPLE" /></>);
    expect(screen.getByText("SIMULATED")).toBeInTheDocument();
    expect(screen.getByText("LOCAL LAB")).toBeInTheDocument();
    expect(screen.getByText("IMPORTED SAMPLE")).toBeInTheDocument();
  });
  it("result badges show the result word, and missing results show Pending (never PASS)", () => {
    render(<><ResultBadge result="MANUAL_REVIEW" /><ResultBadge result={null} /></>);
    expect(screen.getByText("MANUAL REVIEW")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.queryByText("PASS")).not.toBeInTheDocument();
  });
  it("health dot exposes a text label even when visually hidden", () => {
    render(<HealthDot health="critical" withLabel={false} />);
    expect(screen.getByText("Critical")).toHaveClass("sr-only");
  });
});

describe("formatting", () => {
  it("missing durations render as Unavailable, not zero", () => {
    expect(fmtDuration(null)).toBe("Unavailable");
    expect(fmtDuration(3)).toBe("3.0 s");
    expect(fmtDuration(95)).toBe("1m 35s");
  });
});

describe("Markdown renderer", () => {
  it("does not render raw HTML from summaries", () => {
    const { container } = render(<Markdown text={'# Title\n- item <img src=x onerror="alert(1)">\n**bold**'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
  });
});
