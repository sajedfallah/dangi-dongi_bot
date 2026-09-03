import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'
import './hero-illustration.css'
import './hero-art.css'
import './onboarding-v3.css'
import { initTelegram } from './telegram'

initTelegram()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
