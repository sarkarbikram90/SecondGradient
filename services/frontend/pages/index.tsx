import { useState, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

interface PredictionData {
  timestamp: string
  drift: number
  velocity: number
  acceleration: number
  time_to_failure: number
  confidence: number
}

export default function Home() {
  const [data, setData] = useState<PredictionData[]>([])
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/api/predictions')
        if (response.ok) {
          const newData = await response.json()
          setData(prev => [...prev.slice(-50), newData])
          setIsConnected(true)
        }
      } catch (error) {
        setIsConnected(false)
      }
    }

    const interval = setInterval(fetchData, 1000)
    return () => clearInterval(interval)
  }, [])

  const chartData = {
    labels: data.map(d => new Date(d.timestamp).toLocaleTimeString()),
    datasets: [
      {
        label: 'Drift',
        data: data.map(d => d.drift),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
        yAxisID: 'y',
      },
      {
        label: 'Velocity',
        data: data.map(d => d.velocity),
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        yAxisID: 'y1',
      },
      {
        label: 'Acceleration',
        data: data.map(d => d.acceleration),
        borderColor: 'rgb(255, 205, 86)',
        backgroundColor: 'rgba(255, 205, 86, 0.5)',
        yAxisID: 'y1',
      },
    ],
  }

  const options = {
    responsive: true,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    stacked: false,
    plugins: {
      title: {
        display: true,
        text: 'Real-time Drift Analysis',
      },
    },
    scales: {
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
      },
      y1: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        grid: {
          drawOnChartArea: false,
        },
      },
    },
  }

  const latest = data[data.length - 1]

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-2">SecondGradient</h1>
          <p className="text-xl text-gray-300">Real-time Predictive Intelligence</p>
          <div className="mt-4 flex items-center gap-4">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-sm">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
          <div className="bg-gray-800 p-6 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">Current Drift</h3>
            <div className="text-3xl font-bold text-red-400">
              {latest ? latest.drift.toFixed(3) : 'N/A'}
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">Time to Failure</h3>
            <div className="text-3xl font-bold text-yellow-400">
              {latest ? `${latest.time_to_failure.toFixed(1)}s` : 'N/A'}
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">Confidence</h3>
            <div className="text-3xl font-bold text-green-400">
              {latest ? `${(latest.confidence * 100).toFixed(1)}%` : 'N/A'}
            </div>
          </div>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg">
          <Line data={chartData} options={options} />
        </div>
      </div>
    </div>
  )
}