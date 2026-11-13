import QRCode from "qrcode";
import { useEffect, useState } from "react";

/** Printable label. The QR encodes the local route for the record, e.g. http://localhost:5173/assets/12 */
export function QrLabel({ title, subtitle, path }: { title: string; subtitle?: string; path: string }) {
  const [svg, setSvg] = useState("");
  const url = `${window.location.origin}${path}`;
  useEffect(() => {
    QRCode.toString(url, { type: "svg", margin: 0, errorCorrectionLevel: "M", color: { dark: "#101827", light: "#ffffff" } }).then(setSvg).catch(() => setSvg(""));
  }, [url]);
  return (
    <div className="inline-flex items-center gap-3 rounded-lg border border-ink/70 bg-white p-2.5 pr-4" style={{ breakInside: "avoid" }}>
      <div className="h-[64px] w-[64px] shrink-0" role="img" aria-label={`QR code linking to ${url}`} dangerouslySetInnerHTML={{ __html: svg }} />
      <div className="min-w-0">
        <div className="mono text-[15px] font-bold leading-tight text-ink">{title}</div>
        {subtitle && <div className="mono mt-0.5 text-[10.5px] text-ink-2">{subtitle}</div>}
        <div className="mono mt-1 max-w-[220px] truncate text-[9.5px] text-ink-3">{url}</div>
      </div>
    </div>
  );
}
