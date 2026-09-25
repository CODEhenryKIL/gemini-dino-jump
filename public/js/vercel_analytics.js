// Aggregated Preview pageviews; business events stay in the private DB.
// https://vercel.com/docs/analytics/redacting-sensitive-data
export function redactPageview(event, origin) {
  if (event?.type !== 'pageview') return null;
  try {
    const url = new URL(event.url, origin);
    if (url.origin !== origin) return null;
    const publicEntry = url.pathname === '/' || url.pathname === '/index.html'
      || /^\/invite\/[A-Za-z0-9_-]{12,64}$/.test(url.pathname);
    if (!publicEntry) return null;
    return { type: 'pageview', url: `${origin}/__preview__/home` };
  } catch (_) {
    return null;
  }
}

export function startVercelAnalytics(config) {
  if (config?.web_analytics_enabled !== true || config.environment !== 'preview'
      || window.location.protocol !== 'https:'
      || document.querySelector('script[data-dino-web-analytics]')) return;
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
  window.va('beforeSend', (event) => redactPageview(event, window.location.origin));
  const script = document.createElement('script');
  script.src = '/_vercel/insights/script.js';
  script.defer = true;
  script.dataset.dinoWebAnalytics = 'true';
  document.head.appendChild(script);
}
