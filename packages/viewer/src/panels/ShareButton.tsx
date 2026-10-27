import { useEffect, useRef, useState } from "react";

export interface ShareButtonProps {
  /** the link to this view of the map */
  readonly url: string;
}

type Status = "idle" | "copied" | "manual";

const NOTICE_MS = 2000;

/** Phones and tablets get the system share sheet; desktops copy the link. */
function prefersShareSheet(): boolean {
  return "share" in navigator && "matchMedia" in window && window.matchMedia("(pointer: coarse)").matches;
}

function isCancel(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function ShareButton({ url }: ShareButtonProps) {
  const [status, setStatus] = useState<Status>("idle");
  const fieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (status === "manual") {
      fieldRef.current?.focus();
      return undefined;
    }
    if (status !== "copied") return undefined;
    const timer = setTimeout(() => {
      setStatus("idle");
    }, NOTICE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [status]);

  async function share(): Promise<void> {
    if (prefersShareSheet()) {
      try {
        await navigator.share({ url });
        return;
      } catch (error) {
        if (isCancel(error)) return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setStatus("copied");
    } catch {
      // No clipboard (an insecure page, or permission refused): let the reader copy it.
      setStatus("manual");
    }
  }

  return (
    <div className="qv-share">
      <button type="button" className="qv-button" onClick={() => void share()}>
        Share
      </button>
      {status === "manual" && (
        <input
          ref={fieldRef}
          className="qv-share__field"
          type="url"
          readOnly
          value={url}
          aria-label="Link to this view"
          onFocus={(event) => {
            event.currentTarget.select();
          }}
        />
      )}
      <span role="status" className="qv-share__status">
        {status === "copied" ? "Link copied" : ""}
      </span>
    </div>
  );
}
