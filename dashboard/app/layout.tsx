import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GFX Sync Dashboard",
  description: "GFX JSON Supabase 동기화 대시보드",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex items-center">
                <span className="text-xl font-bold text-gray-900">
                  GFX Sync Dashboard
                </span>
              </div>
              <div className="flex items-center space-x-4">
                <a
                  href="/"
                  className="text-gray-600 hover:text-gray-900 px-3 py-2"
                >
                  대시보드
                </a>
                <a
                  href="/errors"
                  className="text-gray-600 hover:text-gray-900 px-3 py-2"
                >
                  오류
                </a>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          {children}
        </main>
      </body>
    </html>
  );
}
