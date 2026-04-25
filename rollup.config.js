import deckyPlugin from "@decky/rollup";

export default deckyPlugin({
  input: "src/index.tsx",
  output: {
    dir: "dist",
    format: "esm",
    sourcemap: true,
  },
});
