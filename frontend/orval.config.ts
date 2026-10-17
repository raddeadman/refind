import { defineConfig } from 'orval'

// Regenerate after any API change:  npm run api
export default defineConfig({
  refind: {
    input: './openapi.json',
    output: {
      mode: 'tags-split', // one file per FastAPI tag (categories, items, ...)
      target: './src/api/generated',
      schemas: './src/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: { path: './src/api/fetcher.ts', name: 'apiFetch' },
        // apiFetch throws ApiError on non-2xx, so responses are success-only.
        fetch: { forceSuccessResponse: true },
      },
    },
  },
})
