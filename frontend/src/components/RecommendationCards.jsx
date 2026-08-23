import { useState } from 'react'

const MEDALS = [
  { ring: 'ring-amber-400', badge: 'bg-gradient-to-br from-amber-400 to-amber-600', label: '#1 Best Choice' },
  { ring: 'ring-gray-300', badge: 'bg-gradient-to-br from-gray-300 to-gray-500', label: '#2' },
  { ring: 'ring-orange-300', badge: 'bg-gradient-to-br from-orange-300 to-orange-600', label: '#3' },
]

const fmt = (n) => `Rs ${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

function Card({ rec }) {
  const [open, setOpen] = useState(false)
  const m = MEDALS[Math.min(rec.rank - 1, MEDALS.length - 1)]
  const profit = rec.predicted_profit_rs_per_acre
  return (
    <div className={`bg-white rounded-xl shadow-sm border border-gray-200 ring-2 ${m.ring} overflow-hidden`}>
      <div className={`${m.badge} text-white px-4 py-1.5 text-xs font-bold tracking-wide uppercase`}>
        {m.label}
      </div>
      <div className="p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xl font-bold text-green-800">{rec.crop_name}</h3>
          <div className="text-right">
            <div className={`text-2xl font-extrabold ${profit >= 0 ? 'text-green-700' : 'text-red-600'}`}>
              {fmt(profit)}
            </div>
            <div className="text-xs text-gray-500">predicted net profit / acre</div>
          </div>
        </div>

        <button onClick={() => setOpen(!open)}
                className="mt-3 text-sm font-medium text-green-700 hover:text-green-900 underline underline-offset-2">
          {open ? 'Hide' : 'Why this crop?'}
        </button>

        {open && (
          <div className="mt-3 space-y-3">
            <p className="text-sm text-gray-600 bg-amber-50 border border-amber-200 rounded-lg p-3">
              {rec.reason}
            </p>
            <dl className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-gray-50 rounded-lg p-2">
                <dt className="text-[11px] uppercase tracking-wide text-gray-500">Yield</dt>
                <dd className="font-semibold text-sm">
                  {rec.predicted_yield_ton_per_acre.toFixed(2)} t/acre
                </dd>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <dt className="text-[11px] uppercase tracking-wide text-gray-500">Price</dt>
                <dd className="font-semibold text-sm">
                  Rs {Math.round(rec.predicted_price_rs_per_quintal).toLocaleString('en-IN')}/qtl
                </dd>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <dt className="text-[11px] uppercase tracking-wide text-gray-500">Cost</dt>
                <dd className="font-semibold text-sm">
                  {fmt(rec.cost_of_cultivation_rs_per_acre)}
                </dd>
              </div>
            </dl>
          </div>
        )}
      </div>
    </div>
  )
}

export default function RecommendationCards({ data }) {
  return (
    <section>
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-lg font-semibold text-green-800">
          Recommended crops for next season
        </h2>
        <span className="text-xs text-gray-400">
          as of {new Date(data.generated_at).toLocaleString()}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.recommendations.map((rec) => <Card key={rec.rank} rec={rec} />)}
      </div>
    </section>
  )
}
