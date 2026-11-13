// Verifies WCAG contrast of the design tokens (run: node scripts/contrast.mjs).
const L = (hex) => { const c = hex.match(/\w\w/g).map((h) => parseInt(h, 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [L(a), L(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const pairs = [
  ["Primary text on canvas", "#172033", "#F5F7FA"], ["Primary text on panel", "#172033", "#FFFFFF"],
  ["Secondary text on panel", "#5E6B7E", "#FFFFFF"], ["Secondary text on canvas", "#5E6B7E", "#F5F7FA"],
  ["Tertiary text on panel", "#6B7789", "#FFFFFF"],
  ["Accent text on panel", "#087F8C", "#FFFFFF"], ["Accent-700 on accent-50", "#066A75", "#E8F4F5"],
  ["White on accent button", "#FFFFFF", "#087F8C"], ["Warning on panel", "#A65D00", "#FFFFFF"], ["Warning on warn-50", "#A65D00", "#FBF2E6"],
  ["Critical on panel", "#C93644", "#FFFFFF"], ["Critical on crit-50", "#C93644", "#FDF1F2"], ["Success on panel", "#18794E", "#FFFFFF"],
  ["Success on ok-50", "#18794E", "#E8F4EE"], ["Sim badge", "#5B4BA8", "#F0EEFA"], ["Local-lab badge", "#0B6E4F", "#E6F3EE"], ["Imported badge", "#7A5A12", "#F7F1E3"],
  ["Nav text on nav", "#C9D3E3", "#101827"], ["Nav muted on nav", "#8E9BB3", "#101827"], ["Accent-300 on nav", "#5DB3BC", "#101827"],
];
let fail = 0;
for (const [name, fg, bg] of pairs) {
  const r = ratio(fg, bg);
  const ok = r >= 4.5;
  if (!ok) fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${r.toFixed(2).padStart(5)}:1  ${name} (${fg} on ${bg})`);
}
console.log(fail ? `${fail} pair(s) below 4.5:1` : "All pairs meet WCAG AA (4.5:1) for normal text.");
process.exit(fail ? 1 : 0);
