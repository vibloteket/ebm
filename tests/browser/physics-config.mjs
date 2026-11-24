import assert from "node:assert/strict";
import { physicsConfig, solverUrl } from "../../web/physics-config.js";
assert.equal(physicsConfig("").version, "7.4.0");
assert.equal(physicsConfig("").solver, "baseline");
assert.match(physicsConfig("").wheel, /7\.4\.0-cp314/);
assert.equal(physicsConfig("?solver=auto").solver, "auto");
assert.equal(physicsConfig("?pymunk=7.3.1&solver=auto").solver, "baseline");
assert.match(physicsConfig("?pymunk=7.3.1").wheel, /7\.3\.1-cp314/);
for (const search of ["?pymunk=unknown", "?pymunk=__proto__", "?pymunk=", "?solver=unknown"]) {
  assert.throws(() => physicsConfig(search), /Unsupported/);
}
assert.equal(solverUrl("https://example.org/?pymunk=7.4.0&x=1#stats", "auto").href,
  "https://example.org/?pymunk=7.4.0&x=1&solver=auto#stats");
console.log("PASS physics URL configuration");
