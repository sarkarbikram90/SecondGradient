# SecondGradient Frontend

Next.js application for real-time ML system monitoring and prediction visualization.

## Structure

```
services/frontend/
├── components/
│   ├── Dashboard.tsx          # Main dashboard layout
│   ├── SignalChart.tsx        # Real-time signal graphs
│   ├── PredictionPanel.tsx    # Failure prediction display
│   ├── RootCauseAlert.tsx     # Root cause notifications
│   └── RiskGauge.tsx          # Risk score visualization
├── pages/
│   ├── index.tsx              # Dashboard home
│   ├── model/[id].tsx         # Model detail page
│   └── api/                   # Next.js API routes
├── lib/
│   ├── api.ts                 # API client
│   ├── websocket.ts           # Real-time updates
│   └── types.ts               # TypeScript types
├── styles/
│   └── globals.css            # Tailwind styles
└── package.json
```

## Key Features

- **Real-time Updates**: WebSocket connection for live signal data
- **Interactive Charts**: Chart.js or D3.js for trajectory visualization
- **Alert System**: Toast notifications for predictions and alerts
- **Responsive Design**: Mobile-friendly dashboard

## Sample Component

```tsx
// components/PredictionPanel.tsx
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface Prediction {
  failure_predicted: boolean;
  minutes_remaining: number;
  confidence: string;
}

export default function PredictionPanel({ modelId }: { modelId: string }) {
  const [prediction, setPrediction] = useState<Prediction | null>(null);

  useEffect(() => {
    const fetchPrediction = async () => {
      const data = await api.getPrediction(modelId);
      setPrediction(data);
    };

    fetchPrediction();
    const interval = setInterval(fetchPrediction, 30000); // Update every 30s

    return () => clearInterval(interval);
  }, [modelId]);

  if (!prediction) return <div>Loading...</div>;

  return (
    <div className="bg-red-50 border border-red-200 rounded p-4">
      <h3 className="text-lg font-semibold text-red-800">
        ⚠ Failure Prediction
      </h3>
      {prediction.failure_predicted ? (
        <p className="text-red-700">
          Predicted failure in {prediction.minutes_remaining} minutes
          (Confidence: {prediction.confidence})
        </p>
      ) : (
        <p className="text-green-700">No immediate failure predicted</p>
      )}
    </div>
  );
}
```

## Technology Stack

- **Framework**: Next.js 13+ with App Router
- **Styling**: Tailwind CSS
- **Charts**: Chart.js or Recharts
- **Real-time**: WebSockets or Server-Sent Events
- **State**: React Query for API state management