import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/archivo-black'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/noto-sans-tamil'
import '@fontsource-variable/noto-sans-telugu'
import './styles/tokens.css'
import './styles/landing.css'
import './styles/app.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
