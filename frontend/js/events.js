export function emit(name, detail) {
  window.dispatchEvent(new CustomEvent(`tf:${name}`, { detail }));
}

export function on(name, handler) {
  const type = `tf:${name}`;
  window.addEventListener(type, handler);
  return () => window.removeEventListener(type, handler);
}
