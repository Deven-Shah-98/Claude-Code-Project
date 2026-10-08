// Single-chunk build (no code splitting) for hosts that only accept one inlined page, e.g. the artifact.
export default { base: './', build: { outDir: 'dist-single', chunkSizeWarningLimit: 4000, rollupOptions: { output: { inlineDynamicImports: true } } } };
