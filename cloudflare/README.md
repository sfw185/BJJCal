# Country auto-detect via Cloudflare Worker

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
