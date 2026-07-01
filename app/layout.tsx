import './globals.css'
import { Plus_Jakarta_Sans } from 'next/font/google'
import { Analytics } from "@vercel/analytics/next"

const plusJakarta = Plus_Jakarta_Sans({ subsets: ['latin'] })

export const metadata = {
  title: 'Match Cut Generator',
  description: 'Auto-aligned Match Cut Video Generator - Create smooth eye-aligned animations from your photos',
  keywords: ['match cut', 'video generator', 'face alignment', 'animation', 'gif', 'mp4'],
  authors: [{ name: 'Match Cut Generator' }],
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
      </head>
      <body className={plusJakarta.className}>
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
          {children}
        </div>
        <Analytics />
      </body>
    </html>
  )
}