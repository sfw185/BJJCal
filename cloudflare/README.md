# Cloudflare setup: country auto-detect + static asset caching

`bjjcal.app` currently uses Cloudflare only for DNS (grey-clouded / "DNS
only"); traffic goes straight to GitHub Pages, which has no server-side code
and no access to the visitor's IP-derived country. `country-worker.js`
fixes that by running at Cloudflare's edge, in front of GitHub Pages, and
injecting the detected country into the page before it reaches the browser.

This setup happens in the Cloudflare dashboard - there's no repo-side
deploy step.

## 1. Proxy the domain (orange-cloud it)

**DNS tab → find the `bjjcal.app` (and `www`, if used) records → click the
grey cloud icon to turn it orange (Proxied).**

**Before doing this, set SSL/TLS mode to "Full" or "Full (strict)"**
(SSL/TLS tab → Overview). GitHub Pages already serves valid HTTPS and
force-redirects HTTP → HTTPS. If the mode is left on "Flexible", Cloudflare
talks HTTP to GitHub's origin, GitHub redirects back to HTTPS, and the
result is an infinite redirect loop that takes the site down. This is the
single most common way this kind of setup breaks.

## 2. Create the Worker

Workers & Pages → Create → Create Worker → replace the default script with
the contents of `country-worker.js` → Deploy.

## 3. Route it at the domain

On the Worker's Triggers tab (or Websites → bjjcal.app → Workers Routes),
add a route:

```
bjjcal.app/*
```

(add `www.bjjcal.app/*` too if that subdomain is live).

## 4. Verify

Visit `https://bjjcal.app/`, open devtools console, and check:

```js
window.__CF_COUNTRY__
```

It should print a 2-letter ISO code (e.g. `"US"`). Also confirm a calendar
file still downloads correctly, e.g. `https://bjjcal.app/calendars/australia.ics`
- the Worker is scoped to only rewrite `/` and `/index.html`, but this
confirms that scoping actually holds against live traffic.

If the country matches one in `metadata.json`, the site's dropdown
pre-selects it automatically; otherwise it just falls back to "Select a
country...".

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
