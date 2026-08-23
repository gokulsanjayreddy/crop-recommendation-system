import { useEffect, useState } from 'react'
import { fetchHistory, logSeason } from '../api'

export default function HistoryPanel({ refreshKey, lastRequest }) {
  const [farmerId, setFarmerId] = useState('')
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [logged, setLogged] = useState(false)
  const [logging, setLogging] = useState(false)
  const [localTick, setLocalTick] = useState(0)

  useEffect(() => {
    if (lastRequest && refreshKey > 0) setFarmerId(lastRequest.farmer_id)
  }, [refreshKey]) // eslint-disable-line

  useEffect(() => {
    if (!farmerId) return
    setLogged(false)
    setError(null)
    fetchHistory(farmerId).then(setRows).catch((e) => setError(e.message))
  }, [farmerId, refreshKey, localTick])

  const logThisSeason = async () => {
    if (!lastRequest) return
    setLogging(true)
    try {
      await logSeason({
        farmer_id: farmerId,
        season: 'Kharif',
        year: new Date().getFullYear(),
        soil_type: lastRequest.soil_type,
        previous_crop: lastRequest.previous_crop,
        outcome: lastRequest.previous_outcome,
        profit_amount_rs_per_acre:
          lastRequest.previous_profit_amount ?? null,
        next_crop_sown: rows?.length
          ? rows[rows.length - 1].next_crop_sown
          : '',
      })
      setLogged(true)
      setLocalTick((t) => t + 1)
    } catch (e) {
      setError(e.message)
    } finally {
      setLogging(false)
    }
  }

  return (
    <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold text-green-800">Season history</h2>
        <div className="flex gap-2">
          <input
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="Farmer ID e.g. F1001"
            value={farmerId}
            onChange={(e) => setFarmerId(e.target.value.trim())}
          />
          {lastRequest && (
            <button onClick={logThisSeason} disabled={logging || logged}
                    className="px-4 py-1.5 rounded-lg bg-amber-500 text-white text-sm font-semibold hover:bg-amber-600 disabled:opacity-50">
              {logged ? 'Logged' : logging ? 'Saving...' : 'Log this season'}
            </button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {!farmerId ? (
        <p className="text-sm text-gray-400">Enter a Farmer ID to view logged seasons.</p>
      ) : !rows ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gray-400">No history found for {farmerId}.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b border-gray-200">
                <th className="py-2 pr-4">Year</th>
                <th className="py-2 pr-4">Season</th>
                <th className="py-2 pr-4">Soil</th>
                <th className="py-2 pr-4">Previous crop</th>
                <th className="py-2 pr-4">Crop sown</th>
                <th className="py-2 pr-4">Outcome</th>
                <th className="py-2">Profit (Rs/acre)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-green-50/50">
                  <td className="py-2 pr-4">{r.year}</td>
                  <td className="py-2 pr-4">{r.season}</td>
                  <td className="py-2 pr-4">{r.soil_type}</td>
                  <td className="py-2 pr-4">{r.previous_crop || '-'}</td>
                  <td className="py-2 pr-4 font-medium">{r.next_crop_sown}</td>
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                      r.outcome === 'profit'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {r.outcome}
                    </span>
                  </td>
                  <td className="py-2 font-medium">
                    {r.profit_amount_rs_per_acre != null
                      ? Math.round(r.profit_amount_rs_per_acre).toLocaleString('en-IN')
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
