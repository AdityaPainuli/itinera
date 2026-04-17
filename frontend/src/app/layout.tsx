import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Itinera — AI travel itineraries",
  description: "Generate concrete, researched travel itineraries for any destination.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-ink-200 bg-ink-50/80 backdrop-blur sticky top-0 z-10">
            <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
              <div className="flex items-baseline gap-3">
                <span className="font-serif text-2xl text-ink-900">Itinera</span>
                <span className="text-sm text-ink-500">trips, researched</span>
              </div>
              <a
                href="https://github.com"
                className="text-sm text-ink-500 hover:text-ink-800"
                target="_blank"
                rel="noreferrer"
              >
                github
              </a>
            </div>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="border-t border-ink-200 py-6 text-center text-xs text-ink-400">
            Built with Claude · Always verify critical bookings and prices before travel.
          </footer>
        </div>
      </body>
    </html>
  );
}
