/* eslint-disable @next/next/no-img-element */
import type { Metadata } from "next";
import Link from "next/link";

const LOGO_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuDgfvXg-uJnsV5CdyC--V7hto3-bolr-GFugiigXaac5EQweYK7uqhVM32QPQ99IG-Lmk-p1KCONPJWD2SiCM9KRGqRepEhYth0P7SC12eZanns6eWpoecjyB49GDX7j_ZNdsvisZDxSDof0OcRgmiPEBW3D3dFg_TgijtsxMVfNOY45Wfnl8fcjIm4K05hOBYTh8VXfcyAICiGl1ctPD168mfF8nv44Rtd6YVuq9i7bN2XpQhmT9PDtq0zGfV4Nu2RdQ";

const EMBLEM_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuCNJae6uhyDDBwjBXXJTKVb2qcEU7n5sOyuU0YvlwTgnqiHpVI-Q7Rsv42G03lqbYLwHZGLrv9Mq7hau6IqDMurwB_pfNdr1keVAtibmr3gteWyiUnQHDS4OSssnUXTn7lKNww1kVWhy31j5abAllivgTTo7mgLOso2IrTZBSLGY2Kf5KeWfR0eP6m43quLcr3-vKb32Cvp_bvibt6pgAkxkCv11bFYMxVITFKHmSL2In6ldDEEkMq9kYa8jGG28_hJNg";

export const metadata: Metadata = {
  title: "Paari — The governance layer for agentic commerce",
  description:
    "Paari enables AI buying agents to safely transact with AI-ready merchants by governing identity, authorization, policies, payments, and fulfillment.",
};

export default function HomePage() {
  return (
    <div className="min-h-screen bg-surface text-on-surface font-body-md text-body-md antialiased">
      <header className="fixed top-0 left-0 right-0 z-50 bg-surface/80 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="h-16 max-w-max-width mx-auto px-gutter-desktop flex items-center justify-between">
          <div className="flex items-center gap-space-lg">
            <Link
              href="/"
              className="flex items-center gap-space-xs focus:outline-none"
              data-path="overview"
            >
              <img
                src={LOGO_URL}
                alt="Paari Logo"
                className="w-8 h-8 rounded-full object-cover"
              />
              <span className="font-headline-sm text-headline-sm tracking-tight text-on-surface">
                Paari
              </span>
            </Link>
          </div>
          <nav className="hidden md:flex items-center gap-space-lg">
            <Link
              href="/buyer"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Buyer AI
            </Link>
            <Link
              href="/merchant"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Merchant
            </Link>
            <Link
              href="/audit"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Audit
            </Link>
          </nav>
        </div>
      </header>

      <main className="w-full pt-16 bg-surface">
        <div className="flex flex-col w-full">
          {/* Architectural Hero & Statement Section */}
          <section className="relative w-full max-w-max-width mx-auto px-gutter-mobile md:px-gutter-desktop pb-space-4xl flex flex-col items-center text-center py-space-4xl">
            {/* Ambient Halo Glow Behind Brand Emblem */}
            <div className="absolute top-12 left-1/2 -translate-x-1/2 w-96 h-96 rounded-full bg-tertiary-fixed/15 blur-3xl -z-10 pointer-events-none"></div>

            {/* Dove of Peace & Sovereignty Emblem */}
            <div className="mb-space-xl relative group">
              <div className="w-32 h-32 sm:w-36 sm:h-36 rounded-2xl bg-surface-container-lowest p-2 shadow-[0_8px_30px_rgba(24,24,27,0.06)] flex items-center justify-center transition-transform duration-500 hover:scale-105 overflow-hidden relative">
                <img
                  src={EMBLEM_URL}
                  alt="Paari Logo"
                  className="w-full h-full object-cover rounded-2xl scale-150 transition-transform duration-500"
                  style={{ objectPosition: "center center", transform: "scale(1.5)" }}
                />
              </div>
              <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 px-space-xs py-space-3xs bg-surface-container-high rounded-full shadow-sm"></div>
            </div>

            {/* Editorial Header Title */}
            <div className="max-w-4xl flex flex-col items-center">
              <div className="inline-flex items-center gap-2 mb-space-sm px-space-md py-space-3xs rounded-full bg-surface-container-low text-secondary font-mono-label text-mono-label tracking-wider"></div>
              <h1 className="font-display-hero text-display-hero tracking-tight text-on-surface mb-space-lg">
                Paari
              </h1>

              {/* Mandatory Copy Block with Editorial Typographic Polish */}
              <div className="max-w-3xl space-y-space-md">
                <p className="font-headline-lg text-headline-lg italic font-normal text-on-surface leading-snug">
                  The governance layer for agentic commerce.
                </p>
                <p className="font-body-lg text-body-lg text-secondary leading-relaxed max-w-2xl mx-auto">
                  Paari enables AI buying agents to safely transact with
                  AI-ready merchants by governing identity, authorization,
                  policies, payments, and fulfillment.
                </p>
                <p className="font-headline-md text-headline-md italic font-medium text-on-surface pt-space-xs tracking-tight">
                  Agents negotiate. Paari governs. Payments execute.
                </p>
              </div>
            </div>

            {/* Action Hub: Dual Agentic Gateways */}
            <div className="mt-space-2xl w-full max-w-xl flex flex-col sm:flex-row items-stretch justify-center gap-space-md">
              {/* Buyer AI CTA */}
              <Link
                href="/buyer"
                className="group relative flex-1 flex items-center justify-between px-space-xl py-space-md rounded-full bg-primary text-on-primary shadow-[0_8px_24px_rgba(0,0,0,0.12)] hover:bg-primary-container transition-all duration-300"
              >
                <div className="flex items-center gap-space-sm text-left">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-white/10 text-white">
                    <span className="material-symbols-outlined text-body-md">
                      smart_toy
                    </span>
                  </span>
                  <div className="flex flex-col">
                    <span className="font-headline-sm text-headline-sm text-white">
                      Buyer AI
                    </span>
                    <span className="font-mono-label text-mono-label text-white/60">
                      Policy &amp; Budget Config
                    </span>
                  </div>
                </div>
                <span className="material-symbols-outlined text-body-lg group-hover:translate-x-1 transition-transform">
                  arrow_forward
                </span>
              </Link>

              {/* Merchant AI CTA */}
              <Link
                href="/merchant"
                className="group relative flex-1 flex items-center justify-between px-space-xl py-space-md rounded-full bg-surface-container-lowest text-on-surface shadow-[0_4px_20px_rgba(0,0,0,0.04)] hover:bg-surface-container-high transition-all duration-300"
              >
                <div className="flex items-center gap-space-sm text-left">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-surface-container text-on-surface">
                    <span className="material-symbols-outlined text-body-md">
                      storefront
                    </span>
                  </span>
                  <div className="flex flex-col">
                    <span className="font-headline-sm text-headline-sm text-on-surface">
                      Merchant AI
                    </span>
                    <span className="font-mono-label text-mono-label text-secondary">
                      Verified Catalog Node
                    </span>
                  </div>
                </div>
                <span className="material-symbols-outlined text-body-lg group-hover:translate-x-1 transition-transform">
                  arrow_outward
                </span>
              </Link>
            </div>

            {/* Assurance Micro-copy */}
            <div className="mt-space-lg flex flex-wrap items-center justify-center gap-x-space-md gap-y-space-xs font-mono-label text-mono-label text-secondary">
              <span className="hidden sm:inline opacity-30">•</span>
              <span className="hidden sm:inline opacity-30">•</span>
            </div>
          </section>
        </div>
      </main>

      <footer className="w-full bg-surface-container-low py-space-3xl">
        <div className="max-w-max-width mx-auto px-gutter-desktop">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-space-xl pb-space-2xl">
            <div className="flex flex-col gap-space-xs">
              <div className="flex items-center gap-space-xs">
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-surface-container-highest text-on-surface">
                  <span className="material-symbols-outlined text-body-md">
                    flutter
                  </span>
                </span>
                <span className="font-headline-sm text-headline-sm tracking-tight text-on-surface">
                  Paari
                </span>
              </div>
              <p className="text-on-surface-variant font-body-sm text-body-sm max-w-sm">
                Sovereign computational governance protocol. Anchoring
                verifiable autonomy with architectural calm.
              </p>
            </div>
          </div>
          <div className="pt-space-lg flex flex-col sm:flex-row items-center justify-between gap-space-md bg-surface-container/50 px-space-md py-space-sm rounded-DEFAULT">
            <div className="flex items-center gap-space-xs font-mono-label text-mono-label text-on-surface-variant">
              <span className="w-2 h-2 rounded-full bg-on-surface"></span>
              <span className="">ALL SYSTEMS VERIFIED &amp; OPERATIONAL</span>
            </div>
            <div className="text-on-surface-variant font-mono-label text-mono-label">
              © 2025 PAARI PROTOCOL FOUNDATION
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}