import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Website Heuristics Audit Tool',
  description: 'Comprehensive website audit covering SEO, Core Web Vitals, UX, and Conversion optimization',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen">
        {children}
      </body>
    </html>
  )
}
