/**
 * Injects the visitor's edge-detected country into the BJJ Calendar
 * homepage, so the country dropdown can auto-select without a client-side
 * geolocation API call.
 *
 * Deploy in the Cloudflare dashboard and route it at bjjcal.app/* (see
 * cloudflare/README.md for the full setup, including a required SSL mode
 * change). DNS for bjjcal.app must be proxied (orange-clouded) or the
 * request never reaches this Worker.
 */

const HOMEPAGE_PATHS = new Set(['/', '/index.html']);

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const response = await fetch(request);

    // Only touch the homepage document. Every other path - calendars/*.ics,
    // metadata.json, CNAME - passes through completely unmodified.
    if (request.method !== 'GET' || !HOMEPAGE_PATHS.has(url.pathname)) {
      return response;
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/html')) {
      return response;
    }

    // ISO 3166-1 alpha-2 (e.g. "US"), or "T1" for Tor, or "XX" if
    // undetermined. The front end only acts on it if it matches a known
    // country code, so unrecognized values are a silent no-op.
    const country = request.cf?.country || '';

    return new HTMLRewriter()
      .on('head', {
        element(element) {
          element.append(
            `<script>window.__CF_COUNTRY__=${JSON.stringify(country)};</script>`,
            { html: true }
          );
        },
      })
      .transform(response);
  },
};
