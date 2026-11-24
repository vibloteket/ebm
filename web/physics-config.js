// Only the main machine imports this module; tools keep their fixed wheel.
export const PYMUNK_WHEELS = Object.freeze({
  "7.4.0": "./vendor/pymunk-7.4.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
  "7.3.1": "./vendor/pymunk-7.3.1-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
});

export function physicsConfig(search) {
  const params = new URLSearchParams(search);
  const version = params.get("pymunk") ?? "7.4.0";
  const solver = params.get("solver") ?? "baseline";
  if (!Object.hasOwn(PYMUNK_WHEELS, version)) {
    throw new Error(`Unsupported pymunk version: ${version}. Use 7.4.0 or 7.3.1.`);
  }
  if (!["baseline", "auto"].includes(solver)) {
    throw new Error(`Unsupported solver: ${solver}. Use baseline or auto.`);
  }
  return { version, wheel: PYMUNK_WHEELS[version], solver: version === "7.3.1" ? "baseline" : solver };
}

export function solverUrl(href, solver) {
  const url = new URL(href);
  url.searchParams.set("solver", solver);
  return url;
}
