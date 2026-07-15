const navButton = document.querySelector('.nav-toggle');
const nav = document.querySelector('.site-nav');
const root = document.documentElement;

root.classList.add('motion-ready');

if (navButton && nav) {
  navButton.addEventListener('click', () => {
    const open = navButton.getAttribute('aria-expanded') === 'true';
    navButton.setAttribute('aria-expanded', String(!open));
    nav.classList.toggle('open', !open);
  });
}

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const header = document.querySelector('.site-header');
const progressBar = document.createElement('span');

progressBar.className = 'scroll-progress';
document.body.appendChild(progressBar);

if (header) {
  const updateHeader = () => {
    header.classList.toggle('is-scrolled', window.scrollY > 12);
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const progress = scrollable > 0 ? window.scrollY / scrollable : 0;
    progressBar.style.transform = `scaleX(${Math.max(0, Math.min(1, progress))})`;
  };
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });
}

const categoryRail = document.querySelector('.news-category-scroll');
if (categoryRail) {
  let isDown = false;
  let startX = 0;
  let scrollLeft = 0;

  categoryRail.addEventListener('pointerdown', (event) => {
    isDown = true;
    startX = event.pageX - categoryRail.offsetLeft;
    scrollLeft = categoryRail.scrollLeft;
    categoryRail.classList.add('is-dragging');
    categoryRail.setPointerCapture(event.pointerId);
  });

  categoryRail.addEventListener('pointermove', (event) => {
    if (!isDown) return;
    const x = event.pageX - categoryRail.offsetLeft;
    categoryRail.scrollLeft = scrollLeft - (x - startX);
  });

  ['pointerup', 'pointercancel', 'pointerleave'].forEach((eventName) => {
    categoryRail.addEventListener(eventName, () => {
      isDown = false;
      categoryRail.classList.remove('is-dragging');
    });
  });
}

if (!prefersReducedMotion) {
  const revealTargets = document.querySelectorAll([
    '.home-hero-copy > *',
    '.hero-signal-panel',
    '.hero-proof-rail div',
    '.editorial-card',
    '.market-map-panel',
    '.market-orbit-panel',
    '.market-region-panel',
    '.video-studio-card',
    '.visual-story-image',
    '.visual-story-panel',
    '.visual-story-points div',
    '.live-intel-copy > *',
    '.live-player',
    '.live-channel-card',
    '.live-signal-card',
    '.brand-strip',
    '.section-heading',
    '.newsroom-stat-panel',
    '.news-category-scroll a',
    '.news-featured-card',
    '.news-list-header',
    '.news-card',
    '.latest-news-strip article',
    '.service-page-hero .eyebrow',
    '.service-page-hero h1',
    '.service-page-hero p',
    '.service-page-media',
    '.service-proof-grid div',
    '.service-capability-grid article',
    '.service-flow-list div',
    '.case-hero-grid > *',
    '.case-score-grid div',
    '.case-dashboard-grid > *',
    '.case-study-card',
    '.case-method-steps div',
    '.services-hero-grid > *',
    '.services-score-grid div',
    '.services-showcase-card',
    '.services-analytics-grid > *',
    '.services-timeline div',
    '.services-final-inner',
    '.refined-service-card',
    '.refined-case-card',
    '.refined-insight-card',
    '.about-proof',
    '.home-about-media',
    '.home-final-cta',
    '.article-cover',
    '.article-visual-inline',
    '.article-side-visual',
    '.article-contact-card',
    '.article-trust-panel',
    '.glossary-hero-grid > *',
    '.glossary-radar',
    '.glossary-term-grid a',
    '.glossary-method-grid > *',
    '.glossary-term-hero-grid > *',
    '.glossary-signal-stack div',
    '.glossary-decision-grid > *',
    '.glossary-faq-grid > *'
  ].join(','));

  revealTargets.forEach((element, index) => {
    element.classList.add('reveal');
    element.style.setProperty('--reveal-delay', `${Math.min(index % 6, 5) * 70}ms`);
  });

  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    });
  }, { threshold: 0.14, rootMargin: '0px 0px -6% 0px' });

  revealTargets.forEach((element) => revealObserver.observe(element));

  const hero = document.querySelector('.home-hero');
  const heroMedia = document.querySelectorAll('.home-hero-network');
  let pointerFrame = 0;

  if (hero && heroMedia.length) {
    hero.addEventListener('pointermove', (event) => {
      if (pointerFrame) return;
      pointerFrame = window.requestAnimationFrame(() => {
        const bounds = hero.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width - 0.5;
        const y = (event.clientY - bounds.top) / bounds.height - 0.5;

        hero.style.setProperty('--hero-line-x', `${x * 34}`);
        heroMedia.forEach((image, index) => {
          const depth = index % 2 === 0 ? 10 : 6;
          image.style.transform = `translate3d(${x * depth}px, ${y * depth}px, 0) scale(1.055)`;
        });

        pointerFrame = 0;
      });
    });

    hero.addEventListener('pointerleave', () => {
      hero.style.removeProperty('--hero-line-x');
      heroMedia.forEach((image) => {
        image.style.transform = '';
      });
    });
}

const heroCommand = document.querySelector('[data-hero-command]');
if (heroCommand && !prefersReducedMotion) {
  let commandStart = performance.now();
  const animateCommand = (time) => {
    const phase = (time - commandStart) / 1000;
    heroCommand.style.setProperty('--command-x', `${68 + Math.sin(phase * .55) * 10}%`);
    heroCommand.style.setProperty('--command-y', `${34 + Math.cos(phase * .42) * 9}%`);
    heroCommand.style.setProperty('--command-drift', `${Math.sin(phase * .28) * 12}`);
    window.requestAnimationFrame(animateCommand);
  };
  window.requestAnimationFrame(animateCommand);
}

const metricValues = document.querySelectorAll('.hero-panel-metrics strong, .editorial-card-metrics strong, .refined-case-card dt, [data-count]');
  const numberObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting || entry.target.dataset.counted) return;

      const element = entry.target;
      const text = element.textContent.trim();
      const match = text.match(/^([+]?)(\d+(?:\.\d+)?)(.*)$/);
      if (!match) return;

      element.dataset.counted = 'true';
      const prefix = match[1];
      const target = Number(match[2]);
      const suffix = match[3];
      const decimals = match[2].includes('.') ? match[2].split('.')[1].length : 0;
      const start = performance.now();
      const duration = 900;

      const tick = (time) => {
        const progress = Math.min((time - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        element.textContent = `${prefix}${(target * eased).toFixed(decimals)}${suffix}`;
        if (progress < 1) window.requestAnimationFrame(tick);
      };

      window.requestAnimationFrame(tick);
      numberObserver.unobserve(element);
    });
  }, { threshold: 0.55 });

  metricValues.forEach((element) => numberObserver.observe(element));

  const interactiveCards = document.querySelectorAll('.hero-signal-panel, .news-card, .latest-news-strip article, .service-capability-grid article, .case-study-card, .services-showcase-card, .video-studio-card, .visual-story-image, .visual-story-panel, .live-channel-card, .live-signal-card, [data-chart-card], .refined-insight-card, .refined-case-card, .refined-service-card, .article-side-visual, .article-contact-card, .article-trust-panel, .glossary-term-grid a, .glossary-method-list div, .glossary-signal-stack div');
  interactiveCards.forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 100;
      const y = ((event.clientY - rect.top) / rect.height) * 100;
      const rotateX = (50 - y) / 18;
      const rotateY = (x - 50) / 18;
      card.style.setProperty('--shine-x', `${x}%`);
      card.style.setProperty('--shine-y', `${y}%`);
      card.style.transform = `translateY(-6px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    card.addEventListener('pointerleave', () => {
      card.style.removeProperty('--shine-x');
      card.style.removeProperty('--shine-y');
      card.style.transform = '';
    });
  });

  const magneticTargets = document.querySelectorAll('.button, .nav-cta');
  magneticTargets.forEach((target) => {
    target.addEventListener('pointermove', (event) => {
      const rect = target.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      target.style.transform = `translate(${x * 0.08}px, ${y * 0.16}px)`;
    });

    target.addEventListener('pointerleave', () => {
      target.style.transform = '';
    });
  });

  const articleHeadings = document.querySelectorAll('.article-content h2, .article-content h3');
  const relatedBox = document.querySelector('.article-aside');
  if (articleHeadings.length && relatedBox) {
    const headingObserver = new IntersectionObserver((entries) => {
      const active = entries.find((entry) => entry.isIntersecting);
      if (active) {
        relatedBox.dataset.reading = active.target.textContent.trim().slice(0, 64);
      }
    }, { threshold: 0.35, rootMargin: '-20% 0px -60% 0px' });
    articleHeadings.forEach((heading) => headingObserver.observe(heading));
  }

  const barCharts = document.querySelectorAll('[data-bar-chart]');
  const barObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-active');
      barObserver.unobserve(entry.target);
    });
  }, { threshold: 0.35 });
  barCharts.forEach((chart) => barObserver.observe(chart));
}

const marketImpact = document.querySelector('[data-market-impact]');
if (marketImpact) {
  const dataUrl = marketImpact.dataset.marketDataUrl || '/public/data/tiktok-market-impact.json';
  const bars = marketImpact.querySelector('[data-market-bars]');
  const orbit = marketImpact.querySelector('[data-market-orbit]');
  const regions = marketImpact.querySelector('[data-market-regions]');
  const total = marketImpact.querySelector('[data-market-total]');
  const updated = marketImpact.querySelector('[data-market-updated]');
  const source = marketImpact.querySelector('[data-market-source]');
  const leader = marketImpact.querySelector('[data-market-leader]');
  const commerce = marketImpact.querySelector('[data-market-commerce]');
  const count = marketImpact.querySelector('[data-market-count]');
  const filters = marketImpact.querySelectorAll('[data-market-filter]');
  let marketData = [];
  let activeFilter = 'all';

  const regionGroups = {
    Americas: ['North America', 'Latin America'],
    APAC: ['Southeast Asia', 'South Asia', 'East Asia'],
    EMEA: ['Europe', 'Middle East & Africa'],
  };

  const formatMillions = (value) => `${Number(value).toLocaleString('en-US', { maximumFractionDigits: 1 })}M`;
  const sum = (items) => items.reduce((acc, item) => acc + Number(item.users || 0), 0);
  const getFiltered = () => {
    if (activeFilter === 'all') return marketData;
    const allowed = regionGroups[activeFilter] || [activeFilter];
    return marketData.filter((market) => allowed.includes(market.region));
  };

  const renderMarketImpact = () => {
    if (!marketData.length || !bars || !orbit || !regions) return;

    const filtered = getFiltered();
    const visible = filtered.slice(0, activeFilter === 'all' ? 10 : 8);
    const maxUsers = Math.max(...visible.map((market) => Number(market.users || 0)), 1);
    const totalUsers = sum(activeFilter === 'all' ? marketData.slice(0, 10) : filtered);
    const bestCommerce = [...filtered].sort((a, b) => Number(b.commerce || 0) - Number(a.commerce || 0))[0] || marketData[0];

    if (total) total.textContent = `${formatMillions(totalUsers)} tracked reach`;
    if (leader) leader.textContent = `${visible[0]?.code || '--'} ${visible[0]?.country || 'Market'} leads`;
    if (commerce) commerce.textContent = `${bestCommerce.country}: ${bestCommerce.commerce}/100 commerce readiness`;
    if (count) count.textContent = `${filtered.length} markets`;

    bars.innerHTML = visible.map((market, index) => {
      const width = Math.max(10, (Number(market.users || 0) / maxUsers) * 100);
      return `
        <button type="button" class="market-bar" style="--bar-value:${width}; --bar-delay:${index * 54}ms" data-market-country="${market.country}">
          <span><em>${market.code || ''}</em>${market.country}</span>
          <i class="market-bar-track"><b></b></i>
          <strong>${formatMillions(market.users)}</strong>
          <small>${market.priority || 'Market signal'}</small>
        </button>
      `;
    }).join('');

    const orbitMarkets = visible.slice(0, 7);
    orbit.querySelectorAll('.market-node').forEach((node) => node.remove());
    orbitMarkets.forEach((market, index) => {
      const node = document.createElement('button');
      const angle = -80 + (index * (300 / Math.max(orbitMarkets.length - 1, 1)));
      const size = 20 + Math.min(34, Number(market.users || 0) / maxUsers * 34);
      node.type = 'button';
      node.className = 'market-node';
      node.style.setProperty('--node-angle', `${angle}deg`);
      node.style.setProperty('--node-radius', `${66 + (index % 2) * 12}px`);
      node.style.setProperty('--node-size', `${size}px`);
      node.setAttribute('aria-label', `${market.country}: ${formatMillions(market.users)} TikTok audience estimate`);
      node.innerHTML = `<span>${market.code || market.country.slice(0, 2).toUpperCase()}</span>`;
      node.addEventListener('click', () => {
        activeFilter = Object.keys(regionGroups).find((key) => regionGroups[key].includes(market.region)) || 'all';
        filters.forEach((filter) => filter.classList.toggle('is-active', filter.dataset.marketFilter === activeFilter));
        renderMarketImpact();
      });
      orbit.appendChild(node);
    });

    const regionTotals = marketData.reduce((acc, market) => {
      acc[market.region] = (acc[market.region] || 0) + Number(market.users || 0);
      return acc;
    }, {});
    const regionRows = Object.entries(regionTotals).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const maxRegion = Math.max(...regionRows.map(([, value]) => value), 1);
    regions.innerHTML = regionRows.map(([name, value], index) => `
      <div class="market-region-row" style="--region-value:${(value / maxRegion) * 100}; --bar-delay:${index * 70}ms">
        <span>${name}</span>
        <i><b></b></i>
        <strong>${formatMillions(value)}</strong>
      </div>
    `).join('');
  };

  filters.forEach((filter) => {
    filter.addEventListener('click', () => {
      activeFilter = filter.dataset.marketFilter || 'all';
      filters.forEach((item) => item.classList.toggle('is-active', item === filter));
      renderMarketImpact();
    });
  });

  fetch(dataUrl, { cache: 'force-cache' })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('market data unavailable')))
    .then((payload) => {
      marketData = Array.isArray(payload.markets) ? payload.markets.sort((a, b) => Number(b.users || 0) - Number(a.users || 0)) : [];
      if (updated) updated.textContent = payload.updated ? `Updated ${payload.updated}` : 'Live market data';
      if (source && payload.source) {
        source.textContent = `Source: ${payload.source.name}. ${payload.source.note || 'Directional market signal.'}`;
      }
      renderMarketImpact();
    })
    .catch(() => {
      if (bars) bars.innerHTML = '<p class="market-error">Market data is syncing. Please check back shortly.</p>';
    });
}

const liveMonitor = document.querySelector('[data-live-monitor]');
if (liveMonitor) {
  const video = liveMonitor.querySelector('[data-live-video]');
  const title = liveMonitor.querySelector('[data-live-title]');
  const description = liveMonitor.querySelector('[data-live-description]');
  const feeds = liveMonitor.querySelectorAll('[data-live-feed]');
  const frame = liveMonitor.querySelector('[data-live-frame]');
  const startButton = liveMonitor.querySelector('[data-live-video-start]');

  const loadLiveVideo = (videoSrc, shouldPlay = false) => {
    if (!videoSrc || !video) return;

    const source = video.querySelector('source') || document.createElement('source');
    const shouldReload = source.src !== videoSrc;
    source.src = videoSrc;
    source.type = 'video/mp4';
    if (!source.parentNode) video.appendChild(source);
    if (shouldReload || !video.currentSrc) video.load();
    if (frame) frame.classList.add('is-loaded');
    if (shouldPlay) video.play().catch(() => {});
  };

  if (startButton && video) {
    startButton.addEventListener('click', () => {
      loadLiveVideo(video.dataset.initialVideoSrc, true);
    });
  }

  feeds.forEach((feed) => {
    feed.addEventListener('click', () => {
      const videoSrc = feed.dataset.videoSrc;
      if (!videoSrc || !video) return;

      feeds.forEach((item) => {
        const active = item === feed;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-selected', String(active));
      });

      video.setAttribute('aria-label', feed.dataset.title || 'TikTok operating video');
      loadLiveVideo(videoSrc, true);
      if (title) title.textContent = feed.dataset.title || '';
      if (description) description.textContent = feed.dataset.description || '';
    });
  });
}

const videoCards = document.querySelectorAll('[data-video-card]');
videoCards.forEach((card, index) => {
  const video = card.querySelector('video');
  const toggle = card.querySelector('[data-video-toggle]');
  if (!video || !toggle) return;

  const syncState = () => {
    const playing = !video.paused;
    card.classList.toggle('is-playing', playing);
    toggle.textContent = playing ? 'Pause' : 'Play';
    toggle.setAttribute('aria-pressed', String(playing));
  };

  const playVideo = () => {
    video.play().then(syncState).catch(syncState);
  };

  toggle.addEventListener('click', () => {
    if (video.paused) {
      playVideo();
    } else {
      video.pause();
      syncState();
    }
  });

  card.addEventListener('pointerenter', () => {
    if (!prefersReducedMotion) playVideo();
  });

  video.addEventListener('play', syncState);
  video.addEventListener('pause', syncState);

  if (index === 0 && !prefersReducedMotion && 'IntersectionObserver' in window) {
    const videoStartObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        playVideo();
        videoStartObserver.disconnect();
      });
    }, { threshold: 0.35 });
    videoStartObserver.observe(card);
  }
  syncState();
});

const contactForm = document.querySelector('[data-contact-form]');
if (contactForm) {
  const screenField = contactForm.querySelector('[data-device-screen]');
  const timezoneField = contactForm.querySelector('[data-device-timezone]');
  const platformField = contactForm.querySelector('[data-device-platform]');
  const referrerField = contactForm.querySelector('[data-page-referrer]');
  if (screenField) screenField.value = `${window.screen.width}x${window.screen.height}@${window.devicePixelRatio || 1}`;
  if (timezoneField) timezoneField.value = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  if (platformField) platformField.value = navigator.userAgentData?.platform || navigator.platform || '';
  if (referrerField) referrerField.value = document.referrer || location.href;
}
