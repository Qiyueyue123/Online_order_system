import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's automatic afterEach cleanup only registers itself
// when a global `afterEach` is present; this project doesn't enable Vitest's
// `globals` option, so we wire it up explicitly for every test file.
afterEach(() => {
  cleanup();
});
