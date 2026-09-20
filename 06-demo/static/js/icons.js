// One drawn icon set: 24px grid, 1.75 stroke, round joins. No glyphs or emoji
// stand in for icons anywhere in the app.
const P = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  compose: '<path d="M12 20h8"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  send: '<path d="M12 19V5"/><path d="m5.5 11.5 6.5-6.5 6.5 6.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  raised: '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
  supports: '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.2 2.4 2.4 4.6-4.9"/>',
  flag: '<path d="M5.5 21V4"/><path d="M5.5 4.5h11l-2.5 4 2.5 4h-11"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 7.6v.01"/>',
  people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18.5 14.2a6.5 6.5 0 0 1 3 5.8"/>',
  compare: '<rect x="3.5" y="4.5" width="7" height="15" rx="1"/><rect x="13.5" y="4.5" width="7" height="15" rx="1"/>',
  alert: '<path d="M12 3.8 21 19.5H3Z"/><path d="M12 10v4.2"/><path d="M12 16.9v.01"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  back: '<path d="m15 6-6 6 6 6"/>',
  none: '<circle cx="12" cy="12" r="8"/><path d="M6.4 6.4l11.2 11.2"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0"/><path d="M12 18v3"/>',
  stop: '<rect x="7.5" y="7.5" width="9" height="9" rx="1"/>',
};

export function icon(name, label) {
  const a11y = label ? `role="img" aria-label="${label}"` : 'aria-hidden="true" focusable="false"';
  return `<svg class="i" viewBox="0 0 24 24" ${a11y}>${P[name]}</svg>`;
}
