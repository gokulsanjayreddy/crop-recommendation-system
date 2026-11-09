import { useState } from 'react'
import { fetchLiveWeather } from '../api'

const value = (v, unit) => (v == null || v === '' ? '-' : `${Number(v).toFixed(1)}${unit}`)

export default function LiveWeatherCard({ districts = [] }) {
  const [district, setDistrict] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (!district) {
      setError('Select a district first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      setData(await fetchLiveWeather(district))
    } catch (e) {
      setData(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const input =
    'rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white'

  return (
    <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
      <h2 className="text-lg font-semibold mb-4 text-green-800">Live weather</h2>

      <div className="flex flex-wrap gap-2 mb-4">
        <select className={input} value={district}
                onChange={(e) => setDistrict(e.target.value)}>
          <option value="">Select Andhra Pradesh district...</option>
          {districts.map((d) => <option key={d}>{d}</option>)}
        </select>
        <button type="button" onClick={load} disabled={loading}
                className="px-4 py-2 rounded-lg bg-green-700 text-white text-sm font-semibold hover:bg-green-800 disabled:opacity-50">
          {loading ? 'Loading...' : 'Check live weather'}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
          {error}
        </p>
      )}

      {!data && !error && (
        <p className="text-sm text-gray-400">
          Select a district to see current temperature, humidity and rain.
        </p>
      )}

      {data && (
        <div className="rounded-lg border border-gray-200 bg-slate-50 p-4">
          <div className="flex flex-wrap justify-between gap-2">
            <div>
              <div className="font-semibold text-green-800">{data.location}</div>
              <div className="text-xs text-gray-400">{data.timezone}</div>
            </div>
            <div className="text-xs text-gray-400">
              as of {new Date(data.fetched_at).toLocaleString()}
            </div>
          </div>
          <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 text-center">
            <div className="bg-white border border-gray-100 rounded-lg p-3">
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">Temperature</dt>
              <dd className="text-2xl font-extrabold text-green-700">
                {value(data.current.temperature_c, '°C')}
              </dd>
            </div>
            <div className="bg-white border border-gray-100 rounded-lg p-3">
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">Humidity</dt>
              <dd className="text-2xl font-extrabold text-green-700">
                {value(data.current.humidity_pct, '%')}
              </dd>
            </div>
            <div className="bg-white border border-gray-100 rounded-lg p-3">
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">Rain</dt>
              <dd className="text-2xl font-extrabold text-green-700">
                {value(data.current.precipitation_mm, ' mm')}
              </dd>
            </div>
          </dl>
          <div className="text-xs text-gray-400 mt-3">Source: {data.source}</div>
        </div>
      )}
    </section>
  )
}
