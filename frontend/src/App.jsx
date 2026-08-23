import { useEffect, useState } from 'react'
import { fetchMeta } from './api'
import InputForm from './components/InputForm'
import RecommendationCards from './components/RecommendationCards'
import HistoryPanel from './components/HistoryPanel'

export default function App() {
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState(null)
  const [result, setResult] = useState(null)
  const [lastRequest, setLastRequest] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    fetchMeta().then(setMeta).catch((e) => setMetaError(e.message))
  }, [])

  const handleResult = (data, request) => {
    setResult(data)
    setLastRequest(request)
    setRefreshKey((k) => k + 1)
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-green-50 to-amber-50 text-gray-800">
      <header className="bg-green-700 text-white shadow-md">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            AI Crop Recommendation System
          </h1>
          <p className="text-green-100 mt-1 text-sm sm:text-base">
            Decide the most profitable crop to sow next season - ranked by predicted
            net profit per acre.
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        {metaError && (
          <div className="bg-red-100 border border-red-300 text-red-700 rounded-lg p-4">
            Could not reach the backend ({metaError}). Start it with:{' '}
            <code className="bg-red-50 px-1 rounded">uvicorn backend.main:app --port 8000</code>
          </div>
        )}

        {meta && (
          <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
            <h2 className="text-lg font-semibold mb-4 text-green-800">
              Your farm details
            </h2>
            <InputForm meta={meta} onResult={handleResult} />
          </section>
        )}

        {result && (
          <RecommendationCards data={result} />
        )}

        <HistoryPanel refreshKey={refreshKey} lastRequest={lastRequest} />
      </main>

      <footer className="max-w-5xl mx-auto px-4 pb-8 text-xs text-gray-500">
        Demo only - soil, weather and market data are synthetically generated.
        Swap in Soil Health Card, IMD and Agmarknet feeds for production use.
      </footer>
    </div>
  )
}
