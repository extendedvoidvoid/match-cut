import Link from 'next/link'
import { Smile, Zap, Music2, Share2, Sparkles, ShieldCheck, Image as ImageIcon, Play, TrendingUp } from 'lucide-react'
import { InstagramIcon } from '@/components/InstagramIcon'

export const metadata = {
  title: 'About – Match Cut Generator',
  description: 'Learn what the Match Cut Generator is, how to use it, and who it is for. Create viral eye-aligned match cut videos and GIFs in seconds.',
  keywords: [
    'match cut',
    'match cut generator',
    'face match cut',
    'eye aligned animation',
    'face alignment video',
    'photo to video',
    'gif maker',
    'mp4 maker',
    'viral video effect',
    'instagram reels',
    'tiktok trend',
    'youtube shorts',
    'music beat sync',
    'auto video editor',
    'ai video tool',
    'creator tools',
    'social media video',
  ],
}

export default function AboutPage() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-yellow-400 rounded-lg flex items-center justify-center">
                <Smile className="w-5 h-5 text-gray-900" />
              </div>
              <Link href="/" className="text-xl font-bold text-gray-900">
                Match Cut Generator
              </Link>
            </div>
            
            <div className="flex items-center space-x-4">
              <Link
                href="/about"
                className="text-blue-600 font-medium px-3 py-2 rounded-md hover:bg-blue-50"
              >
                About
              </Link>
              <a 
                href="https://www.producthunt.com/products/face-match-cut-generator?embed=true&utm_source=badge-featured&utm_medium=badge&utm_source=badge-face&#0045;match&#0045;cut&#0045;generator" 
                target="_blank"
                rel="noopener noreferrer"
                className="hover:opacity-80 transition-opacity"
              >
                <img 
                  src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1015749&theme=light&t=1757742596193" 
                  alt="Face Match Cut Generator - Upload Photos, Generate Eye-Aligned Animations in Seconds | Product Hunt" 
                  style={{ width: '250px', height: '54px' }} 
                  width="250" 
                  height="54" 
                />
              </a>
              
              <a
                href="https://www.instagram.com/sanjogsays/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-500 hover:text-gray-700 transition-colors"
              >
                <InstagramIcon className="w-5 h-5" />
              </a>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Hero */}
        <section className="mb-12">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-4">
                What is a Match Cut? And why this tool?
              </h1>
              <p className="text-lg text-gray-700 mb-4">
                The Match Cut Generator automatically aligns eyes across your photos to create
                a seamless, rhythmic transition between faces. Drop in images, and get a
                smooth, eye-locked animation as a GIF or MP4 in seconds.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                <div className="card p-4 flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <Smile className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <div className="font-medium">Eye‑aligned cuts</div>
                    <div className="text-sm text-gray-600">Smooth transitions locked on the eyes</div>
                  </div>
                </div>
                <div className="card p-4 flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <Zap className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <div className="font-medium">Fast & simple</div>
                    <div className="text-sm text-gray-600">Upload, auto-align, export in seconds</div>
                  </div>
                </div>
                <div className="card p-4 flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <Music2 className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <div className="font-medium">Beat aware</div>
                    <div className="text-sm text-gray-600">Optional music beat‑sync timing</div>
                  </div>
                </div>
                <div className="card p-4 flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <div className="font-medium">Private by design</div>
                    <div className="text-sm text-gray-600">In‑browser processing, no uploads</div>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="card p-4 text-center">
                  <div className="text-2xl font-bold text-blue-600">1M+</div>
                  <div className="text-gray-600 text-sm">Social Impressions</div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-2xl font-bold text-blue-600">Thousands</div>
                  <div className="text-gray-600 text-sm">Active Users</div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-2xl font-bold text-blue-600">Viral</div>
                  <div className="text-gray-600 text-sm">On Reels & TikTok</div>
                </div>
              </div>
            </div>
            <div>
              <div className="bg-white card p-2">
                <div className="relative w-full rounded-lg overflow-hidden">
                  <video
                    src="/effect demo.mp4"
                    autoPlay
                    loop
                    muted
                    playsInline
                    className="w-full h-auto rounded-lg"
                  >
                    Your browser does not support the video tag.
                  </video>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2 text-blue-700"><Play className="w-5 h-5 text-blue-600" /> How to use</h2>
            <ol className="text-gray-700 space-y-3 list-decimal list-inside">
              <li className="flex gap-2 items-start"><ImageIcon className="w-4 h-4 mt-1 text-gray-500" /> Upload a set of clear, front‑facing photos.</li>
              <li className="flex gap-2 items-start"><Sparkles className="w-4 h-4 mt-1 text-gray-500" /> Let the tool detect faces and align eyes automatically.</li>
              <li className="flex gap-2 items-start"><Music2 className="w-4 h-4 mt-1 text-gray-500" /> Optionally enable beat sync for music‑driven timing.</li>
              <li className="flex gap-2 items-start"><Share2 className="w-4 h-4 mt-1 text-gray-500" /> Export as GIF or MP4 and share anywhere.</li>
            </ol>
          </div>
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2 text-blue-700"><TrendingUp className="w-5 h-5 text-blue-600" /> Who it’s for</h2>
            <ul className="text-gray-700 space-y-3 list-disc list-inside">
              <li>Creators making Instagram Reels, TikTok, Shorts.</li>
              <li>Photographers showcasing portraits and transformations.</li>
              <li>Brands and social teams seeking trendy, high‑retention content.</li>
              <li>Anyone who loves satisfying, rhythmic face transitions.</li>
            </ul>
          </div>
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2 text-blue-700"><Sparkles className="w-5 h-5 text-blue-600" /> Why it stands out</h2>
            <ul className="text-gray-700 space-y-3 list-disc list-inside">
              <li>Eye‑locked alignment for clean match cuts.</li>
              <li>In‑browser processing – privacy‑first, no uploads.</li>
              <li>Simple, fast exports (GIF/MP4) ideal for social sharing.</li>
              <li>Optimized for viral, trendy, beat‑matched edits.</li>
            </ul>
          </div>
        </section>

        {/* Music & Sound Guide */}
        <section className="card p-6 mb-12">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2 text-blue-700"><Music2 className="w-5 h-5 text-blue-600" /> Music & Sound</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-gray-700">
            <div>
              <h3 className="font-medium text-gray-900 mb-2">Adding Audio</h3>
              <ul className="list-disc list-inside space-y-2">
                <li>Enable sound in Export options.</li>
                <li>Choose built‑in clicks/pops or upload a custom track.</li>
                <li>Adjust volume to sit under the visuals.</li>
              </ul>
            </div>
            <div>
              <h3 className="font-medium text-gray-900 mb-2">Beat Sync</h3>
              <ul className="list-disc list-inside space-y-2">
                <li>Toggle Beat Sync to analyze your song.</li>
                <li>Fine‑tune sensitivity to lock cuts to the rhythm.</li>
                <li>Use Offset to nudge cuts earlier or later on the beat.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* SEO section (readable, keyword-rich) */}
        <section className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Match Cut Video, Face Alignment, GIF & MP4</h2>
          <p className="text-gray-700">
            Create eye-aligned match cut videos from photos. Perfect for Instagram Reels,
            TikTok, and YouTube Shorts. Generate GIF and MP4 exports, align faces and eyes
            automatically, and optionally sync cuts to music beats. Great for creators,
            editors, photographers, and social media teams seeking viral video effects,
            trends, and high-retention transitions.
          </p>
        </section>
      </main>
    </div>
  )
}


