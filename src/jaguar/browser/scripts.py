"""
Injectable JavaScript snippets for JAGUAR.

These scripts are injected into pages via Playwright for:
- axe-core accessibility testing
- Technology detection via JS globals
- DOM analysis (element visibility, computed styles)
"""

# ---------------------------------------------------------------------------
# axe-core accessibility runner
# ---------------------------------------------------------------------------

AXE_CORE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"

AXE_RUN_SCRIPT = """
async () => {
    if (typeof axe === 'undefined') {
        return { error: 'axe-core not loaded' };
    }
    try {
        const results = await axe.run(document, {
            runOnly: {
                type: 'tag',
                values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']
            }
        });
        return {
            violations: results.violations.map(v => ({
                id: v.id,
                impact: v.impact,
                description: v.description,
                help: v.help,
                helpUrl: v.helpUrl,
                tags: v.tags,
                nodes: v.nodes.length
            })),
            passes: results.passes.length,
            incomplete: results.incomplete.length,
            inapplicable: results.inapplicable.length,
            violationCount: results.violations.reduce((sum, v) => sum + v.nodes.length, 0)
        };
    } catch (e) {
        return { error: e.message };
    }
}
"""

# ---------------------------------------------------------------------------
# Technology detection script
# ---------------------------------------------------------------------------

TECH_DETECT_SCRIPT = """
() => {
    const detected = {};

    // React
    const reactRoot = document.querySelector('[data-reactroot]') ||
                      document.querySelector('#__next') ||
                      document.querySelector('#root');
    if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || reactRoot) {
        detected.react = {
            found: true,
            version: window.React?.version || null
        };
    }

    // Next.js
    if (window.__NEXT_DATA__ || document.querySelector('#__next')) {
        detected.nextjs = {
            found: true,
            version: window.__NEXT_DATA__?.buildId ? 'detected' : null
        };
    }

    // Vue
    if (window.__VUE__ || document.querySelector('[data-v-]') ||
        document.querySelector('[data-vue-app]')) {
        detected.vue = {
            found: true,
            version: window.Vue?.version || null
        };
    }

    // Nuxt
    if (window.__NUXT__ || window.$nuxt) {
        detected.nuxt = {
            found: true,
            version: window.__NUXT__?.config?.public?.version || null
        };
    }

    // Angular
    if (window.ng || document.querySelector('[ng-version]') ||
        document.querySelector('[_ngcontent]') ||
        document.querySelector('app-root')) {
        const ngVersion = document.querySelector('[ng-version]');
        detected.angular = {
            found: true,
            version: ngVersion?.getAttribute('ng-version') || null
        };
    }

    // Svelte
    if (document.querySelector('[class*="svelte-"]')) {
        detected.svelte = { found: true, version: null };
    }

    // jQuery
    if (window.jQuery || window.$?.fn?.jquery) {
        detected.jquery = {
            found: true,
            version: window.jQuery?.fn?.jquery || window.$?.fn?.jquery || null
        };
    }

    // WordPress
    if (window.wp || document.querySelector('meta[name="generator"][content*="WordPress"]') ||
        document.querySelector('link[href*="wp-content"]')) {
        const gen = document.querySelector('meta[name="generator"][content*="WordPress"]');
        detected.wordpress = {
            found: true,
            version: gen?.content?.replace('WordPress ', '') || null
        };
    }

    // Shopify
    if (window.Shopify || document.querySelector('meta[name="shopify-digital-wallet"]') ||
        document.querySelector('link[href*="cdn.shopify.com"]')) {
        detected.shopify = { found: true, version: null };
    }

    // Cloudflare
    if (document.querySelector('script[src*="cloudflare"]') ||
        document.cookie.includes('__cf')) {
        detected.cloudflare = { found: true, version: null };
    }

    // Google Analytics
    if (window.ga || window.gtag || window.dataLayer ||
        document.querySelector('script[src*="google-analytics"]') ||
        document.querySelector('script[src*="googletagmanager"]')) {
        detected.google_analytics = { found: true, version: null };
    }

    // Tailwind CSS (heuristic: look for Tailwind utility classes)
    const allElements = document.querySelectorAll('*');
    let tailwindScore = 0;
    const tailwindPatterns = /\\b(flex|grid|p-\\d|m-\\d|text-\\w|bg-\\w|rounded|shadow|hover:|focus:)/;
    for (let i = 0; i < Math.min(allElements.length, 100); i++) {
        if (tailwindPatterns.test(allElements[i].className)) {
            tailwindScore++;
        }
    }
    if (tailwindScore > 10) {
        detected.tailwind = { found: true, version: null, confidence: Math.min(tailwindScore / 30, 1) };
    }

    // Bootstrap
    if (document.querySelector('link[href*="bootstrap"]') ||
        document.querySelector('script[src*="bootstrap"]') ||
        document.querySelector('.container .row .col')) {
        detected.bootstrap = { found: true, version: null };
    }

    return detected;
}
"""

# ---------------------------------------------------------------------------
# DOM analysis helpers
# ---------------------------------------------------------------------------

DOM_ANALYSIS_SCRIPT = """
() => {
    const result = {};

    // Navigation analysis
    const navElements = document.querySelectorAll('nav, [role="navigation"]');
    const links = document.querySelectorAll('a[href]');
    result.navigation = {
        navElementCount: navElements.length,
        totalLinks: links.length,
        hasMainNav: navElements.length > 0,
        hasMobileMenu: !!document.querySelector(
            '[class*="hamburger"], [class*="mobile-menu"], [class*="menu-toggle"], ' +
            'button[aria-label*="menu"], .navbar-toggler'
        )
    };

    // CTA analysis
    const buttons = document.querySelectorAll('button, [role="button"], a.btn, a.button, .cta');
    result.ctas = {
        count: buttons.length,
        aboveFold: 0
    };
    buttons.forEach(btn => {
        const rect = btn.getBoundingClientRect();
        if (rect.top < window.innerHeight) {
            result.ctas.aboveFold++;
        }
    });

    // Heading hierarchy
    const headings = [];
    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
        headings.push({
            level: parseInt(h.tagName[1]),
            text: h.textContent.trim().substring(0, 100)
        });
    });
    result.headings = headings;

    // Images
    const images = document.querySelectorAll('img');
    let missingAlt = 0;
    images.forEach(img => {
        if (!img.alt && !img.getAttribute('aria-label') && img.getAttribute('role') !== 'presentation') {
            missingAlt++;
        }
    });
    result.images = {
        total: images.length,
        missingAlt: missingAlt
    };

    // Viewport meta
    const viewportMeta = document.querySelector('meta[name="viewport"]');
    result.viewport = {
        hasTag: !!viewportMeta,
        content: viewportMeta?.content || null
    };

    // Forms
    const forms = document.querySelectorAll('form');
    result.forms = {
        count: forms.length,
        hasLabels: true
    };
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input:not([type="hidden"])');
        inputs.forEach(input => {
            const id = input.id;
            if (!id || !document.querySelector(`label[for="${id}"]`)) {
                if (!input.getAttribute('aria-label') && !input.getAttribute('placeholder')) {
                    result.forms.hasLabels = false;
                }
            }
        });
    });

    // Trust indicators
    result.trust = {
        hasPrivacyPolicy: !!document.querySelector('a[href*="privacy"]'),
        hasTerms: !!document.querySelector('a[href*="terms"]'),
        hasContact: !!document.querySelector('a[href*="contact"]'),
        hasSocialLinks: !!document.querySelector(
            'a[href*="twitter"], a[href*="facebook"], a[href*="linkedin"], ' +
            'a[href*="instagram"], a[href*="x.com"]'
        ),
        hasHttps: window.location.protocol === 'https:'
    };

    return result;
}
"""

# ---------------------------------------------------------------------------
# AI tool detection script (Requirement #4 expanded)
# ---------------------------------------------------------------------------

AI_TOOL_DETECT_SCRIPT = """
() => {
    const signals = {};
    const html = document.documentElement.outerHTML;
    const head = document.head.innerHTML;
    const body = document.body.innerHTML;

    // Lovable detection
    signals.lovable = {
        metaGenerator: !!document.querySelector('meta[content*="lovable" i]'),
        comments: html.includes('lovable') || html.includes('Lovable'),
        classPatterns: !!document.querySelector('[class*="lovable"]'),
    };

    // Bolt.new detection
    signals.bolt = {
        comments: html.includes('bolt.new') || html.includes('Bolt'),
        stackblitzEmbed: !!document.querySelector('[src*="stackblitz"]'),
        boltMeta: !!document.querySelector('meta[content*="bolt" i]'),
    };

    // v0.dev detection
    signals.v0 = {
        comments: html.includes('v0.dev') || html.includes('v0 by Vercel'),
        shadcnPatterns: !!(
            document.querySelector('[class*="rounded-md"]') &&
            document.querySelector('[class*="border"]') &&
            document.querySelector('[data-slot]')
        ),
    };

    // Replit detection
    signals.replit = {
        comments: html.includes('replit') || html.includes('Replit'),
        replitBadge: !!document.querySelector('a[href*="replit.com"]'),
        meta: !!document.querySelector('meta[content*="replit" i]'),
    };

    // Cursor / Claude Code / GPT patterns (code analysis)
    const scripts = document.querySelectorAll('script:not([src])');
    let inlineJS = '';
    scripts.forEach(s => inlineJS += s.textContent);

    signals.codePatterns = {
        excessiveComments: (html.match(/<!--/g) || []).length > 20,
        genericVarNames: /(?:const|let|var)\\s+(?:data|result|response|item|element|container|wrapper)\\s*=/g.test(inlineJS),
        todoComments: (html.match(/TODO:|FIXME:|HACK:/gi) || []).length,
        boilerplateStructure: !!(
            document.querySelector('.hero-section, .hero') &&
            document.querySelector('.features, .feature-section') &&
            document.querySelector('.cta, .call-to-action') &&
            document.querySelector('footer')
        ),
    };

    // shadcn/ui template detection
    signals.shadcnUI = {
        dataSlots: document.querySelectorAll('[data-slot]').length,
        radixPrimitives: !!document.querySelector('[data-radix-collection-item]'),
        lucideIcons: document.querySelectorAll('[class*="lucide-"]').length > 0,
        cnUtility: /\\bcn\\(/.test(inlineJS),
    };

    return signals;
}
"""
