// Inline SVG icon set (stroke-based, 24×24). No external deps.
const P = {
  logo: '<path d="M12 2.5 3.5 7.25v9.5L12 21.5l8.5-4.75v-9.5L12 2.5Z"/><path d="M3.5 7.25 12 12l8.5-4.75"/><path d="M12 12v9.5"/><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>',
  cloud: '<path d="M7 18.5h10.5a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.6 9.1 4.75 4.75 0 0 0 7 18.5Z"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5M2.5 9H6M2.5 15H6M18 9h3.5M18 15h3.5"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-9 9"/>',
  video: '<rect x="2.5" y="5" width="14" height="14" rx="3"/><path d="m16.5 10 5-3v10l-5-3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z"/>',
  cube: '<path d="M12 2.8 20 7.2v9.6l-8 4.4-8-4.4V7.2l8-4.4Z"/><path d="m4 7.2 8 4.6 8-4.6M12 11.8v9.4"/>',
  wand: '<path d="m15 4 1 2.2L18.2 7 16 8l-1 2.2L14 8l-2.2-1L14 6.2 15 4ZM19.5 13l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4Z"/><path d="m3 21 10-10"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
  folder: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2h7.5A2.5 2.5 0 0 1 21 9.5v7a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5v-9Z"/>',
  download: '<path d="M12 4v11M7 10.5l5 5 5-5M4.5 20h15"/>',
  upload: '<path d="M12 20V9M7 13.5l5-5 5 5M4.5 4h15"/>',
  trash: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/>',
  maximize: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  dice: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><circle cx="8.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="8.5" cy="15.5" r="1.2" fill="currentColor"/>',
  sparkles: '<path d="M10 3.5 11.6 8 16 9.6l-4.4 1.6L10 15.6 8.4 11.2 4 9.6 8.4 8 10 3.5ZM18 14l.9 2.1L21 17l-2.1.9L18 20l-.9-2.1L15 17l2.1-.9L18 14Z"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  chevronLeft: '<path d="m15 6-6 6 6 6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.6-4.5M4 4.5v3.5h3.5M4 13a8 8 0 0 0 14.6 4.5M20 19.5V16h-3.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  zap: '<path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12l1-8Z"/>',
  film: '<rect x="3" y="3.5" width="18" height="17" rx="3"/><path d="M7.5 3.5v17M16.5 3.5v17M3 8h4.5M3 12h4.5M3 16h4.5M16.5 8H21M16.5 12H21M16.5 16H21"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  arrowRight: '<path d="M4.5 12h15M13.5 6l6 6-6 6"/>',
  alert: '<path d="M12 3.5 2.5 20h19L12 3.5Z"/><path d="M12 10v4.5M12 17.2v.3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.2"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M12.5 15H17"/>',
  list: '<path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20"/><circle cx="4.5" cy="6.5" r="1" fill="currentColor"/><circle cx="4.5" cy="12" r="1" fill="currentColor"/><circle cx="4.5" cy="17.5" r="1" fill="currentColor"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V6A2.5 2.5 0 0 0 13 3.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
  play: '<path d="M7 4.8v14.4a1 1 0 0 0 1.5.86l11.6-7.2a1 1 0 0 0 0-1.72L8.5 3.94A1 1 0 0 0 7 4.8Z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
  power: '<path d="M12 3v8.5"/><path d="M6.8 6.5a8 8 0 1 0 10.4 0"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
  unlink: '<path d="M12 5 5.5 13.5h13L12 5Z"/><path d="M5.5 18.5h13"/>',
  eject: '<path d="M12 5 5.5 13.5h13L12 5Z"/><path d="M5.5 18.5h13"/>',
  unload: '<path d="M12 5 5.5 13.5h13L12 5Z"/><path d="M5.5 18.5h13"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  rocket: '<path d="M14 4.5c3-1.5 5.5-1 5.5-1s.5 2.5-1 5.5l-6 6-4.5-4.5 6-6Z"/><path d="m8 10.5-3.5.5L3 13.5l4 1M13.5 16l-.5 3.5-2.5 1.5-1-4M6.5 17.5 4 20"/><circle cx="15" cy="9" r="1.3"/>',
  gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="m12 17 4-5.5"/>',
  thermo: '<path d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0Z"/>',
  hdd: '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M5.5 13 8 4.5h8l2.5 8.5M7 16.5h.01M10 16.5h.01"/>',
  memory: '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 10.5v3M11 10.5v3M15 10.5v3M7 17v2.5M12 17v2.5M17 17v2.5"/>',
  hf: '<circle cx="12" cy="12" r="9"/><circle cx="9" cy="10.5" r="1" fill="currentColor"/><circle cx="15" cy="10.5" r="1" fill="currentColor"/><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0"/>',
  camera: '<path d="M4 8.5A2.5 2.5 0 0 1 6.5 6H8l1.5-2h5L16 6h1.5A2.5 2.5 0 0 1 20 8.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-8Z"/><circle cx="12" cy="12.5" r="3.5"/>',
  coin: '<ellipse cx="12" cy="7" rx="7.5" ry="3.5"/><path d="M4.5 7v5c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5V7M4.5 12v5c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5v-5"/>',
  bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.4 1.1 2.2h5c0-.8.4-1.6 1.1-2.2A6 6 0 0 0 12 3Z"/>',
  scissors: '<circle cx="6" cy="6.5" r="2.5"/><circle cx="6" cy="17.5" r="2.5"/><path d="M8 8.2 20 18M8 15.8 20 6"/>',
  speed: '<path d="M4 6.5 10 12l-6 5.5M12 6.5l6 5.5-6 5.5"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
  dot: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 8.5-8.5M16 7l2.5 2.5M14 9l2 2"/>',
  star: '<path d="m12 3.2 2.65 5.38 5.94.86-4.3 4.19 1.02 5.91L12 16.75l-5.31 2.79 1.02-5.91-4.3-4.19 5.94-.86L12 3.2Z"/>',
  starFill: '<path d="m12 3.2 2.65 5.38 5.94.86-4.3 4.19 1.02 5.91L12 16.75l-5.31 2.79 1.02-5.91-4.3-4.19 5.94-.86L12 3.2Z" fill="currentColor" stroke="currentColor"/>',
  compare: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 3v18"/><path d="m8.5 10-2 2 2 2M15.5 10l2 2-2 2"/>',
  cinema: '<rect x="2.5" y="4.5" width="19" height="13.5" rx="2.5"/><path d="M8 21h8M12 18v3"/><path d="M10 9.2v4.6l4-2.3-4-2.3Z" fill="currentColor" stroke="none"/>',
  sort: '<path d="M4 7h10M4 12h7M4 17h4M17 5v14M14 16l3 3 3-3"/>',
  pause: '<rect x="6.5" y="5" width="3.8" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.7" y="5" width="3.8" height="14" rx="1" fill="currentColor" stroke="none"/>',
  skipBack: '<path d="M18 5 9 12l9 7V5Z" fill="currentColor" stroke="none"/><path d="M6 5v14"/>',
  skipForward: '<path d="m6 5 9 7-9 7V5Z" fill="currentColor" stroke="none"/><path d="M18 5v14"/>',
};

export function icon(name, cls = '') {
  const body = P[name] || P.dot;
  return `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

/** Replace all <i data-icon="name"> placeholders inside root with inline SVG. */
export function hydrateIcons(root = document) {
  root.querySelectorAll('i[data-icon]').forEach((el) => {
    el.outerHTML = icon(el.dataset.icon, el.className || '');
  });
}

/* Camera trajectory diagrams (Lyra modes). 64×40 viewBox. */
const TRAJ = {
  flythrough:
    '<path class="tr-ghost" d="M6 30 C 20 30, 26 20, 32 20"/><path class="tr-path" d="M32 20 C 40 20, 46 12, 58 10"/><circle class="tr-cam" cx="32" cy="20" r="3"/><path class="tr-arrow" d="m54 7 4 3-4.5 2"/><path class="tr-arrow tr-dim" d="m10 27-4 3 4.5 2"/>',
  horizontal_zoom:
    '<path class="tr-grid" d="M4 34h56M14 34 28 14M50 34 36 14"/><path class="tr-path" d="M32 34V12"/><circle class="tr-cam" cx="32" cy="32" r="3"/><path class="tr-arrow" d="m28.5 15 3.5-4 3.5 4"/>',
  horizontal_zoom_bend:
    '<path class="tr-grid" d="M4 34h56"/><path class="tr-path" d="M14 12 C 30 12, 38 16, 44 30"/><circle class="tr-cam" cx="14" cy="12" r="3"/><path class="tr-arrow" d="m40 28 4 3 1-4.8"/>',
  horizontal_spiral:
    '<path class="tr-path" d="M8 20 C 14 8, 22 8, 24 20 S 34 32, 38 20 S 48 8, 52 18 L 58 18"/><circle class="tr-cam" cx="8" cy="20" r="3"/><path class="tr-arrow" d="m54.5 14.5 3.5 3.5-3.5 3.5"/>',
  orbit_horizontal:
    '<ellipse class="tr-path" cx="32" cy="22" rx="24" ry="10"/><circle class="tr-subject" cx="32" cy="22" r="4"/><circle class="tr-cam" cx="56" cy="22" r="3"/><path class="tr-arrow" d="m12 28.5-4-4 5.5-1.5"/>',
  orbit_vertical:
    '<ellipse class="tr-path" cx="32" cy="20" rx="10" ry="16"/><circle class="tr-subject" cx="32" cy="20" r="4"/><circle class="tr-cam" cx="32" cy="4" r="3"/><path class="tr-arrow" d="m38 33.5-4.5 2.5 1-5"/>',
  horizontal:
    '<path class="tr-grid" d="M4 34h56"/><path class="tr-path" d="M10 20h44"/><circle class="tr-cam" cx="10" cy="20" r="3"/><path class="tr-arrow" d="m50 16 4.5 4-4.5 4"/><path class="tr-grid" d="M22 26v-2M32 26v-2M42 26v-2"/>',
  horizontal_lift:
    '<path class="tr-grid" d="M4 36h56"/><path class="tr-path" d="M12 32 C 26 32, 36 12, 54 8"/><circle class="tr-cam" cx="12" cy="32" r="3"/><path class="tr-arrow" d="m50 5 4.5 3-4 3.5"/>',
  rotate_spot:
    '<path class="tr-path" d="M44 12 A 14 14 0 1 1 22 11"/><circle class="tr-cam" cx="32" cy="22" r="3.5"/><path class="tr-arrow" d="m40 9 4.5 3-4.5 3"/><path class="tr-grid" d="M32 22 46 16"/>',
  spiral:
    '<path class="tr-path" d="M32 20 c 0 -3, 5 -3, 5 0 s -3 7, -8 6 s -9 -6, -6 -11 s 12 -8, 17 -2 s 4 16, -6 18 s -20 -2, -20 -12"/><circle class="tr-cam" cx="32" cy="20" r="2.5"/>',
};
export function trajDiagram(id) {
  const body = TRAJ[id] || TRAJ.horizontal_zoom;
  return `<svg class="traj" viewBox="0 0 64 40" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}
