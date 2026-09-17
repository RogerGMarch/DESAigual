# Deploy DESAigual to Vercel

The site is a static React/Vite application. Python and DuckDB generate the
analysis locally; the published site reads the exported files in
`web/public/data/`. No API, running database, or environment variables are
required for the current website.

## First deployment

1. Sign in to Vercel and choose **Add New → Project**.
2. Import **RogerGMarch/DESAigual** from GitHub. Grant Vercel access to that repository if prompted.
3. Set **Root Directory** to `web`.
4. Use **Vite** as the framework preset. The checked-in `web/vercel.json`
   specifies these settings:

   | Setting | Value |
   | --- | --- |
   | Install command | `npm ci` |
   | Build command | `npx vite build` |
   | Output directory | `dist/client` |
   | Production branch | `main` |

5. Choose Node.js **22.x** in the project settings if a version must be selected.
6. Leave environment variables empty and click **Deploy**.
7. Open the generated URL. Check the introduction, scroll through the charts,
   and search for Zamora in the explorer to confirm building data loads.

The Vercel build intentionally skips the separate Sites/Cloudflare packaging
step in `npm run build`. Keep the existing Sites files intact; Vercel serves
only `dist/client`. Hash links such as `#explorar` need no SPA rewrite.

## Updating the website

Push changes to `main`; the connected Vercel project builds a new production
deployment. Other branches can receive preview deployments.

When analysis changes, regenerate exports from the repository root in your
local Python environment, then commit the generated files along with any code
changes:

```sh
python -m desfibrilator.story_export
cd web
npm ci
npm test
npx vite build
```

The exporter needs local source datasets; those are deliberately not stored in
GitHub. Vercel uses the committed exports and does not rerun the Python study.

## Data and repository contents

- `web/public/data/`: committed public JSON, GeoJSON and map images needed by the site.
- Raw downloads, DuckDB, local `.env` files and `node_modules`: excluded from Git.
- All files under `web/public/` are publicly downloadable when deployed.
- The current public assets total roughly 70 MB. Future data expansion may
  warrant separate object storage, but no additional storage service is needed now.

## Custom domain

After deployment, open **Project → Settings → Domains**, add your domain, and
apply the DNS records shown by Vercel at your domain provider.

## Troubleshooting

- **Blank maps or missing data:** confirm `web/public/data/` is committed and
  requests such as `/data/summary.json` return JSON on the deployed URL.
- **No output directory found:** confirm root `web` and output `dist/client`.
- **Changes not visible:** verify the deployed commit and reload the page.

References: [Vite deployment guide](https://vite.dev/guide/static-deploy#vercel)
and [Vercel deployment limits](https://vercel.com/docs/limits).
