import { useMemo, useState } from 'react'
import { fetchRecommendations } from '../api'

export default function InputForm({ meta, onResult }) {
  const [farmerId, setFarmerId] = useState('F1001')
  const [state, setState] = useState('')
  const [district, setDistrict] = useState('')
  const [soilType, setSoilType] = useState('')
  const [previousCrop, setPreviousCrop] = useState('')
  const [outcome, setOutcome] = useState('profit')
  const [profitAmount, setProfitAmount] = useState('')
  const [cropSearch, setCropSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const states = Object.keys(meta.states).sort()
  const districts = state ? meta.states[state] : []
  const filteredCrops = useMemo(() => {
    const q = cropSearch.trim().toLowerCase()
    return meta.crops
      .map((c) => c.crop_name)
      .filter((c) => c.toLowerCase().includes(q))
      .slice(0, 8)
  }, [meta.crops, cropSearch])

  // auto-pick the district's dominant soil type
  const pickDistrict = (d) => {
    setDistrict(d)
    const entry = districts.find((x) => x.district === d)
    if (entry) setSoilType(entry.soil_type)
  }

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const payload = {
        farmer_id: farmerId.trim() || 'anonymous',
        soil_type: soilType,
        state,
        district,
        previous_crop: previousCrop,
        previous_outcome: outcome,
      }
      if (profitAmount !== '') payload.previous_profit_amount = Number(profitAmount)
      const data = await fetchRecommendations(payload)
      onResult(data, payload)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const label = 'block text-sm font-medium text-gray-700 mb-1'
  const input =
    'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 bg-white'

  return (
    <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label className={label}>Farmer ID</label>
        <input className={input} value={farmerId}
               onChange={(e) => setFarmerId(e.target.value)}
               placeholder="e.g. F1023" />
      </div>

      <div>
        <label className={label}>State</label>
        <select required className={input} value={state}
                onChange={(e) => { setState(e.target.value); setDistrict('') }}>
          <option value="">Select state...</option>
          {states.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>

      <div>
        <label className={label}>District</label>
        <select required className={input} value={district} disabled={!state}
                onChange={(e) => pickDistrict(e.target.value)}>
          <option value="">Select district...</option>
          {districts.map((d) => <option key={d.district}>{d.district}</option>)}
        </select>
      </div>

      <div>
        <label className={label}>
          Soil type{' '}
          {district && (
            <span className="text-xs text-green-600">(auto-set from district)</span>
          )}
        </label>
        <select required className={input} value={soilType}
                onChange={(e) => setSoilType(e.target.value)}>
          <option value="">Select soil...</option>
          {meta.soil_types.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>

      <div className="relative">
        <label className={label}>Previous crop (search)</label>
        <input
          className={input}
          value={previousCrop ? `${previousCrop}` : cropSearch}
          onChange={(e) => { setPreviousCrop(''); setCropSearch(e.target.value) }}
          placeholder="Type to search crops..."
          required
        />
        {!previousCrop && cropSearch && (
          <ul className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-auto">
            {filteredCrops.map((c) => (
              <li key={c}>
                <button type="button"
                        className="w-full text-left px-3 py-2 text-sm hover:bg-green-50"
                        onClick={() => { setPreviousCrop(c); setCropSearch('') }}>
                  {c}
                </button>
              </li>
            ))}
            {filteredCrops.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-400">No matches</li>
            )}
          </ul>
        )}
      </div>

      <div>
        <label className={label}>Last season outcome</label>
        <div className="flex rounded-lg overflow-hidden border border-gray-300">
          {['profit', 'loss'].map((o) => (
            <button key={o} type="button" onClick={() => setOutcome(o)}
                    className={`flex-1 py-2 text-sm font-medium transition-colors ${
                      outcome === o
                        ? o === 'profit'
                          ? 'bg-green-600 text-white'
                          : 'bg-red-500 text-white'
                        : 'bg-white text-gray-600 hover:bg-gray-50'
                    }`}>
              {o === 'profit' ? 'Profit' : 'Loss'}
            </button>
          ))}
        </div>
      </div>

      <div className="sm:col-span-2">
        <label className={label}>Approximate margin last season (Rs/acre, optional)</label>
        <input className={input} type="number" step="any"
               placeholder="e.g. -3200 for a loss, 18500 for a profit"
               value={profitAmount} onChange={(e) => setProfitAmount(e.target.value)} />
      </div>

      {error && (
        <p className="sm:col-span-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
          {error}
        </p>
      )}

      <div className="sm:col-span-2">
        <button type="submit" disabled={loading}
                className="w-full sm:w-auto px-8 py-2.5 rounded-lg bg-green-700 text-white font-semibold hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {loading ? 'Analyzing...' : 'Get Top-3 Crop Recommendations'}
        </button>
      </div>
    </form>
  )
}
