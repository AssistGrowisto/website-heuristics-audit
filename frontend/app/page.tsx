'use client'

import { useState, useRef } from 'react'

type AuditStage = 'idle' | 'fetching' | 'analyzing_seo' | 'analyzing_cwv' | 'analyzing_ux' | 'analyzing_conversion' | 'generating' | 'done' | 'error'

const STAGE_LABELS: Record<AuditStage, string> = {
  idle: '',
  fetching: 'Fetching website...',
  analyzing_seo: 'Analyzing SEO parameters...',
  analyzing_cwv: 'Analyzing Core Web Vitals...',
  analyzing_ux: 'Analyzing UX & Usability...',
  analyzing_conversion: 'Analyzing Conversion factors...',
  generating: 'Generating Excel report...',
  done: 'Audit complete!',
  error: 'Audit failed',
}

const STAGE_PROGRESS: Record<AuditStage, number> = {
  idle: 0,
  fetching: 10,
  analyzing_seo: 30,
  analyzing_cwv: 50,
  analyzing_ux: 65,
  analyzing_conversion: 80,
  generating: 92,
  done: 100,
  error: 0,
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function Home() {
  const [url, setUrl] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showCredentials, setShowCredentials] = useState(false)
  const [stage, setStage] = useState<AuditStage>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [downloadFilename, setDownloadFilename] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const isLoading = !['idle', 'done', 'error'].includes(stage)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    const trimmedUrl = url.trim()
    if (!trimmedUrl) return

    // Reset state
    setStage('fetching')
    setErrorMessage('')
    setDownloadUrl(null)
    setDownloadFilename('')

    // Abort any previous request
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    // Simulate progress stages while waiting for API
    const stageTimers: NodeJS.Timeout[] = []
    stageTimers.push(setTimeout(() => setStage('analyzing_seo'), 3000))
    stageTimers.push(setTimeout(() => setStage('analyzing_cwv'), 8000))
    stageTimers.push(setTimeout(() => setStage('analyzing_ux'), 14000))
    stageTimers.push(setTimeout(() => setStage('analyzing_conversion'), 20000))
    stageTimers.push(setTimeout(() => setStage('generating'), 28000))

    try {
      const body: Record<string, string> = { url: trimmedUrl }
      if (showCredentials && username.trim()) {
        body.username = username.trim()
        body.password = password
      }

      const response = await fetch(`${API_BASE_URL}/api/audit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abortRef.current.signal,
      })

      // Clear simulated progress
      stageTimers.forEach(clearTimeout)

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errData.detail || `HTTP ${response.status}`)
      }

      // Get filename from Content-Disposition header
      const disposition = response.headers.get('Content-Disposition')
      let filename = 'audit_report.xlsx'
      if (disposition) {
        const match = disposition.match(/filename=(.+?)(?:;|$)/)
        if (match) filename = match[1].replace(/"/g, '')
      }

      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)

      setDownloadUrl(blobUrl)
      setDownloadFilename(filename)
      setStage('done')

    } catch (err: any) {
      stageTimers.forEach(clearTimeout)
      if (err.name === 'AbortError') return
      setStage('error')
      setErrorMessage(err.message || 'Failed to complete audit')
    }
  }

  function handleDownload() {
    if (!downloadUrl) return
    const a = document.createElement('a')
    a.href = downloadUrl
    a.download = downloadFilename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  function handleReset() {
    setStage('idle')
    setErrorMessage('')
    if (downloadUrl) URL.revokeObjectURL(downloadUrl)
    setDownloadUrl(null)
    setDownloadFilename('')
  }

  return (
    <main className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center gap-3">
          <div className="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Website Heuristics Audit</h1>
            <p className="text-sm text-gray-500">SEO · Core Web Vitals · UX · Conversion</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex items-start justify-center pt-12 pb-16 px-6">
        <div className="w-full max-w-2xl">

          {/* Audit Form Card */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-8">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Run Website Audit</h2>
              <p className="text-sm text-gray-500 mb-6">
                Enter a website URL to get a comprehensive heuristics audit with 80+ parameters scored across SEO, performance, usability, and conversion.
              </p>

              <form onSubmit={handleSubmit}>
                {/* URL Input */}
                <div className="mb-4">
                  <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1.5">
                    Website URL
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                      <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
                      </svg>
                    </div>
                    <input
                      id="url"
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://example.com"
                      className="w-full pl-11 pr-4 py-3 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                      disabled={isLoading}
                      required
                    />
                  </div>
                </div>

                {/* Login Credentials Toggle */}
                <div className="mb-4">
                  <button
                    type="button"
                    onClick={() => setShowCredentials(!showCredentials)}
                    className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600 transition-colors"
                  >
                    <svg className={`w-4 h-4 transition-transform ${showCredentials ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                    </svg>
                    <span>Login credentials {showCredentials ? '(optional)' : '— for password-protected sites'}</span>
                  </button>

                  {showCredentials && (
                    <div className="mt-3 p-4 bg-gray-50 rounded-xl border border-gray-200 space-y-3">
                      <p className="text-xs text-gray-500 mb-2">
                        If the website requires login, provide credentials below. The tool will attempt to authenticate before running the audit.
                      </p>
                      <div>
                        <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
                          Username / Email
                        </label>
                        <input
                          id="username"
                          type="text"
                          value={username}
                          onChange={(e) => setUsername(e.target.value)}
                          placeholder="user@example.com"
                          className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors text-sm"
                          disabled={isLoading}
                          autoComplete="username"
                        />
                      </div>
                      <div>
                        <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                          Password
                        </label>
                        <input
                          id="password"
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="••••••••"
                          className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors text-sm"
                          disabled={isLoading}
                          autoComplete="current-password"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={isLoading || !url.trim()}
                  className="w-full py-3 px-6 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>Auditing...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                      </svg>
                      <span>Start Audit</span>
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Progress Section */}
            {isLoading && (
              <div className="border-t border-gray-200 bg-gray-50 px-8 py-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-gray-700">{STAGE_LABELS[stage]}</span>
                  <span className="text-sm text-gray-500">{STAGE_PROGRESS[stage]}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-primary-600 h-2.5 rounded-full transition-all duration-1000 ease-out"
                    style={{ width: `${STAGE_PROGRESS[stage]}%` }}
                  />
                </div>
                <div className="mt-4 flex items-center gap-6 text-xs text-gray-500">
                  <StageIndicator label="SEO" active={['analyzing_seo', 'analyzing_cwv', 'analyzing_ux', 'analyzing_conversion', 'generating'].includes(stage)} done={['analyzing_cwv', 'analyzing_ux', 'analyzing_conversion', 'generating'].includes(stage)} />
                  <StageIndicator label="CWV" active={['analyzing_cwv', 'analyzing_ux', 'analyzing_conversion', 'generating'].includes(stage)} done={['analyzing_ux', 'analyzing_conversion', 'generating'].includes(stage)} />
                  <StageIndicator label="UX" active={['analyzing_ux', 'analyzing_conversion', 'generating'].includes(stage)} done={['analyzing_conversion', 'generating'].includes(stage)} />
                  <StageIndicator label="Conversion" active={['analyzing_conversion', 'generating'].includes(stage)} done={['generating'].includes(stage)} />
                </div>
              </div>
            )}

            {/* Success State */}
            {stage === 'done' && downloadUrl && (
              <div className="border-t border-gray-200 bg-green-50 px-8 py-6">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                    <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-green-900">Audit Complete</h3>
                    <p className="text-sm text-green-700 mt-0.5">
                      Your comprehensive heuristic audit report is ready with 80+ scored parameters.
                    </p>
                    <div className="mt-4 flex gap-3">
                      <button
                        onClick={handleDownload}
                        className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded-lg transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                        </svg>
                        Download Excel Report
                      </button>
                      <button
                        onClick={handleReset}
                        className="inline-flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg border border-gray-300 transition-colors"
                      >
                        Audit Another Site
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Error State */}
            {stage === 'error' && (
              <div className="border-t border-gray-200 bg-red-50 px-8 py-6">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                    <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-red-900">Audit Failed</h3>
                    <p className="text-sm text-red-700 mt-0.5">{errorMessage}</p>
                    <button
                      onClick={handleReset}
                      className="mt-3 inline-flex items-center gap-2 px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg border border-gray-300 transition-colors"
                    >
                      Try Again
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Feature Cards */}
          <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <FeatureCard icon="seo" title="SEO" description="Meta tags, schema, headings, sitemap, security headers" />
            <FeatureCard icon="cwv" title="Core Web Vitals" description="Page size, JS/CSS, images, fonts, compression" />
            <FeatureCard icon="ux" title="UX / Usability" description="Mobile-friendliness, a11y, navigation, forms" />
            <FeatureCard icon="conversion" title="Conversion" description="CTAs, trust signals, social proof, forms" />
          </div>

          {/* Footer */}
          <p className="text-center text-xs text-gray-400 mt-8">
            Powered by Website Heuristics Audit Engine · 80+ Parameters · Downloadable Excel Reports
          </p>
        </div>
      </div>
    </main>
  )
}

function StageIndicator({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${done ? 'bg-green-500' : active ? 'bg-primary-500 animate-pulse' : 'bg-gray-300'}`} />
      <span className={done ? 'text-green-600 font-medium' : active ? 'text-primary-600 font-medium' : 'text-gray-400'}>{label}</span>
    </div>
  )
}

function FeatureCard({ icon, title, description }: { icon: string; title: string; description: string }) {
  const icons: Record<string, JSX.Element> = {
    seo: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
    cwv: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
    ux: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3" />
      </svg>
    ),
    conversion: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
      </svg>
    ),
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow">
      <div className="w-9 h-9 bg-primary-50 text-primary-600 rounded-lg flex items-center justify-center mb-2.5">
        {icons[icon]}
      </div>
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <p className="text-xs text-gray-500 mt-1 leading-relaxed">{description}</p>
    </div>
  )
}

