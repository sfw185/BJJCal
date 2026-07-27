# Cloudflare setup: country auto-detect + static asset caching

**Status: live.** `bjjcal.app` is proxied through Cloudflare (SSL/TLS mode
set to Full, per the redirect-loop warning below), and `country-worker.js`
is deployed and routed at `bjjcal.app/*`. Verified against production: the
Worker injects `window.__CF_COUNTRY__` into the homepage, a real visitor
request auto-selected the correct country in the dropdown, and
`calendars/*.ics` / `metadata.json` pass through byte-identical (confirmed
via two consecutive fetches diffing clean).

## How it's deployed

`wrangler.toml` in this directory holds the account ID and route. To
redeploy after editing `country-worker.js`:

```
cd cloudflare
npx wrangler deploy
```

This requires an authenticated `wrangler` session (`npx wrangler login`,
or a `CLOUDFLARE_API_TOKEN` env var scoped to Workers + zone for
`bjjcal.app`). `wrangler deploy --dry-run` bundles the script without
publishing, useful for catching syntax errors before touching production.

## Re-verifying after a change

```
curl -s https://bjjcal.app/ | grep -oE '<script>window\.__CF_COUNTRY__=[^<]*</script>'
curl -sI https://bjjcal.app/calendars/australia.ics | grep -iE 'content-type|cf-ray'
```

The first should show an injected script tag with a 2-letter ISO code (or
whatever Cloudflare resolves your request's country to); the second
confirms the Worker is still leaving calendar files untouched - it's
scoped to only rewrite `/` and `/index.html`, but this is what actually
proves that scoping holds against live traffic.

If the country matches one in `metadata.json`, the site's dropdown
pre-selects it automatically; otherwise it just falls back to "Select a
country...".

### The manual dashboard steps, for reference

These are already done for the current setup, kept here in case the zone
or Worker ever needs to be rebuilt from scratch in the dashboard instead
of via `wrangler`.

**1. Proxy the domain (orange-cloud it).** DNS tab → find the `bjjcal.app`
(and `www`, if used) records → click the grey cloud icon to turn it
orange (Proxied). **Do this only after** setting SSL/TLS mode to "Full" or
"Full (strict)" (SSL/TLS tab → Overview) - GitHub Pages already serves
valid HTTPS and force-redirects HTTP → HTTPS, so leaving the mode on
"Flexible" makes Cloudflare talk HTTP to GitHub's origin, which redirects
back to HTTPS, producing an infinite redirect loop that takes the site
down. This is the single most common way this kind of setup breaks.

**2. Create the Worker.** Workers & Pages → Create → Create Worker →
replace the default script with the contents of `country-worker.js` →
Deploy.

**3. Route it at the domain.** On the Worker's Triggers tab (or Websites →
bjjcal.app → Workers Routes), add a route: `bjjcal.app/*` (and
`www.bjjcal.app/*` too if that subdomain is live).

---

## Caching static icons at Cloudflare's edge

`static/icons/chevron-down.svg` (the select-dropdown arrow) is a small,
effectively-immutable file, but GitHub Pages sends the same
`Cache-Control: max-age=600` (10 minutes) on it as it does on `index.html`
and the daily-regenerated `.ics` calendars - there's no way to configure
GitHub Pages to treat it differently, since it's static hosting with no
per-path config.

Once the domain is proxied (step 1 above), a **Cache Rule** lets Cloudflare
override that at the edge for just this path, with nothing beyond what's
already been provisioned - no Worker, no KV, no build step:

**Rules → Overview → Create rule → Cache Rule**

- Rule name: `Cache static icons`
- When incoming requests match: `starts_with(http.request.uri.path, "/icons/")`
- Then:
  - Eligible for cache: **Eligible**
  - Edge Cache TTL: **1 month** (or longer - it only matters until the file
    changes)
  - Browser Cache TTL: **1 month**

This means the first visitor after the rule goes live fetches the icon
once; every visitor after that, and every repeat visit, gets it from
Cloudflare's edge or straight from the browser's own disk cache, without a
round trip to GitHub at all.

**Trade-off:** because there's no content hash in the filename (no build
step generates one), if `chevron-down.svg` is ever edited, browsers and
Cloudflare's edge will keep serving the old bytes for up to a month unless
you either purge the cache for that path (Caching → Configuration → Purge
Cache → Custom Purge → enter the URL) or rename the file so its URL
changes.
