// Split the heavy map libraries into their own chunks so the app code can change without
// re-downloading them (they are cached separately).
export default {
  base: './',
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('maplibre-gl')) return 'maplibre';
          if (id.includes('@deck.gl') || id.includes('@luma.gl') || id.includes('@math.gl') || id.includes('@loaders.gl')) return 'deck';
          return undefined;
        },
      },
    },
  },
};
