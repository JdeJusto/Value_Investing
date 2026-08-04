interface MetricCardProps {
  label: string
  value: string
  interpretation?: string
  highlight?: 'positive' | 'negative' | 'neutral'
}

export default function MetricCard({ label, value, interpretation, highlight }: MetricCardProps) {
  const colorMap = {
    positive: 'text-[#00cc88]',
    negative: 'text-red-400',
    neutral: 'text-white',
  }

  const bgMap = {
    positive: 'bg-[#00cc88]/5',
    negative: 'bg-red-400/5',
    neutral: 'bg-[#1a1c23]',
  }

  return (
    <div className={`${bgMap[highlight || 'neutral']} rounded-xl p-4 border border-[#2d3139]`}>
      <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-lg font-semibold ${colorMap[highlight || 'neutral']}`}>{value}</div>
      {interpretation && <div className="text-xs text-gray-500 mt-1">{interpretation}</div>}
    </div>
  )
}
